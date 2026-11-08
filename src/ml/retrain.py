"""
Model Retraining Pipeline (F-11 & F-12)
Script untuk menjalankan siklus eksperimen komparasi (Baseline vs Retrained Candidate)
dan mencatat perbandingan performa kedua model.
"""

import json
from src.ml.train import run_training

def run_retrain_pipeline():
    print("==================================================")
    print("   FLIGHT DELAY ML RETRAINING PIPELINE (F-11)     ")
    print("==================================================")
    
    # Eksperimen 1: Model Baseline (v1)
    res_v1 = run_training(model_version="v1", model_type="baseline")
    
    # Eksperimen 2: Model Retrained Candidate (v2) dengan algoritma lebih kompleks
    res_v2 = run_training(model_version="v2", model_type="candidate")
    
    print("\n================== KOMPARASI HASIL EKSPERIMEN ==================")
    print(f"Model v1 (Baseline Ridge)       -> RMSE: {res_v1['metrics']['RMSE']} | MAE: {res_v1['metrics']['MAE']}")
    print(f"Model v2 (Retrained RF)         -> RMSE: {res_v2['metrics']['RMSE']} | MAE: {res_v2['metrics']['MAE']}")
    
    if res_v2['metrics']['RMSE'] < res_v1['metrics']['RMSE']:
        improvement = ((res_v1['metrics']['RMSE'] - res_v2['metrics']['RMSE']) / res_v1['metrics']['RMSE']) * 100
        print(f"\n[PROMOSI MODEL] Model v2 menunjukkan peningkatan performa {improvement:.2f}%!")
        print("Model v2 direkomendasikan untuk serving inference production.")
    print("================================================================")

if __name__ == "__main__":
    run_retrain_pipeline()
