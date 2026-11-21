"""Multi-model training on the real Gold feature mart (F-11)."""
from __future__ import annotations

import json
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

from src.common.config import EVIDENCE_DIR, GOLD_DIR, utcnow_iso
from src.common.logging_utils import get_logger
from src.common.metrics import mark_model, measure_job
from src.ml.prepare_features import FEATURES, TARGET, dataset_version, generate_flight_ml_dataset
from src.ml.tracking import log_run

log = get_logger("ml.training")
MODEL_DIR = Path(__file__).resolve().parent / "models"
METRICS_DIR = Path(__file__).resolve().parent / "experiments"
REGISTRY = GOLD_DIR / "model_registry.json"
SEED = 42


def _build_model(model_type: str) -> tuple[Any, dict[str, Any]]:
    if model_type == "baseline":
        return Ridge(alpha=1.0), {"model_name": "Ridge_Regression", "alpha": 1.0}
    if model_type == "candidate_rf":
        return (RandomForestRegressor(n_estimators=100, max_depth=8, random_state=SEED),
                {"model_name": "RandomForestRegressor", "n_estimators": 100, "max_depth": 8})
    if model_type == "candidate_gbm":
        return (GradientBoostingRegressor(n_estimators=120, learning_rate=0.08, max_depth=5,
                                          random_state=SEED),
                {"model_name": "GradientBoostingRegressor", "n_estimators": 120,
                 "learning_rate": 0.08, "max_depth": 5})
    raise ValueError(f"Unknown model_type: {model_type}")


def run_training(model_version: str = "v1", model_type: str = "baseline") -> dict[str, Any]:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    frame = generate_flight_ml_dataset()
    x = frame[FEATURES]
    y = frame[TARGET]
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=SEED)

    model, hyperparams = _build_model(model_type)
    with measure_job(f"train_{model_version}") as meta:
        model.fit(x_train, y_train)
        prediction = model.predict(x_test)
        meta["rows"] = len(frame)

    metrics = {
        "MAE": round(float(mean_absolute_error(y_test, prediction)), 4),
        "RMSE": round(float(np.sqrt(mean_squared_error(y_test, prediction))), 4),
        "R2_Score": round(float(r2_score(y_test, prediction)), 4),
    }
    artifact = MODEL_DIR / f"flight_delay_model_{model_version}.pkl"
    with artifact.open("wb") as fh:
        pickle.dump({"model": model, "features": FEATURES,
                     "model_version": model_version, "trained_at": utcnow_iso()}, fh)

    result = {
        "model_version": model_version,
        "model_type": model_type,
        "hyperparameters": hyperparams,
        "metrics": metrics,
        "train_samples": len(x_train),
        "test_samples": len(x_test),
        "features": FEATURES,
        "target": TARGET,
        "dataset_version": dataset_version(),
        "dataset_rows": len(frame),
        "split_seed": SEED,
    }
    (METRICS_DIR / f"experiment_{model_version}.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    log_run(f"run-{model_version}", model_version, model_type, hyperparams, metrics,
            result["dataset_version"], len(frame), SEED, str(artifact))
    log.info("model trained", extra={"job": "train", "status": "SUCCESS",
                                     "model_version": model_version, "rows": len(frame)})
    return result


def promote_champion(results: list[dict[str, Any]]) -> str:
    best = min(results, key=lambda item: item["metrics"]["RMSE"])
    registry = {
        "champion": best["model_version"],
        "model_type": best["model_type"],
        "rmse": best["metrics"]["RMSE"],
        "features": FEATURES,
        "dataset_version": best["dataset_version"],
        "promoted_at": utcnow_iso(),
    }
    REGISTRY.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    mark_model(best["model_version"])
    (EVIDENCE_DIR / "ml").mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "ml" / "model_registry.json").write_text(json.dumps(registry, indent=2), encoding="utf-8")
    return best["model_version"]


def run_retrain_all() -> dict[str, Any]:
    results = [run_training("v1", "baseline"), run_training("v2", "candidate_rf"),
               run_training("v3", "candidate_gbm")]
    champion = promote_champion(results)
    from src.ml.tracking import write_report
    write_report(results, champion)
    return {"champion": champion, "experiments": results}


if __name__ == "__main__":
    output = run_retrain_all()
    print(json.dumps({"champion": output["champion"],
                      "results": [(r["model_version"], r["metrics"]) for r in output["experiments"]]},
                     indent=2))
