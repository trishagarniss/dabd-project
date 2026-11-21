"""
Batch Source 1: OurAirports global airport master (F-02, F-03).

Real, public-domain data from https://davidmegginson.github.io/ourairports-data/airports.csv
Writes an idempotent raw/bronze snapshot with batch_id, source, ingest_time and checksum.
The fallback below only uses a previously downloaded local snapshot; it never invents rows.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

import pandas as pd
import requests

from src.common.config import (
    BRONZE_DIR, EVIDENCE_DIR, OURAIRPORTS_URL, REFERENCE_DIR, RUN_ID, utcnow_iso,
)
from src.common.lineage import record_lineage
from src.common.logging_utils import get_logger
from src.common.metrics import count_event, measure_job
from src.common.storage import write_snapshot

log = get_logger("batch.airports")
RAW_PATH = BRONZE_DIR / "airports_raw"
LOCAL_CACHE = REFERENCE_DIR / "airports_reference.csv"
JOB_EVIDENCE = EVIDENCE_DIR / "jobs"
COLUMNS = [
    "ident", "iata_code", "name", "type", "latitude_deg", "longitude_deg",
    "elevation_ft", "iso_country", "municipality",
]


def _batch_id(source: str, checksum: str) -> str:
    return "BATCH_AIRPORTS_" + hashlib.sha256(f"{source}|{checksum}".encode()).hexdigest()[:16]


def _write_status(batch_id: str, status: str, **extra: object) -> None:
    JOB_EVIDENCE.mkdir(parents=True, exist_ok=True)
    payload = {"batch_id": batch_id, "run_id": RUN_ID, "status": status,
               "checked_at": utcnow_iso(), **extra}
    (JOB_EVIDENCE / f"airports_{batch_id}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )


def _load_source(source_url: str, offline: bool) -> tuple[pd.DataFrame, str, str]:
    if offline or not source_url:
        if not LOCAL_CACHE.exists():
            raise FileNotFoundError(
                "Offline mode needs a cached OurAirports snapshot at data/reference/airports_reference.csv"
            )
        raw_bytes = LOCAL_CACHE.read_bytes()
        source = f"local-cache:{LOCAL_CACHE.name}"
    else:
        response = requests.get(source_url, timeout=60, headers={"User-Agent": "SkyPulseAcademic/1.0"})
        response.raise_for_status()
        raw_bytes = response.content
        source = source_url
    checksum = hashlib.sha256(raw_bytes).hexdigest()
    frame = pd.read_csv(io.BytesIO(raw_bytes), low_memory=False)
    return frame, source, checksum


def download_and_process_airports(source_url: str = OURAIRPORTS_URL, offline: bool = False,
                                  mode: str = "manual") -> pd.DataFrame:
    batch_id = "PENDING"
    try:
        frame, source, checksum = _load_source(source_url, offline)
        batch_id = _batch_id(source, checksum)

        clean = frame[
            frame["type"].isin(["large_airport", "medium_airport"])
            & frame["latitude_deg"].notna() & frame["longitude_deg"].notna()
        ].copy()
        clean = clean[[c for c in COLUMNS if c in clean.columns]].drop_duplicates(subset=["ident"])
        clean["batch_id"] = batch_id
        clean["source"] = source
        clean["source_checksum"] = checksum
        clean["row_count"] = len(clean)
        clean["ingest_time"] = utcnow_iso()

        with measure_job("ingest_airports") as meta:
            snapshot = write_snapshot(clean, RAW_PATH, keys=["ident"],
                                      description="Raw OurAirports master with ingestion metadata")
            meta["rows"] = len(clean)
            REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
            clean.to_csv(LOCAL_CACHE, index=False)

        record_lineage(RUN_ID, "ingest_airports", [source], ["bronze.airports_raw"],
                       {"bronze.airports_raw": len(clean)}, consumers=["transform_batch"])
        _write_status(batch_id, "SUCCESS", mode=mode, checksum=checksum,
                      row_count=len(clean), snapshot_version=snapshot["version"])
        count_event("bronze_airports", "batch")
        log.info("airport batch ingested", extra={"batch_id": batch_id, "job": "ingest_airports",
                                                  "rows": len(clean), "status": "SUCCESS"})
        return clean
    except Exception as exc:
        _write_status(batch_id, "FAILED", error=str(exc), mode=mode, retryable=True)
        log.error("airport batch failed", extra={"job": "ingest_airports", "status": "FAILED",
                                                 "error": str(exc)})
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest OurAirports master data into Bronze")
    parser.add_argument("--offline", action="store_true", help="Use cached snapshot instead of network")
    parser.add_argument("--mode", choices=["manual", "scheduled"], default="manual")
    parser.add_argument("--backfill-start", help="ISO date for backfill start (documentation/control field)")
    parser.add_argument("--backfill-end", help="ISO date for backfill end (documentation/control field)")
    parser.add_argument("--retry", type=int, default=0, help="Retry attempts on failure")
    args = parser.parse_args()

    for attempt in range(args.retry + 1):
        try:
            download_and_process_airports(offline=args.offline, mode=args.mode)
            return
        except Exception:
            if attempt >= args.retry:
                raise
            log.warning("retrying airport ingest", extra={"job": "ingest_airports", "attempt": attempt + 2})


if __name__ == "__main__":
    main()
