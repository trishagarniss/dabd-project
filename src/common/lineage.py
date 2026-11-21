"""Dataset catalog, ownership and run-level lineage (F-09)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.common.config import DATA_DIR, LINEAGE_DIR, utcnow_iso
from src.common.storage import append_jsonl, read_jsonl, snapshot_info

CATALOG_FILE = LINEAGE_DIR / "catalog.json"
RUNS_DIR = LINEAGE_DIR / "runs"
LINEAGE_FILE = LINEAGE_DIR / "lineage.jsonl"

DEFAULT_CATALOG: dict[str, Any] = {
    "owner": "SkyPulse Data Platform Team (DABD S5)",
    "classification": "internal-academic",
    "retention": {"bronze": "90 days", "silver": "180 days", "gold": "365 days"},
    "refresh": {"airports": "daily batch", "bts_ontime": "monthly batch", "flight_stream": "15s polling"},
    "datasets": {
        "bronze.airports_raw": {"owner": "Data Engineering", "classification": "public", "location": "data/bronze/airports_raw", "schema": "ident,iata_code,name,latitude_deg,longitude_deg,elevation_ft,iso_country,municipality,batch_id,ingest_time"},
        "bronze.bts_ontime_raw": {"owner": "Data Engineering", "classification": "public", "location": "data/bronze/bts_ontime_raw", "schema": "FlightDate,Origin,Dest,CRSDepTime,ArrDelay,DepDelay,Distance"},
        "bronze.flight_events_raw": {"owner": "Streaming", "classification": "public", "location": "data/bronze/flight_events_raw.jsonl", "schema": "event_id,event_time,ingest_time,payload_version,icao24,..."},
        "silver.airports_clean": {"owner": "Data Engineering", "classification": "public", "location": "data/silver/airports_clean", "schema": "icao_code,iata_code,name,country,latitude,longitude,elevation_ft"},
        "silver.bts_ontime_clean": {"owner": "Data Engineering", "classification": "public", "location": "data/silver/bts_ontime_clean", "schema": "flight_key,flight_date,origin,dest,dep_delay_min,arr_delay_min,distance_miles"},
        "silver.flight_states_clean": {"owner": "Streaming", "classification": "public", "location": "data/silver/flight_states_clean", "schema": "event_id,icao24,event_time,ingest_time,latitude,longitude,baro_altitude"},
        "silver.dlq_events": {"owner": "Data Quality", "classification": "internal", "location": "data/silver/dlq_events", "schema": "event_id,reasons,raw_payload,quarantined_at"},
        "gold.airport_dimension": {"owner": "Analytics", "classification": "public", "location": "data/gold/airport_dimension", "schema": "icao_code,iata_code,country,latitude,longitude"},
        "gold.flight_delay_features": {"owner": "ML", "classification": "public", "location": "data/gold/flight_delay_features", "schema": "flight_record_id,distance_km,hour_of_day,day_of_week,month,dep_delay_min,taxi_out_min,crs_elapsed_min,arr_delay_min"},
        "gold.active_flights_mart": {"owner": "Analytics", "classification": "public", "location": "data/gold/active_flights_mart", "schema": "icao24,callsign,latitude,longitude,altitude_m,velocity_kmh,predicted_delay_min,last_updated"},
        "gold.airspace_density_mart": {"owner": "Analytics", "classification": "public", "location": "data/gold/airspace_density_mart", "schema": "origin_country,total_active_flights,avg_altitude_m,avg_velocity_kmh"},
        "gold.predictions": {"owner": "ML", "classification": "internal", "location": "data/gold/predictions.jsonl", "schema": "input_record_id,model_version,predicted_at,predicted_delay_min,status"},
    },
}


def ensure_catalog() -> dict[str, Any]:
    LINEAGE_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    if not CATALOG_FILE.exists():
        CATALOG_FILE.write_text(json.dumps(DEFAULT_CATALOG, indent=2), encoding="utf-8")
    return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))


def record_lineage(run_id: str, job: str, inputs: list[str], outputs: list[str],
                   row_counts: dict[str, int] | None = None, status: str = "SUCCESS",
                   consumers: list[str] | None = None) -> dict[str, Any]:
    """Record input dataset -> run/job -> output dataset -> consumer with run_id (F-09)."""
    ensure_catalog()
    record = {
        "run_id": run_id,
        "job": job,
        "inputs": inputs,
        "outputs": outputs,
        "consumers": consumers or ["fastapi-serving", "web-dashboard", "ml-training"],
        "row_counts": row_counts or {},
        "snapshots": {name: snapshot_info(DATA_DIR / name.split(".", 1)[-1].replace(".", "/"))
                      for name in outputs if name.startswith(("gold.", "silver."))},
        "status": status,
        "recorded_at": utcnow_iso(),
    }
    (RUNS_DIR / f"{run_id}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    append_jsonl(LINEAGE_FILE, record)
    return record


def get_run(run_id: str) -> dict[str, Any] | None:
    path = RUNS_DIR / f"{run_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    for row in reversed(read_jsonl(LINEAGE_FILE)):
        if row.get("run_id") == run_id:
            return row
    return None
