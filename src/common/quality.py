"""Configurable data-quality gate with quarantine, pass/fail report and publish block (F-08)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.common.config import BRONZE_DIR, CONFIG_DIR, EVIDENCE_DIR, QUALITY_THRESHOLD, SILVER_DIR, utcnow_iso

RULES_FILE = CONFIG_DIR / "quality_rules.json"
REPORT_DIR = EVIDENCE_DIR / "quality"


def load_rules() -> dict[str, Any]:
    if RULES_FILE.exists():
        return json.loads(RULES_FILE.read_text(encoding="utf-8"))
    return {"threshold_pass_ratio": QUALITY_THRESHOLD, "datasets": {}}


def validate_quality_gate(event: dict[str, Any]) -> tuple[bool, list[str]]:
    """Backward-compatible single-event gate used by the stream consumer and unit tests."""
    rules = load_rules().get("datasets", {}).get("flight_event", {})
    reasons: list[str] = []
    for column in rules.get("not_null", []):
        if event.get(column) is None:
            reasons.append(f"Missing {column}")
    for column, (low, high) in rules.get("range", {}).items():
        value = event.get(column)
        if value is not None and not (low <= float(value) <= high):
            reasons.append(f"Out of range {column}={value} expected [{low},{high}]")
    return len(reasons) == 0, reasons


def _cross_dataset_check(df: pd.DataFrame, name: str, known_airports: set[str] | None) -> list[str]:
    if name == "bts_ontime" and known_airports:
        bad = df[~df["origin"].isin(known_airports) | ~df["dest"].isin(known_airports)]
        return [f"cross_dataset_unknown_airport rows={len(bad)}"] if not bad.empty else []
    return []


def validate_dataframe(df: pd.DataFrame, dataset: str,
                       known_airports: set[str] | None = None) -> dict[str, Any]:
    """Run not-null, range, uniqueness and cross-dataset rules over a DataFrame."""
    rules = load_rules().get("datasets", {}).get(dataset, {})
    total = len(df)
    failed: dict[int, list[str]] = {}

    def mark(mask: pd.Series, reason: str) -> None:
        for idx in df.index[mask.fillna(False)]:
            failed.setdefault(int(idx), []).append(reason)

    for column in rules.get("not_null", []):
        if column in df.columns:
            mark(df[column].isna(), f"not_null:{column}")
    for column, (low, high) in rules.get("range", {}).items():
        if column in df.columns:
            numeric = pd.to_numeric(df[column], errors="coerce")
            mark((numeric < low) | (numeric > high), f"range:{column}")
    for column in rules.get("unique", []):
        if column in df.columns:
            mark(df.duplicated(subset=[column], keep="first"), f"unique:{column}")

    global_reasons = _cross_dataset_check(df, dataset, known_airports)
    passed = total - len(failed)

    report = {
        "dataset": dataset,
        "checked_at": utcnow_iso(),
        "total_records": total,
        "passed_records": passed,
        "failed_records": len(failed),
        "pass_ratio": round(passed / total, 4) if total else 1.0,
        "threshold": load_rules().get("threshold_pass_ratio", QUALITY_THRESHOLD),
        "failed_examples": [
            {"row_index": idx, "reasons": reasons,
             "record": df.loc[idx].to_dict()} for idx, reasons in list(failed.items())[:20]
        ],
        "cross_dataset_findings": global_reasons,
        "warnings": global_reasons,
        "status": "PASS",
    }
    # Cross-dataset findings are reported as warnings, not hard failures: reference
    # masters drift over time (e.g. airport IATA code renames), so they must be
    # visible in the quality report without blocking otherwise valid rows (F-08).
    report["status"] = "PASS" if report["pass_ratio"] >= report["threshold"] else "DEGRADED"

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    (REPORT_DIR / f"quality_report_{dataset}_{stamp}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    pd.DataFrame([
        {"dataset": dataset, "metric": k, "value": v}
        for k, v in report.items()
        if isinstance(v, (int, float, str))
    ]).to_csv(REPORT_DIR / f"quality_report_{dataset}_{stamp}.csv", index=False)

    if failed:
        quarantine = SILVER_DIR / "dlq_events"
        bad_df = df.loc[list(failed.keys())].copy()
        bad_df["dq_reasons"] = [";".join(r) for r in failed.values()]
        bad_df["quarantined_at"] = utcnow_iso()
        bad_df["dataset"] = dataset
        from src.common.storage import write_snapshot
        write_snapshot(bad_df, quarantine, description="Quarantined records from quality gate")
    return report


def enforce(report: dict[str, Any]) -> bool:
    """Return True when the dataset may be published to Gold; otherwise block/degrade."""
    return report["status"] == "PASS"
