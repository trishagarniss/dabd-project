"""Retraining entry point (F-11): baseline vs candidate comparison and champion promotion."""
from __future__ import annotations

import json
from pathlib import Path

from src.common.config import EVIDENCE_DIR
from src.ml.train import run_retrain_all


def run_retrain_pipeline() -> dict:
    output = run_retrain_all()
    results = {row["model_version"]: row["metrics"] for row in output["experiments"]}
    baseline = results["v1"]["RMSE"]
    candidate = results["v2"]["RMSE"]
    improvement = ((baseline - candidate) / baseline * 100) if baseline else 0.0
    summary = {
        "baseline_rmse": baseline,
        "candidate_rmse": candidate,
        "improvement_pct": round(improvement, 2),
        "champion": output["champion"],
        "same_test_set_seed": 42,
    }
    target = EVIDENCE_DIR / "ml" / "comparison.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    run_retrain_pipeline()
