"""
FastAPI Serving & ML Online/Batch Inference Layer (F-10 & F-12)
Menyediakan minimal 3 API read-only dan query ke Gold Marts:
1. GET /api/v1/health (Health check F-01)
2. GET /api/v1/flights/active (Mart penerbangan aktif)
3. GET /api/v1/airports/{iata_or_icao} (Query mart bandara)
4. POST /api/v1/ml/predict-delay (Inference ML F-12: score, model_version, predicted_at, error handling)
5. GET /api/v1/ml/experiments (Komparasi versi eksperimen F-11)
"""

import os
import json
import pickle
import pandas as pd
from typing import Optional
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

app = FastAPI(
    title="Flight Data Platform Serving API",
    description="Serving Layer untuk Flight Telemetry Marts & ML Inference Engine (TBP DABD)",
    version="1.0.0"
)

# Load Model v2 (Production Champion)
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "ml", "models", "flight_delay_model_v2.pkl")
MODEL = None
if os.path.exists(MODEL_PATH):
    with open(MODEL_PATH, "rb") as f:
        MODEL = pickle.load(f)

# Request & Response Schemas (F-12 Requirement)
class DelayPredictionRequest(BaseModel):
    input_record_id: str = Field(..., example="FL_00123")
    distance_to_dest_km: float = Field(..., ge=0, example=250.5)
    altitude_m: float = Field(..., ge=0, example=9500.0)
    velocity_kmh: float = Field(..., ge=0, example=720.0)
    vertical_rate: float = Field(..., example=-2.5)
    hour_of_day: int = Field(..., ge=0, le=23, example=14)

class DelayPredictionResponse(BaseModel):
    input_record_id: str
    model_version: str
    predicted_at: str
    predicted_delay_min: float
    status: str

# 1. Healthcheck Endpoint (F-01)
@app.get("/api/v1/health", tags=["System"])
def health_check():
    return {
        "status": "HEALTHY",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_loaded": MODEL is not None
    }

# 2. Mart 1: Active Flights (F-10)
@app.get("/api/v1/flights/active", tags=["Serving Marts"])
def get_active_flights(limit: int = Query(20, ge=1, le=100)):
    # Fallback/mock dari gold features jika database belum dihubungkan
    features_file = os.path.join(os.path.dirname(__file__), "..", "..", "data", "gold", "flight_ml_features.csv")
    if os.path.exists(features_file):
        df = pd.read_csv(features_file).head(limit)
        return {"count": len(df), "data": df.to_dict(orient="records")}
    return {"count": 0, "data": []}

# 3. Mart 2: Detail Bandara (F-10)
@app.get("/api/v1/airports/{code}", tags=["Serving Marts"])
def get_airport_info(code: str):
    airports_file = os.path.join(os.path.dirname(__file__), "..", "..", "data", "reference", "airports_reference.csv")
    if not os.path.exists(airports_file):
        raise HTTPException(status_code=404, detail="Airport database not found.")
    
    df = pd.read_csv(airports_file)
    res = df[(df["ident"].str.upper() == code.upper()) | (df["iata_code"].str.upper() == code.upper())]
    if res.empty:
        raise HTTPException(status_code=404, detail=f"Bandara dengan kode '{code}' tidak ditemukan.")
    return res.iloc[0].to_dict()

# 4. ML Inference API (F-12)
@app.post("/api/v1/ml/predict-delay", response_model=DelayPredictionResponse, tags=["ML Inference"])
def predict_flight_delay(payload: DelayPredictionRequest):
    if MODEL is None:
        raise HTTPException(status_code=503, detail="Model ML belum dimuat.")
    
    # Feature array
    input_data = [[
        payload.distance_to_dest_km,
        payload.altitude_m,
        payload.velocity_kmh,
        payload.vertical_rate,
        payload.hour_of_day
    ]]
    
    try:
        prediction = float(MODEL.predict(input_data)[0])
        predicted_delay = max(0.0, round(prediction, 2))
        
        return DelayPredictionResponse(
            input_record_id=payload.input_record_id,
            model_version="v2_random_forest",
            predicted_at=datetime.now(timezone.utc).isoformat(),
            predicted_delay_min=predicted_delay,
            status="SUCCESS"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")

# 5. MLflow / Experiments Tracker (F-11)
@app.get("/api/v1/ml/experiments", tags=["ML Governance"])
def get_model_experiments():
    exp_dir = os.path.join(os.path.dirname(__file__), "..", "ml", "experiments")
    if not os.path.exists(exp_dir):
        return {"experiments": []}
    
    results = []
    for f in os.listdir(exp_dir):
        if f.endswith(".json"):
            with open(os.path.join(exp_dir, f), "r") as json_f:
                results.append(json.load(json_f))
    return {"experiments": results}
