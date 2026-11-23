"""Prometheus metrics + file snapshots for pipeline, stream, serving and ML (F-14)."""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.common.config import EVIDENCE_DIR, RUN_ID, SERVICE_NAME, utcnow_iso
from src.common.logging_utils import get_logger

log = get_logger("metrics")

try:
    from prometheus_client import Counter, Gauge, Histogram, generate_latest
except ImportError:  # pragma: no cover - fallback keeps local runs working
    Counter = Gauge = Histogram = None  # type: ignore[assignment]
    generate_latest = None  # type: ignore[assignment]

if Counter is not None:
    EVENTS = Counter("fdp_events_total", "Events processed", ["status", "service"])
    JOB_ROWS = Counter("fdp_job_rows_total", "Rows processed by jobs", ["job", "status"])
    JOB_DURATION = Histogram("fdp_job_duration_seconds", "Job duration", ["job"])
    STREAM_LAG = Gauge("fdp_stream_lag_seconds", "Consumer lag in seconds", ["topic"])
    FRESHNESS = Gauge("fdp_ingest_freshness_seconds", "Age of newest ingested record", ["dataset"])
    API_ERRORS = Counter("fdp_api_errors_total", "API errors", ["endpoint", "status_code"])
    INFERENCES = Counter("fdp_inference_total", "ML inference calls", ["status", "model_version"])
    QUALITY_RATIO = Gauge("fdp_quality_pass_ratio", "Quality gate pass ratio", ["dataset"])
    CPU_USAGE = Gauge("fdp_cpu_percent", "Process CPU percent")
    MEM_USAGE = Gauge("fdp_memory_mb", "Process memory MB")
    DISK_USAGE = Gauge("fdp_disk_free_mb", "Free disk MB on data volume")
    MODEL_INFO = Gauge("fdp_model_info", "Loaded model version (1=loaded)", ["model_version"])
else:  # pragma: no cover
    EVENTS = JOB_ROWS = JOB_DURATION = API_ERRORS = INFERENCES = None
    STREAM_LAG = FRESHNESS = QUALITY_RATIO = CPU_USAGE = MEM_USAGE = DISK_USAGE = MODEL_INFO = None

SNAPSHOTS = EVIDENCE_DIR / "metrics"


@contextmanager
def measure_job(job: str) -> Iterator[dict]:
    """Time a job and record duration/rows for the benchmark evidence (F-19)."""
    started = time.perf_counter()
    meta: dict = {"job": job, "run_id": RUN_ID, "started_at": utcnow_iso(), "rows": 0}
    try:
        yield meta
        meta["status"] = "SUCCESS"
    except Exception as exc:
        meta["status"] = "FAILED"
        meta["error"] = str(exc)
        log.error("job failed", extra={"job": job, "status": "FAILED", "error": str(exc)})
        raise
    finally:
        meta["duration_sec"] = round(time.perf_counter() - started, 4)
        meta["finished_at"] = utcnow_iso()
        if JOB_DURATION is not None:
            JOB_DURATION.labels(job=job).observe(meta["duration_sec"])
            JOB_ROWS.labels(job=job, status=meta["status"]).inc(meta.get("rows", 0))
        write_snapshot("job", meta)


def count_event(status: str, service: str | None = None) -> None:
    if EVENTS is not None:
        EVENTS.labels(status=status, service=service or SERVICE_NAME).inc()


def set_lag(seconds: float, topic: str) -> None:
    if STREAM_LAG is not None:
        STREAM_LAG.labels(topic=topic).set(max(0.0, seconds))


def set_freshness(seconds: float, dataset: str) -> None:
    if FRESHNESS is not None:
        FRESHNESS.labels(dataset=dataset).set(max(0.0, seconds))


def set_quality(dataset: str, ratio: float) -> None:
    if QUALITY_RATIO is not None:
        QUALITY_RATIO.labels(dataset=dataset).set(ratio)


def api_error(endpoint: str, status_code: int) -> None:
    if API_ERRORS is not None:
        API_ERRORS.labels(endpoint=endpoint, status_code=str(status_code)).inc()


def inference(status: str, model_version: str) -> None:
    if INFERENCES is not None:
        INFERENCES.labels(status=status, model_version=model_version).inc()


def mark_model(model_version: str) -> None:
    if MODEL_INFO is not None:
        MODEL_INFO.labels(model_version=model_version).set(1)


def _refresh_system() -> None:
    if CPU_USAGE is None:
        return
    try:
        import psutil

        CPU_USAGE.set(psutil.cpu_percent(interval=None))
        MEM_USAGE.set(psutil.Process().memory_info().rss / 1024 / 1024)
        DISK_USAGE.set(psutil.disk_usage(str(SNAPSHOTS.parent.parent)).free / 1024 / 1024)
    except Exception:  # pragma: no cover
        pass


def prometheus_text() -> bytes:
    _refresh_system()
    if generate_latest is None:  # pragma: no cover
        return b""
    return generate_latest()


def start_metrics_server(port: int = 9001) -> None:
    """Expose this process's registry so Prometheus can scrape worker metrics."""
    if generate_latest is None:  # pragma: no cover
        log.warning("prometheus_client unavailable; metrics server not started")
        return
    try:
        from prometheus_client import start_http_server

        start_http_server(port, addr="0.0.0.0")
        log.info("metrics server started", extra={"port": port})
    except Exception as exc:  # pragma: no cover - keep the worker running
        log.warning("metrics server failed", extra={"port": port, "error": str(exc)})


def write_snapshot(kind: str, payload: dict) -> Path:
    """Persist a metric snapshot as evidence even when Prometheus is not deployed."""
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOTS / f"{kind}_{RUN_ID}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    return path
