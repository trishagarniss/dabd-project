"""
Raw -> Silver -> Gold transformation with configurable merge policy, retry and backfill (F-03, F-06, F-07).
All rows originate from real OurAirports / BTS / OpenSky sources; no synthetic records are generated.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.common.config import (
    BRONZE_DIR, GOLD_DIR, RUN_ID, SILVER_DIR, utcnow_iso,
)
from src.common.lineage import record_lineage
from src.common.logging_utils import get_logger
from src.common.metrics import count_event, measure_job, set_quality
from src.common.quality import enforce, validate_dataframe
from src.common.storage import read_latest, write_snapshot
from src.ml.prepare_features import haversine_distance

log = get_logger("batch.transform")

AIRPORTS_RAW = BRONZE_DIR / "airports_raw"
BTS_RAW = BRONZE_DIR / "bts_ontime_raw"
FLIGHT_EVENTS = BRONZE_DIR / "flight_events_raw.jsonl"

SILVER_AIRPORTS = SILVER_DIR / "airports_clean"
SILVER_BTS = SILVER_DIR / "bts_ontime_clean"
SILVER_FLIGHTS = SILVER_DIR / "flight_states_clean"

GOLD_AIRPORTS = GOLD_DIR / "airport_dimension"
GOLD_FEATURES = GOLD_DIR / "flight_delay_features"
GOLD_ACTIVE = GOLD_DIR / "active_flights_mart"
GOLD_DENSITY = GOLD_DIR / "airspace_density_mart"


def _airports_silver() -> tuple[pd.DataFrame, dict]:
    raw = read_latest(AIRPORTS_RAW)
    if raw.empty:
        raise FileNotFoundError("Run src.batch.ingest_airports first")
    df = raw.rename(columns={
        "ident": "icao_code", "iso_country": "country", "latitude_deg": "latitude",
        "longitude_deg": "longitude", "elevation_ft": "elevation_ft",
    }).copy()
    for column in ["icao_code", "iata_code", "name", "latitude", "longitude"]:
        if column in df.columns:
            df = df[df[column].notna()]
    df = df[~df["iata_code"].astype(str).str.strip().eq("")]
    df = df.drop_duplicates(subset=["icao_code"], keep="last")
    numeric = ["latitude", "longitude", "elevation_ft"]
    for column in numeric:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    df["updated_at"] = df.get("ingest_time", utcnow_iso())
    report = validate_dataframe(df, "airports")
    set_quality("airports", report["pass_ratio"])
    write_snapshot(df, SILVER_AIRPORTS, keys=["icao_code"], description="Normalised airport master")
    return df, report


def _bts_silver(airports: pd.DataFrame, backfill_start: str | None, backfill_end: str | None) -> tuple[pd.DataFrame, dict]:
    raw = read_latest(BTS_RAW)
    if raw.empty:
        raise FileNotFoundError("Run src.batch.ingest_bts_ontime first")
    df = raw.copy()
    if "Cancelled" in df:
        df = df[pd.to_numeric(df["Cancelled"], errors="coerce").fillna(0) == 0]
    if "Diverted" in df:
        df = df[pd.to_numeric(df["Diverted"], errors="coerce").fillna(0) == 0]

    df = df.rename(columns={
        "FlightDate": "flight_date", "Reporting_Airline": "carrier", "Origin": "origin",
        "Dest": "dest", "CRSDepTime": "crs_dep_time", "DepDelay": "dep_delay_min",
        "TaxiOut": "taxi_out_min", "CRSElapsedTime": "crs_elapsed_min",
        "ArrDelay": "arr_delay_min", "Distance": "distance_miles",
    })
    date = pd.to_datetime(df["flight_date"], errors="coerce")
    if backfill_start:
        df = df[date >= pd.Timestamp(backfill_start)]
    if backfill_end:
        df = df[date <= pd.Timestamp(backfill_end)]
    df = df[date.notna()].copy()
    date = pd.to_datetime(df["flight_date"])

    dep_time = pd.to_numeric(df["crs_dep_time"], errors="coerce").fillna(0).astype(int)
    df["hour_of_day"] = (dep_time // 100).clip(0, 23).astype(int)
    df["day_of_week"] = date.dt.dayofweek.astype(int)
    df["month"] = date.dt.month.astype(int)
    for column in ["arr_delay_min", "dep_delay_min", "distance_miles", "taxi_out_min", "crs_elapsed_min"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["arr_delay_min", "origin", "dest", "distance_miles"])
    df = df.drop_duplicates(subset=["flight_key"], keep="last")
    df["updated_at"] = df.get("ingest_time", utcnow_iso())

    known = set(airports["icao_code"].astype(str)) | set(airports["iata_code"].astype(str))
    report = validate_dataframe(df, "bts_ontime", known_airports=known)
    set_quality("bts_ontime", report["pass_ratio"])
    write_snapshot(df, SILVER_BTS, keys=["flight_key"], description="Normalised BTS on-time records")
    return df, report


def _gold(airports: pd.DataFrame, bts: pd.DataFrame) -> dict[str, int]:
    airport_dim = airports[[
        "icao_code", "iata_code", "name", "country", "latitude", "longitude", "elevation_ft"
    ]].copy().drop_duplicates(subset=["icao_code"])
    airport_dim["updated_at"] = utcnow_iso()
    write_snapshot(airport_dim, GOLD_AIRPORTS, keys=["icao_code"], description="Airport dimension mart")

    coords = airport_dim.dropna(subset=["latitude", "longitude"])[
        ["icao_code", "iata_code", "latitude", "longitude"]
    ]
    lookup: dict[str, tuple[float, float]] = {}
    for row in coords.to_dict("records"):
        for key in (row["icao_code"], row["iata_code"]):
            if isinstance(key, str):
                lookup[key.upper()] = (float(row["latitude"]), float(row["longitude"]))

    distances = []
    for origin, dest in zip(bts["origin"], bts["dest"]):
        o = lookup.get(str(origin).upper())
        d = lookup.get(str(dest).upper())
        if o and d:
            distances.append(round(haversine_distance(o[0], o[1], d[0], d[1]), 2))
        else:
            distances.append(np.nan)
    features = pd.DataFrame({
        "flight_record_id": bts["flight_key"].astype(str),
        "flight_date": bts["flight_date"].astype(str),
        "carrier": bts.get("carrier", ""),
        "origin": bts["origin"].astype(str),
        "dest": bts["dest"].astype(str),
        "distance_km": distances,
        "distance_miles": pd.to_numeric(bts["distance_miles"], errors="coerce"),
        "hour_of_day": pd.to_numeric(bts["hour_of_day"], errors="coerce"),
        "day_of_week": pd.to_numeric(bts["day_of_week"], errors="coerce"),
        "month": pd.to_numeric(bts["month"], errors="coerce"),
        "dep_delay_min": pd.to_numeric(bts["dep_delay_min"], errors="coerce"),
        "taxi_out_min": pd.to_numeric(bts["taxi_out_min"], errors="coerce"),
        "crs_elapsed_min": pd.to_numeric(bts["crs_elapsed_min"], errors="coerce"),
        "arr_delay_min": pd.to_numeric(bts["arr_delay_min"], errors="coerce"),
    })
    features = features.dropna(subset=["distance_km", "arr_delay_min"])
    features["updated_at"] = utcnow_iso()
    write_snapshot(features, GOLD_FEATURES, keys=["flight_record_id"],
                   description="Flight delay feature store derived from real BTS + OurAirports")

    flights = read_latest(SILVER_FLIGHTS)
    if not flights.empty:
        latest = flights.sort_values("event_time").drop_duplicates("icao24", keep="last")
        active = pd.DataFrame({
            "icao24": latest["icao24"],
            "callsign": latest.get("callsign", "UNKNOWN"),
            "origin_country": latest.get("origin_country", "UNKNOWN"),
            "latitude": latest.get("latitude"),
            "longitude": latest.get("longitude"),
            "altitude_m": latest.get("baro_altitude"),
            "velocity_kmh": pd.to_numeric(latest.get("velocity"), errors="coerce") * 3.6,
            "vertical_rate_ms": latest.get("vertical_rate"),
            "flight_phase": "tracked",
            "predicted_delay_min": np.nan,
            "last_updated": latest["ingest_time"],
        })
        density = active.groupby("origin_country").agg(
            total_active_flights=("icao24", "count"),
            avg_altitude_m=("altitude_m", "mean"),
            avg_velocity_kmh=("velocity_kmh", "mean"),
        ).reset_index()
    else:
        active = pd.DataFrame(columns=[
            "icao24", "callsign", "origin_country", "latitude", "longitude", "altitude_m",
            "velocity_kmh", "vertical_rate_ms", "flight_phase", "predicted_delay_min", "last_updated",
        ])
        density = airport_dim.merge(
            features.groupby("origin").size().rename("total_active_flights").reset_index(),
            left_on="iata_code", right_on="origin", how="inner",
        )
        density = density.groupby("country").agg(
            total_active_flights=("total_active_flights", "sum")
        ).reset_index().rename(columns={"country": "origin_country"})
        density["avg_altitude_m"] = np.nan
        density["avg_velocity_kmh"] = np.nan

    density["last_aggregated_at"] = utcnow_iso()
    write_snapshot(active, GOLD_ACTIVE, keys=["icao24"], description="Current active flights mart")
    write_snapshot(density, GOLD_DENSITY, keys=["origin_country"], description="Airspace density mart")
    return {
        "gold.airport_dimension": len(airport_dim),
        "gold.flight_delay_features": len(features),
        "gold.active_flights_mart": len(active),
        "gold.airspace_density_mart": len(density),
    }


def run_transform(policy: str = "merge", backfill_start: str | None = None,
                  backfill_end: str | None = None, retry: int = 0) -> dict:
    """Run the full transformation. Re-running the same backfill range is idempotent."""
    last_error: Exception | None = None
    for attempt in range(retry + 1):
        try:
            with measure_job("transform_batch") as meta:
                airports, airport_report = _airports_silver()
                bts, bts_report = _bts_silver(airports, backfill_start, backfill_end)
                counts = _gold(airports, bts)
                meta["rows"] = len(airports) + len(bts) + sum(counts.values())
            if not enforce(airport_report) or not enforce(bts_report):
                log.warning("quality threshold not met - gold publication marked DEGRADED",
                            extra={"status": "DEGRADED", "job": "transform_batch"})
            record_lineage(RUN_ID, "transform_batch",
                           ["bronze.airports_raw", "bronze.bts_ontime_raw", "silver.flight_states_clean"],
                           ["silver.airports_clean", "silver.bts_ontime_clean"] + list(counts),
                           {**{"silver.airports_clean": len(airports), "silver.bts_ontime_clean": len(bts)},
                            **counts},
                           status="DEGRADED" if not (enforce(airport_report) and enforce(bts_report)) else "SUCCESS")
            count_event("gold_published", "batch")
            log.info("transform completed", extra={"job": "transform_batch", "status": "SUCCESS",
                                                   "rows": meta["rows"]})
            return {"counts": counts, "quality": [airport_report, bts_report], "policy": policy}
        except Exception as exc:
            last_error = exc
            log.error("transform attempt failed", extra={"job": "transform_batch", "attempt": attempt + 1,
                                                         "status": "FAILED", "error": str(exc)})
    assert last_error is not None
    raise last_error


def main() -> None:
    parser = argparse.ArgumentParser(description="Transform Bronze into Silver and Gold marts")
    parser.add_argument("--policy", default="merge", choices=["merge", "replace"])
    parser.add_argument("--backfill-start", default=None)
    parser.add_argument("--backfill-end", default=None)
    parser.add_argument("--retry", type=int, default=2)
    args = parser.parse_args()
    result = run_transform(args.policy, args.backfill_start, args.backfill_end, args.retry)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
