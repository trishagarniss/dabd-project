"""
Batch Source 2: BTS TranStats On-Time Performance (F-02, F-11).

Real US DOT flight records with real arrival-delay labels. Public-domain US government data.
Only columns needed for the use case are cached; no personal data and no synthetic rows.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import requests

from src.common.config import (
    BTS_EXPECTED_SHA256, BTS_URL, BRONZE_DIR, EVIDENCE_DIR, RUN_ID, utcnow_iso,
)
from src.common.lineage import record_lineage
from src.common.logging_utils import get_logger
from src.common.metrics import count_event, measure_job
from src.common.storage import write_snapshot

log = get_logger("batch.bts")
RAW_PATH = BRONZE_DIR / "bts_ontime_raw"
CACHE_CSV = BRONZE_DIR / "bts_ontime_2024_01_sample.csv"
PROVENANCE = BRONZE_DIR / "bts_ontime_provenance.json"
USECOLS = [
    "FlightDate", "Reporting_Airline", "Origin", "Dest", "CRSDepTime",
    "DepDelay", "TaxiOut", "CRSElapsedTime", "ArrDelay", "Distance",
    "Cancelled", "Diverted",
]


def _sample(frame: pd.DataFrame, target: int) -> pd.DataFrame:
    if len(frame) <= target:
        return frame
    step = max(1, len(frame) // target)
    return frame.iloc[::step].head(target).reset_index(drop=True)


def ingest_bts_ontime(sample_size: int = 5000, offline: bool = False,
                      mode: str = "manual") -> pd.DataFrame:
    try:
        if offline:
            if not CACHE_CSV.exists():
                raise FileNotFoundError("BTS cache missing; run without --offline once to download it")
            raw_bytes = b""
            archive_name = "cached-sample"
            archive_sha = "cached"
        else:
            response = requests.get(BTS_URL, timeout=240)
            response.raise_for_status()
            raw_bytes = response.content
            archive_sha = hashlib.sha256(raw_bytes).hexdigest()
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
                archive_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
                chunks = []
                with zf.open(archive_name) as source:
                    for chunk in pd.read_csv(source, usecols=USECOLS, chunksize=60000, low_memory=False):
                        chunks.append(_sample(chunk, max(1, sample_size // 12)))
                        if sum(len(c) for c in chunks) >= sample_size:
                            break
                frame = _sample(pd.concat(chunks, ignore_index=True), sample_size)
                if archive_sha != BTS_EXPECTED_SHA256:
                    log.warning("BTS archive checksum differs from recorded baseline",
                                extra={"status": "WARN", "checksum": archive_sha})
        if offline:
            frame = pd.read_csv(CACHE_CSV)
            archive_sha = "cached"

        frame["flight_key"] = (
            frame["FlightDate"].astype(str) + "|" + frame["Reporting_Airline"].astype(str)
            + "|" + frame["Flight_Number_Reporting_Airline"].astype(str) if
            "Flight_Number_Reporting_Airline" in frame.columns else
            frame["FlightDate"].astype(str) + "|" + frame["Reporting_Airline"].astype(str)
            + "|" + frame["Origin"].astype(str) + "|" + frame["Dest"].astype(str)
            + "|" + frame["CRSDepTime"].astype(str)
        )
        frame["source"] = BTS_URL
        frame["archive_sha256"] = archive_sha
        frame["batch_id"] = "BATCH_BTS_" + hashlib.sha256(
            f"{BTS_URL}|{archive_sha}|{len(frame)}".encode()
        ).hexdigest()[:16]
        frame["ingest_time"] = utcnow_iso()

        with measure_job("ingest_bts_ontime") as meta:
            write_snapshot(frame, RAW_PATH, keys=["flight_key"],
                           description="Raw BTS on-time performance sample with provenance")
            meta["rows"] = len(frame)
            frame.to_csv(CACHE_CSV, index=False)

        provenance = {
            "dataset": "BTS On-Time Reporting Carrier Performance, January 2024",
            "source_url": BTS_URL,
            "license": "U.S. Government Work / Public Domain (Bureau of Transportation Statistics)",
            "description": "Real domestic US flight records with scheduled times, distances and arrival delay.",
            "limitations": "US domestic carriers only; one month; no weather join; arrival delay may be negative.",
            "archive_sha256": archive_sha,
            "archive_name": archive_name,
            "sample_size": len(frame),
            "sampling": "deterministic systematic sample across the monthly archive; no generated rows",
            "ingested_at": utcnow_iso(),
            "run_id": RUN_ID,
            "mode": mode,
        }
        PROVENANCE.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        (EVIDENCE_DIR / "dataset_provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        record_lineage(RUN_ID, "ingest_bts_ontime", [BTS_URL], ["bronze.bts_ontime_raw"],
                       {"bronze.bts_ontime_raw": len(frame)}, consumers=["transform_batch"])
        count_event("bronze_bts", "batch")
        log.info("BTS batch ingested", extra={"job": "ingest_bts_ontime", "rows": len(frame),
                                               "status": "SUCCESS"})
        return frame
    except Exception as exc:
        log.error("BTS batch failed", extra={"job": "ingest_bts_ontime", "status": "FAILED",
                                              "error": str(exc)})
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest BTS on-time performance sample into Bronze")
    parser.add_argument("--sample-size", type=int, default=5000)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--mode", choices=["manual", "scheduled"], default="manual")
    args = parser.parse_args()
    ingest_bts_ontime(sample_size=args.sample_size, offline=args.offline, mode=args.mode)


if __name__ == "__main__":
    main()
