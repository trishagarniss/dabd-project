"""Integration tests for replay/backfill/recovery and batch idempotency (F-13)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import src.streaming.stream_consumer as consumer
from src.common.storage import append_jsonl, read_jsonl, read_latest


def _event(event_id: str, lat: float = -6.2, seconds_ago: int = 5, icao24: str = "abc123") -> dict:
    now = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    return {
        "event_id": event_id,
        "icao24": icao24,
        "callsign": "TEST1",
        "origin_country": "Indonesia",
        "latitude": lat,
        "longitude": 106.8,
        "baro_altitude": 9000.0,
        "velocity": 220.0,
        "vertical_rate": 0.0,
        "event_time": now.isoformat(),
        "ingest_time": now.isoformat(),
    }


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(consumer, "DEDUP_DB", tmp_path / "dedup.sqlite3")
    monkeypatch.setattr(consumer, "DLQ_JSONL", tmp_path / "dlq.jsonl")
    monkeypatch.setattr(consumer, "SILVER_FLIGHTS", tmp_path / "silver_flights")
    monkeypatch.setattr(consumer, "GOLD_ACTIVE", tmp_path / "gold_active")
    monkeypatch.setattr(consumer, "GOLD_DENSITY", tmp_path / "gold_density")
    monkeypatch.setattr(consumer, "_buffer_valid", [])
    monkeypatch.setattr(consumer, "_buffer_invalid", [])
    return tmp_path


def test_bronze_replay_rebuilds_silver_and_gold(sandbox):
    source = sandbox / "bronze_events.jsonl"
    append_jsonl(source, [_event("it-1"), _event("it-2", lat=999.0), _event("it-3", icao24="def456")])

    first = consumer.replay_from_bronze(source)
    assert first["ACCEPTED"] == 2
    assert first["INVALID"] == 1
    assert first["flushed"]["accepted"] == 2
    assert first["flushed"]["dead_letter"] == 1
    assert len(read_latest(consumer.SILVER_FLIGHTS)) == 2
    assert len(read_latest(consumer.GOLD_ACTIVE)) == 2
    assert len(read_jsonl(consumer.DLQ_JSONL)) == 1


def test_second_replay_is_idempotent(sandbox):
    source = sandbox / "bronze_events.jsonl"
    append_jsonl(source, [_event("it-4"), _event("it-5")])

    first = consumer.replay_from_bronze(source)
    second = consumer.replay_from_bronze(source)
    assert first["ACCEPTED"] == 2
    assert second["DUPLICATE"] == 2
    assert second["ACCEPTED"] == 0
    assert second["flushed"]["accepted"] == 0
    assert len(read_latest(consumer.SILVER_FLIGHTS)) == 2


def test_replay_from_bronze_records_lineage(sandbox):
    source = sandbox / "bronze_events.jsonl"
    append_jsonl(source, [_event("it-6")])
    result = consumer.replay_from_bronze(source)
    assert result["source"] == str(source)
    runs = sandbox / "lineage_runs"
    # Lineage directory is global; verify run file exists via recorded run_id.
    from src.common.config import LINEAGE_DIR

    recorded = list((LINEAGE_DIR / "runs").glob("*.json"))
    assert recorded
    payload = json.loads(recorded[-1].read_text(encoding="utf-8"))
    assert payload["job"] == "stream_bronze_replay"


def test_late_event_is_quarantined(sandbox):
    source = sandbox / "late_events.jsonl"
    append_jsonl(source, [_event("it-late", seconds_ago=10_000)])
    result = consumer.replay_from_bronze(source)
    assert result["LATE"] == 1
    assert result["ACCEPTED"] == 0
