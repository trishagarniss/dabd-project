"""Shared configuration, paths and runtime context for SkyPulse Data Platform."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"
REFERENCE_DIR = DATA_DIR / "reference"
STATE_DIR = DATA_DIR / "state"
LINEAGE_DIR = DATA_DIR / "lineage"
DATA_GOLD_DIR = GOLD_DIR
EVIDENCE_DIR = ROOT / "evidence"
LOG_DIR = ROOT / "logs"
CONFIG_DIR = ROOT / "config"
ML_DIR = ROOT / "src" / "ml"

for _d in (BRONZE_DIR, SILVER_DIR, GOLD_DIR, REFERENCE_DIR, STATE_DIR,
           LINEAGE_DIR, EVIDENCE_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

SERVICE_NAME = os.getenv("FDP_SERVICE", "fdp")
RUN_ID = os.getenv("FDP_RUN_ID") or f"run-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:19092").split(",")
TOPIC_RAW = os.getenv("FDP_TOPIC_RAW", "flight-raw-stream")
TOPIC_DLQ = os.getenv("FDP_TOPIC_DLQ", "flight-stream-dlq")
CONSUMER_GROUP = os.getenv("FDP_CONSUMER_GROUP", "fdp-silver-consumer-v2")

ALLOWED_LATENESS_SEC = int(os.getenv("FDP_ALLOWED_LATENESS_SEC", "300"))
QUALITY_THRESHOLD = float(os.getenv("FDP_QUALITY_THRESHOLD", "0.95"))
MAX_SNAPSHOT_VERSIONS = max(1, int(os.getenv("FDP_MAX_SNAPSHOT_VERSIONS", "5")))
POLL_INTERVAL_SEC = int(os.getenv("FDP_POLL_INTERVAL_SEC", "15"))
OPENSKY_BBOX = [-11.0, 95.0, 6.0, 141.0]

API_KEYS_FILE = ROOT / ".env"
AUDIT_LOG = LOG_DIR / "audit.jsonl"
STRUCTURED_LOG = LOG_DIR / "structured.jsonl"
DEDUP_DB = STATE_DIR / "dedup.sqlite3"

OURAIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
BTS_URL = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2024_1.zip"
)
BTS_EXPECTED_SHA256 = "fe089b45523f9d4ac0ccd0e176a543d274e914ee5ae5bd384dbaafc7dc06ebfd"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
