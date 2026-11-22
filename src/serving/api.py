"""FastAPI serving layer: 10+ queryable endpoints, role-based auth, audit, ML inference (F-10, F-12, F-16)."""
from __future__ import annotations

import json
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.common.config import (
    API_KEYS_FILE, AUDIT_LOG, EVIDENCE_DIR, GOLD_DIR, REFERENCE_DIR, RUN_ID, utcnow_iso,
)
from src.common.lineage import get_run
from src.common.logging_utils import get_logger
from src.common.metrics import api_error, inference, prometheus_text, write_snapshot
from src.common.storage import append_jsonl, read_jsonl, read_latest, write_snapshot as persist_snapshot
from src.ml.prepare_features import FEATURES, dataset_version
from src.ml.tracking import get_runs

log = get_logger("serving.api")
app = FastAPI(title="SkyPulse Flight Data Platform API", version="2.0.0",
              description="Serving marts, data quality, lineage and ML inference for TBP DABD")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["x-api-key", "Content-Type"],
)

MODEL_PATH = Path(__file__).resolve().parents[1] / "ml" / "models" / "flight_delay_model_v2.pkl"
MODEL: Any = None
MODEL_FEATURES: list[str] = FEATURES
MODEL_VERSION = "v2_random_forest"
REGISTRY = GOLD_DIR / "model_registry.json"
PREDICTIONS = GOLD_DIR / "predictions.jsonl"


def _load_model() -> None:
    global MODEL, MODEL_FEATURES, MODEL_VERSION
    if REGISTRY.exists():
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        MODEL_VERSION = str(registry.get("champion", MODEL_VERSION))
        path = MODEL_PATH.parent / f"flight_delay_model_{MODEL_VERSION}.pkl"
    else:
        path = MODEL_PATH
    if not path.exists():
        return
    with path.open("rb") as fh:
        payload = pickle.load(fh)
    if isinstance(payload, dict) and "model" in payload:
        MODEL = payload["model"]
        MODEL_FEATURES = payload.get("features", FEATURES)
        MODEL_VERSION = payload.get("model_version", MODEL_VERSION)
    else:
        MODEL = payload
        MODEL_FEATURES = FEATURES


_load_model()


def _credentials() -> dict[str, str]:
    creds: dict[str, str] = {}
    for line in API_KEYS_FILE.read_text(encoding="utf-8").splitlines() if API_KEYS_FILE.exists() else []:
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.strip().split("=", 1)
            if key.startswith("FDP_API_KEY_"):
                creds[key.replace("FDP_API_KEY_", "").lower()] = value.strip().strip('"')
    import os
    for role in ("admin", "operator", "viewer"):
        env_value = os.getenv(f"FDP_API_KEY_{role.upper()}")
        if env_value:
            creds[role] = env_value
    return creds


ROLE_RANK = {"viewer": 0, "operator": 1, "admin": 2}


def _audit(endpoint: str, role: str | None, status: int, request: Request | None = None) -> None:
    append_jsonl(AUDIT_LOG, {
        "timestamp": utcnow_iso(), "endpoint": endpoint, "role": role, "status_code": status,
        "client": request.client.host if request and request.client else None,
        "run_id": RUN_ID,
    })


def require_role(needed: str = "viewer"):
    def dependency(request: Request) -> str:
        key = request.headers.get("x-api-key", "")
        creds = _credentials()
        role = next((name for name, value in creds.items() if value and value == key), None)
        if role is None:
            api_error(request.url.path, 401)
            _audit(request.url.path, None, 401, request)
            raise HTTPException(status_code=401, detail="Missing or invalid API key")
        if ROLE_RANK.get(role, -1) < ROLE_RANK[needed]:
            api_error(request.url.path, 403)
            _audit(request.url.path, role, 403, request)
            raise HTTPException(status_code=403, detail=f"Role '{role}' cannot perform this action")
        _audit(request.url.path, role, 200, request)
        return role
    return dependency


class DelayPredictionRequest(BaseModel):
    input_record_id: str = Field(..., min_length=1, example="FL_2024_001")
    distance_km: float = Field(..., ge=0, example=820.5)
    hour_of_day: int = Field(..., ge=0, le=23, example=14)
    day_of_week: int = Field(..., ge=0, le=6, example=2)
    month: int = Field(..., ge=1, le=12, example=1)
    dep_delay_min: float = Field(..., example=5.0)
    taxi_out_min: float = Field(..., ge=0, example=18.0)
    crs_elapsed_min: float = Field(..., ge=1, example=140.0)


