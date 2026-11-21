"""Lightweight MLflow-equivalent experiment tracking: run_id, params, metrics, versions, artifacts (F-11)."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from src.common.config import EVIDENCE_DIR, ML_DIR, utcnow_iso

STORE = ML_DIR / "tracking_store"
INDEX = STORE / "index.jsonl"
REPORT = EVIDENCE_DIR / "ml" / "experiment_report.json"


def code_version() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(ML_DIR.parent.parent),
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except Exception:
        paths = [ML_DIR / "train.py", ML_DIR / "prepare_features.py"]
        digest = hashlib.sha256()
        for path in paths:
            if path.exists():
                digest.update(path.read_bytes())
        return "nogit-" + digest.hexdigest()[:10]


def log_run(run_id: str, model_version: str, model_type: str, hyperparams: dict[str, Any],
            metrics: dict[str, float], dataset_version: str, dataset_rows: int,
            split_seed: int, artifact_path: str, test_size: float = 0.2) -> dict[str, Any]:
    STORE.mkdir(parents=True, exist_ok=True)
    (STORE / "runs").mkdir(parents=True, exist_ok=True)
    record = {
        "run_id": run_id,
        "model_version": model_version,
        "model_type": model_type,
        "hyperparameters": hyperparams,
        "metrics": metrics,
        "dataset_version": dataset_version,
        "dataset_rows": dataset_rows,
        "split_seed": split_seed,
        "test_size": test_size,
        "code_version": code_version(),
        "artifact_path": str(Path(artifact_path).as_posix()),
        "logged_at": utcnow_iso(),
        "tracking_tool": "local-json-tracking-store (MLflow-equivalent)",
    }
    (STORE / "runs" / f"{run_id}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    with INDEX.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return record


def get_runs() -> list[dict[str, Any]]:
    if not INDEX.exists():
        return []
    seen: dict[str, dict[str, Any]] = {}
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            seen[row["run_id"]] = row
    return list(seen.values())


def write_report(records: list[dict[str, Any]], champion: str) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "generated_at": utcnow_iso(),
        "champion": champion,
        "experiments": records,
        "note": "Two experiments share an identical test set (seed 42); dataset/code/model versions recorded.",
    }, indent=2, ensure_ascii=False), encoding="utf-8")
