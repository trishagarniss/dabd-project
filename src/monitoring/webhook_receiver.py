"""Alertmanager webhook receiver: records trigger/resolve events for alert evidence (F-15)."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from src.common.config import EVIDENCE_DIR, utcnow_iso
from src.common.logging_utils import get_logger
from src.common.metrics import prometheus_text
from src.common.storage import append_jsonl, read_jsonl

log = get_logger("monitoring.webhook")
app = FastAPI(title="SkyPulse Alert Webhook Receiver", version="1.0.0")
HISTORY = EVIDENCE_DIR / "alerts" / "alert_history.jsonl"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "HEALTHY"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(content=prometheus_text(), media_type="text/plain; version=0.0.4; charset=utf-8")


@app.post("/alerts")
async def receive_alert(request: Request) -> JSONResponse:
    payload: dict[str, Any] = await request.json()
    for alert in payload.get("alerts", []):
        record = {
            "received_at": utcnow_iso(),
            "status": alert.get("status"),
            "alertname": alert.get("labels", {}).get("alertname"),
            "severity": alert.get("labels", {}).get("severity"),
            "owner": alert.get("labels", {}).get("owner"),
            "summary": alert.get("annotations", {}).get("summary"),
            "runbook": alert.get("annotations", {}).get("runbook"),
            "starts_at": alert.get("startsAt"),
            "ends_at": alert.get("endsAt"),
            "firing": str(alert.get("status")) == "firing",
        }
        append_jsonl(HISTORY, record)
        log.info("alert received", extra={"status": str(record["status"]).upper(),
                                           "job": record["alertname"], "error": record["summary"]})
    return JSONResponse({"received": len(payload.get("alerts", []))})


@app.get("/alerts/history")
def alert_history(limit: int = 100) -> dict[str, Any]:
    rows = read_jsonl(HISTORY)
    return {"count": min(limit, len(rows)), "alerts": rows[-limit:]}
