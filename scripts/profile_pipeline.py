"""Reproducible profiling for F-19: throughput, freshness percentiles, serving p95, resources."""
from __future__ import annotations

import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
from fastapi.testclient import TestClient

from src.common.config import BRONZE_DIR, EVIDENCE_DIR, GOLD_DIR
from src.common.storage import read_jsonl, read_latest, write_snapshot
from src.serving.api import app

WARMUP = 3
SAMPLES = 30
SEED_INPUT = "api/v1/flights/active?limit=20"
OUT = EVIDENCE_DIR / "profiling"


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()

    # 1) Batch write throughput: identical input (Gold feature mart), warm-up then measure.
    frame = read_latest(GOLD_DIR / "flight_delay_features")
    for attempt in range(WARMUP):
        write_snapshot(frame.head(100), OUT / "warmup", keys=["flight_record_id"])
    durations = []
    for _ in range(SAMPLES):
        begin = time.perf_counter()
        write_snapshot(frame, OUT / "throughput_run", keys=["flight_record_id"])
        durations.append(time.perf_counter() - begin)
    write_throughput = len(frame) / statistics.median(durations)

    # 2) Stream freshness percentiles from real Bronze event_time values.
    events = read_jsonl(BRONZE_DIR / "flight_events_raw.jsonl")
    now = datetime.now(timezone.utc)
    ages = []
    for event in events:
        value = event.get("event_time")
        if not value:
            continue
        event_time = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)
        ages.append((now - event_time).total_seconds())

    # 3) Serving latency: warm-up then identical request, 30 samples.
    client = TestClient(app)
    for _ in range(WARMUP):
        client.get("/" + SEED_INPUT, headers={"x-api-key": "demo-viewer-key"})
    latencies = []
    for _ in range(SAMPLES):
        begin = time.perf_counter()
        response = client.get("/" + SEED_INPUT, headers={"x-api-key": "demo-viewer-key"})
        latencies.append((time.perf_counter() - begin) * 1000)
        assert response.status_code == 200

    rows = [
        {"metric": "batch_write_throughput_rows_per_sec", "p50": round(write_throughput, 1),
         "p95": "", "unit": "rows/s", "sample_size": SAMPLES},
        {"metric": "stream_freshness_age_seconds", "p50": round(percentile(ages, 0.50), 1),
         "p95": round(percentile(ages, 0.95), 1), "unit": "s", "sample_size": len(ages)},
        {"metric": "serving_latency_ms", "p50": round(percentile(latencies, 0.50), 2),
         "p95": round(percentile(latencies, 0.95), 2), "unit": "ms", "sample_size": SAMPLES},
        {"metric": "cpu_percent", "p50": round(psutil.cpu_percent(interval=None), 1),
         "p95": "", "unit": "%", "sample_size": 1},
        {"metric": "process_memory_mb", "p50": round(psutil.Process().memory_info().rss / 1024 / 1024, 1),
         "p95": "", "unit": "MB", "sample_size": 1},
        {"metric": "disk_free_mb", "p50": round(psutil.disk_usage(str(ROOT_DIR)).free / 1024 / 1024, 1),
         "p95": "", "unit": "MB", "sample_size": 1},
    ]
    import csv
    with (OUT / "raw_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "p50", "p95", "unit", "sample_size"])
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "hardware": {
            "platform": platform.platform(), "cpu_count": psutil.cpu_count(),
            "total_memory_mb": round(psutil.virtual_memory().total / 1024 / 1024, 1),
            "python": sys.version.split()[0],
        },
        "method": {
            "warmup_runs": WARMUP, "samples": SAMPLES,
            "identical_input": "data/gold/flight_delay_features.parquet and Bronze JSONL",
            "serving_request": SEED_INPUT, "seed": 42,
        },
        "dataset": {"gold_rows": len(frame), "bronze_events": len(events)},
        "metrics": rows,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"metrics": rows, "raw": str(OUT / "raw_metrics.csv")}, indent=2))


ROOT_DIR = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    main()
