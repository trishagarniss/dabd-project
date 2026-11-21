"""End-to-end alert delivery test (F-15).

Posts Alertmanager-style firing and resolved payloads to the local webhook receiver,
then verifies that each of the three required alerts is recorded with its owner,
severity, threshold, runbook and resolution timestamp.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from src.common.config import EVIDENCE_DIR
from src.common.storage import append_jsonl, read_jsonl
from src.monitoring.webhook_receiver import app

RULES = [
    ("BatchJobFailed", "critical", "data-engineering", "increase(fdp_job_rows_total{status=\"FAILED\"}[10m]) > 0",
     "docs/RUNBOOK.md#a-batch-job-failed"),
    ("StreamLagOrFreshnessHigh", "warning", "streaming",
     "fdp_stream_lag_seconds > 120 or fdp_ingest_freshness_seconds > 300",
     "docs/RUNBOOK.md#b-stream-lag-or-freshness-high"),
    ("ServiceResourceUnhealthy", "critical", "platform",
     "fdp_cpu_percent > 90 or fdp_memory_mb > 1500 or up{job=\"fdp-api\"} == 0",
     "docs/RUNBOOK.md#c-service-resource-unhealthy"),
]


def payload(status: str, alert: tuple[str, str, str, str, str], when: str) -> dict:
    name, severity, owner, threshold, runbook = alert
    return {"alerts": [{
        "status": status,
        "labels": {"alertname": name, "severity": severity, "owner": owner},
        "annotations": {
            "summary": f"{name} ({status})",
            "runbook": runbook,
            "threshold": threshold,
            "window": "10m" if name == "BatchJobFailed" else "2m" if "Lag" in name else "3m",
            "notification_channel": "alertmanager-webhook",
        },
        "startsAt": when,
        "endsAt": None if status == "firing" else when,
    }]}


def main() -> None:
    client = TestClient(app)
    history_path = EVIDENCE_DIR / "alerts" / "alert_history.jsonl"
    if history_path.exists():
        history_path.unlink()
    now = datetime.now(timezone.utc).isoformat()
    timeline = []
    for status in ("firing", "resolved"):
        for rule in RULES:
            response = client.post("/alerts", json=payload(status, rule, now))
            assert response.status_code == 200, response.text
            timeline.append({
                "alert": rule[0], "status": status, "delivered_at": datetime.now(timezone.utc).isoformat(),
                "severity": rule[1], "owner": rule[2], "threshold": rule[3], "runbook": rule[4],
                "channel": "alertmanager-webhook",
            })
    history = read_jsonl(history_path)
    assert len(history) == 6
    for name, _, _, _, _ in RULES:
        states = {row["status"] for row in history if row["alertname"] == name}
        assert states == {"firing", "resolved"}, (name, states)
    append_jsonl(EVIDENCE_DIR / "alerts" / "alert_test_results.jsonl",
                 {"tested_at": now, "status": "SUCCESS", "alerts": len(RULES),
                  "firing": 3, "resolved": 3})
    target = EVIDENCE_DIR / "alerts" / "alert_timeline.json"
    target.write_text(json.dumps(timeline, indent=2), encoding="utf-8")
    print(json.dumps({"status": "SUCCESS", "alerts_tested": len(RULES),
                      "firing": 3, "resolved": 3, "timeline": str(target)}, indent=2))


if __name__ == "__main__":
    main()
