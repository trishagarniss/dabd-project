"""Batch scheduler service (F-02): runs ingestion + transformation on a documented interval."""
from __future__ import annotations

import os
import time

from src.batch.ingest_airports import download_and_process_airports
from src.batch.ingest_bts_ontime import ingest_bts_ontime
from src.batch.transform import run_transform
from src.common.config import EVIDENCE_DIR, utcnow_iso
from src.common.logging_utils import get_logger
from src.common.metrics import write_snapshot

log = get_logger("batch.scheduler")
INTERVAL_SEC = int(os.getenv("FDP_BATCH_INTERVAL_SEC", "86400"))
SAMPLE_SIZE = int(os.getenv("FDP_BTS_SAMPLE_SIZE", "5000"))


def run_once() -> dict:
    started = utcnow_iso()
    download_and_process_airports(mode="scheduled")
    ingest_bts_ontime(sample_size=SAMPLE_SIZE, mode="scheduled")
    result = run_transform(retry=2)
    payload = {"started_at": started, "finished_at": utcnow_iso(), "result": result}
    write_snapshot("scheduler", payload)
    return payload


def main() -> None:
    log.info("batch scheduler started", extra={"job": "scheduler", "interval_sec": INTERVAL_SEC})
    while True:
        try:
            run_once()
        except Exception as exc:
            log.error("scheduled batch failed", extra={"job": "scheduler", "status": "FAILED",
                                                      "error": str(exc)})
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
