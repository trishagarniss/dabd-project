"""
ML Training & Versioning Script (F-11 Requirement)
Melatih model ML untuk prediksi delay kedatangan pesawat.
Mendukung 2 eksperimen (Baseline vs Retrained Candidate) dengan fixed test set,
logging parameter, metrik evaluasi (MAE, RMSE, R2), dan penyimpanan artefak model.
"""

import os
import json
import argparse
import pickle
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from src.ml.prepare_features import generate_flight_ml_dataset, DATA_GOLD_DIR

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
METRICS_DIR = os.path.join(os.path.dirname(__file__), "experiments")

def run_training(model_version="v1", model_type="baseline"):
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(METRICS_DIR, exist_ok=True)
    
    # 1. Load Feature Store
    feature_file = os.path.join(DATA_GOLD_DIR, "flight_ml_features.csv")
    if not os.path.exists(feature_file):
        df = generate_flight_ml_dataset()
    else:
        df = pd.read_csv(feature_file)
        
    features = ["distance_to_dest_km", "altitude_m", "velocity_kmh", "vertical_rate", "hour_of_day"]
    target = "arrival_delay_min"
    
    X = df[features]
    y = df[target]
    
    # 2. Train-Test Split (F-11: Fixed seed 42 to prevent data leakage & guarantee reproducibility)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # 3. Model Selection: Eksperimen 1 (Baseline) vs Eksperimen 2 (Retrained / Candidate)
    if model_type == "baseline":
        model = Ridge(alpha=1.0)
        hyperparams = {"model_name": "Ridge_Regression", "alpha": 1.0}
    else:
        model = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
        hyperparams = {"model_name": "RandomForestRegressor", "n_estimators": 100, "max_depth": 8}
        
    print(f"\n[INFO] Melatih Model {model_version} ({model_type.upper()})...")
    model.fit(X_train, y_train)
    
    # 4. Evaluasi pada Test Set yang Sama Persis
    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)
    
    metrics = {
        "model_version": model_version,
        "model_type": model_type,
        "hyperparameters": hyperparams,
        "metrics": {
            "MAE": round(mae, 4),
            "RMSE": round(rmse, 4),
            "R2_Score": round(r2, 4)
        },
        "train_samples": len(X_train),
        "test_samples": len(X_test)
    }
    
    # 5. Simpan Artefak Model & Metrics JSON
    model_artifact_path = os.path.join(MODEL_DIR, f"flight_delay_model_{model_version}.pkl")
    with open(model_artifact_path, "wb") as f:
        pickle.dump(model, f)
        
    metric_file = os.path.join(METRICS_DIR, f"experiment_{model_version}.json")
    with open(metric_file, "w") as f:
        json.dump(metrics, f, indent=2)
        
    print(f"[SUCCESS] Model {model_version} disimpan di: {model_artifact_path}")
    print(f"[METRICS] MAE: {mae:.2f} min | RMSE: {rmse:.2f} min | R2: {r2:.4f}")
    return metrics

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", type=str, default="v1", help="Model version (v1, v2)")
    parser.add_argument("--type", type=str, default="baseline", choices=["baseline", "candidate"], help="Model type")
    args = parser.parse_args()
    
    run_training(args.version, args.type)