class DelayPredictionResponse(BaseModel):
    input_record_id: str
    model_version: str
    predicted_at: str
    predicted_delay_min: float
    score: float
    status: str


@app.get("/api/v1/health", tags=["System"])
def health_check() -> dict[str, Any]:
    return {
        "status": "HEALTHY", "timestamp": utcnow_iso(), "run_id": RUN_ID,
        "model_loaded": MODEL is not None, "model_version": MODEL_VERSION,
        "dataset_version": dataset_version(),
    }


@app.get("/api/v1/flights/active", tags=["Serving Marts"])
def get_active_flights(limit: int = Query(20, ge=1, le=20000),
                       role: str = Depends(require_role("viewer"))) -> dict[str, Any]:
    frame = read_latest(GOLD_DIR / "active_flights_mart")
    return {"grain": "one row per icao24", "freshness": _freshness(frame),
            "count": len(frame), "returned": min(limit, len(frame)),
            "data": frame.head(limit).to_dict("records")}


@app.get("/api/v1/airports/{code}", tags=["Serving Marts"])
def get_airport_info(code: str, role: str = Depends(require_role("viewer"))) -> dict[str, Any]:
    path = REFERENCE_DIR / "airports_reference.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Airport reference not found")
    frame = pd.read_csv(path)
    match = frame[frame["ident"].astype(str).str.upper() == code.upper()]
    if match.empty and "iata_code" in frame:
        match = frame[frame["iata_code"].astype(str).str.upper() == code.upper()]
    if match.empty:
        raise HTTPException(status_code=404, detail=f"Airport '{code}' not found")
    return match.iloc[0].to_dict()


@app.get("/api/v1/marts/airspace-density", tags=["Serving Marts"])
def get_airspace_density(role: str = Depends(require_role("viewer"))) -> dict[str, Any]:
    frame = read_latest(GOLD_DIR / "airspace_density_mart")
    return {"grain": "one row per origin country", "count": len(frame), "data": frame.to_dict("records")}


@app.get("/api/v1/marts/airport-dimension", tags=["Serving Marts"])
def get_airport_dimension(limit: int = Query(20, ge=1, le=500),
                          role: str = Depends(require_role("viewer"))) -> dict[str, Any]:
    frame = read_latest(GOLD_DIR / "airport_dimension")
    return {"grain": "one row per icao_code", "count": len(frame),
            "returned": min(limit, len(frame)),
            "data": frame.head(limit).to_dict("records")}


@app.get("/api/v1/flights/by-date", tags=["Serving Marts"])
def get_flights_by_date(date: str = Query(..., description="YYYY-MM-DD"),
                        limit: int = Query(50, ge=1, le=500),
                        role: str = Depends(require_role("viewer"))) -> dict[str, Any]:
    try:
        parsed = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        api_error("/api/v1/flights/by-date", 400)
        raise HTTPException(status_code=400, detail="Invalid date format; expected YYYY-MM-DD")
    frame = read_latest(GOLD_DIR / "flight_delay_features")
    if not frame.empty and "flight_date" in frame:
        frame = frame[frame["flight_date"].astype(str).str.startswith(str(parsed))]
    return {"date": str(parsed), "grain": "one row per flight_record_id",
            "count": len(frame), "returned": min(limit, len(frame)),
            "data": frame.head(limit).to_dict("records")}


@app.get("/api/v1/flights/date-range", tags=["Serving Marts"])
def get_flights_by_date_range(
    start: str = Query(..., description="YYYY-MM-DD inclusive start"),
    end: str = Query(..., description="YYYY-MM-DD inclusive end"),
    limit: int = Query(100, ge=1, le=1000),
    role: str = Depends(require_role("viewer")),
) -> dict[str, Any]:
    """Reconciliation endpoint: same grain as config/serving_queries.sql Q10."""
    try:
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError:
        api_error("/api/v1/flights/date-range", 400)
        raise HTTPException(status_code=400, detail="Dates must use YYYY-MM-DD")
    if start_date > end_date:
        api_error("/api/v1/flights/date-range", 400)
        raise HTTPException(status_code=400, detail="start must be <= end")
    frame = read_latest(GOLD_DIR / "flight_delay_features")
    if not frame.empty and "flight_date" in frame:
        dates = pd.to_datetime(frame["flight_date"], errors="coerce").dt.date
        frame = frame[(dates >= start_date) & (dates <= end_date)]
    return {
        "grain": "one row per flight_record_id",
        "start": str(start_date),
        "end": str(end_date),
        "count": len(frame),
        "returned": min(limit, len(frame)),
        "avg_arr_delay_min": round(float(pd.to_numeric(
            frame["arr_delay_min"], errors="coerce").mean()), 2) if not frame.empty else None,
        "data": frame.head(limit).to_dict("records"),
    }


