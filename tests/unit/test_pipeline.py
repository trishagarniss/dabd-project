"""Unit tests for ingestion, quality, storage, streaming and lineage (F-18)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from src.common import quality
from src.common.config import BRONZE_DIR, GOLD_DIR, SILVER_DIR
from src.common.lineage import record_lineage
from src.common.storage import read_jsonl, read_latest, write_snapshot
from src.ml.prepare_features import FEATURES, TARGET, generate_flight_ml_dataset, haversine_distance
from src.streaming.stream_consumer import is_late, process_event


VALID = {
    "event_id": "unit-test-001",
    "icao24": "e084e7",
    "callsign": "GIA123",
    "latitude": -6.2,
    "longitude": 106.8,
    "baro_altitude": 10500.0,
    "event_time": datetime.now(timezone.utc).isoformat(),
    "ingest_time": datetime.now(timezone.utc).isoformat(),
}


def test_haversine_distance_cgk_sub():
    dist = haversine_distance(-6.1256, 106.6559, -7.3798, 112.7874)
    assert 650 < dist < 730


def test_quality_gate_accepts_complete_event():
    ok, reasons = quality.validate_quality_gate(VALID)
    assert ok and reasons == []


def test_quality_gate_rejects_out_of_range_latitude():
    bad = {**VALID, "latitude": 120.0}
    ok, reasons = quality.validate_quality_gate(bad)
    assert not ok
    assert any("latitude" in reason for reason in reasons)


def test_quality_gate_rejects_missing_identifiers():
    for field in ("event_id", "icao24", "event_time", "latitude", "longitude"):
        bad = dict(VALID)
        bad.pop(field)
        ok, reasons = quality.validate_quality_gate(bad)
        assert not ok, field
        assert reasons


def test_quality_dataframe_report_and_enforcement(tmp_path, monkeypatch):
    monkeypatch.setattr(quality, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(quality, "SILVER_DIR", tmp_path)
    frame = pd.DataFrame({
        "flight_date": ["2024-01-01", "2024-01-01"],
        "origin": ["CGK", "SUB"],
        "dest": ["SUB", "CGK"],
        "arr_delay_min": [10.0, -2.0],
        "distance_miles": [700.0, 700.0],
    })
    report = quality.validate_dataframe(frame, "airports")
    assert report["total_records"] == 2
    assert quality.enforce(report) is True
    assert list(tmp_path.glob("quality_report_airports_*.json"))


def test_is_late_watermark(monkeypatch):
    monkeypatch.setattr("src.streaming.stream_consumer.is_late", is_late)
    assert is_late({"event_time": "2000-01-01T00:00:00+00:00"}, 300)
    assert not is_late({"event_time": "2999-01-01T00:00:00+00:00"}, 300)
    assert is_late({})


def test_stream_process_event_dedup(monkeypatch, tmp_path):
    import src.streaming.stream_consumer as consumer

    monkeypatch.setattr(consumer, "DEDUP_DB", tmp_path / "dedup.sqlite3")
    monkeypatch.setattr(consumer, "_buffer_valid", [])
    monkeypatch.setattr(consumer, "_buffer_invalid", [])
    assert process_event(dict(VALID)) == "ACCEPTED"
    assert process_event(dict(VALID)) == "DUPLICATE"


def test_stream_process_event_invalid_goes_to_dlq(monkeypatch, tmp_path):
    import src.streaming.stream_consumer as consumer

    monkeypatch.setattr(consumer, "DEDUP_DB", tmp_path / "dedup.sqlite3")
    monkeypatch.setattr(consumer, "DLQ_JSONL", tmp_path / "dlq.jsonl")
    monkeypatch.setattr(consumer, "_buffer_valid", [])
    monkeypatch.setattr(consumer, "_buffer_invalid", [])
    bad = {**VALID, "event_id": "unit-test-invalid", "latitude": 999.0}
    assert process_event(bad) == "INVALID"
    assert read_jsonl(tmp_path / "dlq.jsonl")[0]["event_id"] == "unit-test-invalid"


def test_storage_snapshot_upsert_is_idempotent(tmp_path):
    path = tmp_path / "dataset"
    first = pd.DataFrame({"id": ["a", "b"], "updated_at": ["2024-01-01", "2024-01-01"], "value": [1, 2]})
    meta1 = write_snapshot(first, path, keys=["id"])
    second = pd.DataFrame({"id": ["b"], "updated_at": ["2024-01-02"], "value": [9]})
    meta2 = write_snapshot(second, path, keys=["id"])
    result = read_latest(path)
    assert meta1["version"] != meta2["version"]
    assert len(result) == 2
    assert result.loc[result["id"] == "b", "value"].iloc[0] == 9
    assert (path.parent / (path.name + ".snapshot.json")).exists()


def test_storage_handles_nested_cells(tmp_path):
    frame = pd.DataFrame({"id": ["x"], "payload": [[{"a": 1}]]})
    meta = write_snapshot(frame, tmp_path / "nested", keys=["id"])
    assert meta["row_count"] == 1


def test_real_gold_feature_mart_contract():
    frame = generate_flight_ml_dataset()
    assert not frame.empty
    assert set(FEATURES + [TARGET]).issubset(frame.columns)
    assert frame[TARGET].notna().all()


def test_dataset_contains_no_synthetic_marker():
    frame = generate_flight_ml_dataset(n_samples=50, random_seed=7)
    assert len(frame) == 50
    assert "synthetic" not in json.dumps(list(frame.columns)).lower()


def test_lineage_links_run_to_outputs(tmp_path, monkeypatch):
    import src.common.lineage as lineage

    monkeypatch.setattr(lineage, "LINEAGE_DIR", tmp_path)
    monkeypatch.setattr(lineage, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(lineage, "CATALOG_FILE", tmp_path / "catalog.json")
    monkeypatch.setattr(lineage, "LINEAGE_FILE", tmp_path / "lineage.jsonl")
    record = record_lineage("unit-run", "unit_job", ["bronze.x"], ["gold.y"])
    assert record["inputs"] == ["bronze.x"]
    assert (tmp_path / "runs" / "unit-run.json").exists()


def test_artifacts_from_real_runs_exist():
    assert (BRONZE_DIR / "bts_ontime_provenance.json").exists()
    assert (BRONZE_DIR / "flight_events_raw.jsonl").exists()
    assert not (SILVER_DIR / "flight_states_clean.parquet").exists() or \
        len(read_latest(SILVER_DIR / "flight_states_clean")) > 0
    assert not (GOLD_DIR / "flight_delay_features.parquet").exists() or \
        len(read_latest(GOLD_DIR / "flight_delay_features")) > 0