@app.get("/api/v1/quality/report", tags=["Governance"])
def get_quality_report(role: str = Depends(require_role("viewer"))) -> dict[str, Any]:
    folder = EVIDENCE_DIR / "quality"
    files = sorted(folder.glob("quality_report_*.json")) if folder.exists() else []
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in files[-20:]]
    return {"count": len(reports), "reports": reports}


@app.get("/api/v1/lineage/runs", tags=["Governance"])
def list_lineage_runs(limit: int = Query(20, ge=1, le=200),
                      role: str = Depends(require_role("viewer"))) -> dict[str, Any]:
    from src.common.lineage import LINEAGE_FILE
    from src.common.storage import read_jsonl
    rows = read_jsonl(LINEAGE_FILE)
    return {"count": min(limit, len(rows)), "runs": [row["run_id"] for row in rows[-limit:]]}


@app.get("/api/v1/lineage/{run_id}", tags=["Governance"])
def get_lineage(run_id: str, role: str = Depends(require_role("viewer"))) -> dict[str, Any]:
    record = get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No lineage found for run_id '{run_id}'")
    return record


@app.post("/api/v1/ml/predict-delay", response_model=DelayPredictionResponse, tags=["ML Inference"])
def predict_flight_delay(payload: DelayPredictionRequest,
                         role: str = Depends(require_role("operator"))) -> DelayPredictionResponse:
    if MODEL is None:
        inference("MODEL_UNAVAILABLE", MODEL_VERSION)
        raise HTTPException(status_code=503, detail="Model artifact is not loaded")
    row = pd.DataFrame(
        [[float(getattr(payload, feature)) for feature in MODEL_FEATURES]],
        columns=MODEL_FEATURES,
    )
    try:
        prediction = float(MODEL.predict(row)[0])
    except Exception as exc:
        inference("ERROR", MODEL_VERSION)
        write_snapshot("inference_error", {"error": str(exc), "run_id": RUN_ID, "input": payload.model_dump()})
        raise HTTPException(status_code=422, detail=f"Inference rejected: {exc}")

    result = DelayPredictionResponse(
        input_record_id=payload.input_record_id,
        model_version=MODEL_VERSION,
        predicted_at=utcnow_iso(),
        predicted_delay_min=round(max(0.0, prediction), 2),
        score=round(prediction, 4),
        status="SUCCESS",
    )
    record = result.model_dump()
    record["role"] = role
    append_jsonl(PREDICTIONS, record)
    persist_snapshot(__import__("pandas").DataFrame([record]), GOLD_DIR / "predictions",
                     keys=["input_record_id"], description="ML inference predictions")
    inference("SUCCESS", MODEL_VERSION)
    return result


@app.get("/api/v1/ml/experiments", tags=["ML Governance"])
def get_model_experiments(role: str = Depends(require_role("viewer"))) -> dict[str, Any]:
    runs = get_runs()
    if not runs:
        folder = Path(__file__).resolve().parents[1] / "ml" / "experiments"
        runs = [json.loads(p.read_text(encoding="utf-8")) for p in folder.glob("experiment_*.json")] if folder.exists() else []
    return {"count": len(runs), "experiments": runs,
            "champion": json.loads(REGISTRY.read_text()).get("champion") if REGISTRY.exists() else None}


@app.get("/api/v1/ml/predictions", tags=["ML Governance"])
def get_predictions(limit: int = Query(50, ge=1, le=500),
                    role: str = Depends(require_role("viewer"))) -> dict[str, Any]:
    rows = read_jsonl(PREDICTIONS)
    return {"count": len(rows), "returned": min(limit, len(rows)), "data": rows[-limit:]}


@app.get("/api/v1/metrics", response_class=PlainTextResponse, tags=["System"])
def get_metrics() -> PlainTextResponse:
    write_snapshot("scrape", {"run_id": RUN_ID, "at": utcnow_iso()})
    return PlainTextResponse(prometheus_text().decode("utf-8", errors="replace"),
                             media_type="text/plain; version=0.0.4")


def _freshness(frame: Any) -> str | None:
    if frame is None or frame.empty or "last_updated" not in frame.columns:
        return None
    try:
        newest = datetime.fromisoformat(str(frame["last_updated"].max()).replace("Z", "+00:00"))
        return f"{(datetime.now(newest.tzinfo) - newest).total_seconds():.0f}s"
    except Exception:
        return None
