"""Stream consumer with durable dedup, event-time lateness policy, quality gate and DLQ (F-04, F-05, F-08)."""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.common.config import (
    ALLOWED_LATENESS_SEC, BRONZE_DIR, CONSUMER_GROUP, DEDUP_DB, GOLD_DIR,
    KAFKA_BOOTSTRAP, SILVER_DIR, STATE_DIR, TOPIC_RAW, RUN_ID, utcnow_iso,
)
from src.common.lineage import record_lineage
from src.common.logging_utils import get_logger
from src.common.metrics import count_event, measure_job, set_freshness, set_lag
from src.common.quality import validate_quality_gate
from src.common.storage import append_jsonl, read_jsonl, write_snapshot

log = get_logger("stream.consumer")
DLQ_JSONL = SILVER_DIR / "dlq_events.jsonl"
SILVER_FLIGHTS = SILVER_DIR / "flight_states_clean"
GOLD_ACTIVE = GOLD_DIR / "active_flights_mart"
GOLD_DENSITY = GOLD_DIR / "airspace_density_mart"
OFFSET_STATE = STATE_DIR / "consumer_offsets.json"
RAW_EVENTS = BRONZE_DIR / "flight_events_raw.jsonl"

_buffer_valid: list[dict[str, Any]] = []
_buffer_invalid: list[dict[str, Any]] = []
FLUSH_EVERY = 20


def _dedup_db() -> sqlite3.Connection:
    DEDUP_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DEDUP_DB)
    conn.execute("CREATE TABLE IF NOT EXISTS seen_events (event_id TEXT PRIMARY KEY, processed_at TEXT)")
    conn.commit()
    return conn


def is_duplicate(event_id: str) -> bool:
    """Durable dedup: survives consumer restarts (F-05)."""
    with _dedup_db() as conn:
        existing = conn.execute("SELECT 1 FROM seen_events WHERE event_id=?", (event_id,)).fetchone()
        if existing:
            return True
        conn.execute("INSERT INTO seen_events (event_id, processed_at) VALUES (?, ?)",
                     (event_id, utcnow_iso()))
    return False


def is_late(event: dict[str, Any], allowed_lateness_sec: int = ALLOWED_LATENESS_SEC) -> bool:
    """Watermark policy: events older than now - allowed lateness are rejected to DLQ."""
    value = event.get("event_time")
    if not value:
        return True
    try:
        event_time = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)
        watermark = datetime.now(timezone.utc) - timedelta(seconds=allowed_lateness_sec)
        return event_time < watermark
    except ValueError:
        return True


def _dead_letter(event: dict[str, Any], reasons: list[str]) -> None:
    record = {
        "event_id": event.get("event_id"),
        "reasons": reasons,
        "raw_payload": event,
        "quarantined_at": utcnow_iso(),
        "run_id": RUN_ID,
    }
    _buffer_invalid.append(record)
    append_jsonl(DLQ_JSONL, record)
    count_event("dlq", "consumer")


def process_event(event: dict[str, Any]) -> str:
    """Validate one event. Returns ACCEPTED, DUPLICATE, INVALID or LATE."""
    event_id = event.get("event_id")
    if not event_id:
        _dead_letter(event, ["Missing event_id"])
        return "INVALID"
    if is_duplicate(event_id):
        count_event("duplicate", "consumer")
        return "DUPLICATE"
    valid, reasons = validate_quality_gate(event)
    if not valid:
        _dead_letter(event, reasons)
        return "INVALID"
    if is_late(event):
        _dead_letter(event, [f"late_event beyond allowed lateness {ALLOWED_LATENESS_SEC}s"])
        return "LATE"

    event["silver_ingest_time"] = utcnow_iso()
    event["processed_by_run"] = RUN_ID
    _buffer_valid.append(event)
    count_event("accepted", "consumer")
    return "ACCEPTED"


def flush() -> dict[str, int]:
    """Persist buffered events into Silver and recompute Gold marts."""
    global _buffer_valid, _buffer_invalid
    if not _buffer_valid and not _buffer_invalid:
        return {"accepted": 0, "dead_letter": 0}

    accepted, rejected = _buffer_valid, _buffer_invalid
    _buffer_valid, _buffer_invalid = [], []
    with measure_job("stream_flush") as meta:
        if accepted:
            frame = pd.DataFrame(accepted)
            write_snapshot(frame, SILVER_FLIGHTS, keys=["event_id"],
                           description="Validated flight telemetry (Silver)")
            latest = frame.sort_values("event_time").drop_duplicates("icao24", keep="last")
            active = pd.DataFrame({
                "icao24": latest["icao24"],
                "callsign": latest.get("callsign", "UNKNOWN"),
                "origin_country": latest.get("origin_country", "UNKNOWN"),
                "latitude": latest.get("latitude"),
                "longitude": latest.get("longitude"),
                "altitude_m": latest.get("baro_altitude"),
                "velocity_kmh": pd.to_numeric(latest.get("velocity"), errors="coerce") * 3.6,
                "true_track_deg": pd.to_numeric(latest.get("true_track"), errors="coerce"),
                "vertical_rate_ms": latest.get("vertical_rate"),
                "flight_phase": "tracked",
                "predicted_delay_min": latest.get("predicted_delay_min"),
                "last_updated": latest["ingest_time"],
            })
            write_snapshot(active, GOLD_ACTIVE, keys=["icao24"], description="Live active flights mart")
            density = active.groupby("origin_country").agg(
                total_active_flights=("icao24", "count"),
                avg_altitude_m=("altitude_m", "mean"),
                avg_velocity_kmh=("velocity_kmh", "mean"),
            ).reset_index()
            density["last_aggregated_at"] = utcnow_iso()
            write_snapshot(density, GOLD_DENSITY, keys=["origin_country"],
                           description="Live airspace density mart")
        if rejected:
            dlq_frame = pd.DataFrame([{
                "event_id": str(row.get("event_id")),
                "reasons": ";".join(str(reason) for reason in row.get("reasons", [])),
                "raw_payload": json.dumps(row.get("raw_payload", {}), default=str),
                "quarantined_at": row.get("quarantined_at"),
                "run_id": row.get("run_id"),
            } for row in rejected])
            write_snapshot(dlq_frame, SILVER_DIR / "dlq_events",
                           keys=["event_id", "reasons"],
                           description="Quarantined invalid/late events")
        meta["rows"] = len(accepted) + len(rejected)
        set_freshness(0, "silver.flight_states_clean")

    record_lineage(RUN_ID, "stream_consumer", ["bronze.flight_events_raw"],
                   ["silver.flight_states_clean", "silver.dlq_events",
                    "gold.active_flights_mart", "gold.airspace_density_mart"],
                   {"accepted": len(accepted), "dead_letter": len(rejected)})
    return {"accepted": len(accepted), "dead_letter": len(rejected)}


def _load_offsets() -> dict[str, int]:
    if OFFSET_STATE.exists():
        return json.loads(OFFSET_STATE.read_text(encoding="utf-8"))
    return {}


def _save_offsets(offsets: dict[str, int]) -> None:
    OFFSET_STATE.write_text(json.dumps(offsets, indent=2), encoding="utf-8")


def replay_from_bronze(path: Path | None = None, max_messages: int | None = None) -> dict:
    """Replay/backfill from the durable Bronze JSONL (F-13).

    This path is broker-independent, so the same raw events can rebuild Silver
    and Gold after a consumer outage or schema change.
    """
    source = Path(path) if path else RAW_EVENTS
    events = read_jsonl(source)
    if max_messages:
        events = events[:max_messages]
    stats = {"ACCEPTED": 0, "DUPLICATE": 0, "INVALID": 0, "LATE": 0}
    with measure_job("stream_bronze_replay") as meta:
        for event in events:
            outcome = process_event(event)
            stats[outcome] = stats.get(outcome, 0) + 1
        flushed = flush()
        meta["rows"] = len(events)
    record_lineage(RUN_ID, "stream_bronze_replay", [str(source)],
                   ["silver.flight_states_clean", "silver.dlq_events",
                    "gold.active_flights_mart", "gold.airspace_density_mart"], stats)
    log.info("bronze replay completed", extra={
        "job": "stream_bronze_replay", "status": "SUCCESS", "rows": len(events), **stats})
    return {**stats, "flushed": flushed, "source": str(source)}


def run_consumer(duration_sec: int | None = None, max_messages: int | None = None) -> dict:
    try:
        from kafka import KafkaConsumer
    except ImportError:
        log.error("kafka-python not installed; cannot consume from broker", extra={"status": "FAILED"})
        return {"error": "kafka-python not installed"}

    consumer = KafkaConsumer(
        TOPIC_RAW,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        group_id=CONSUMER_GROUP,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        consumer_timeout_ms=1000 if duration_sec else 10000,
    )
    stats = {"ACCEPTED": 0, "DUPLICATE": 0, "INVALID": 0, "LATE": 0}
    started = time.time()
    pending = 0
    try:
        while True:
            if duration_sec and (time.time() - started) > duration_sec:
                break
            batch = consumer.poll(timeout_ms=1000, max_records=100)
            for topic_partition, messages in batch.items():
                for message in messages:
                    event = message.value
                    outcome = process_event(event)
                    stats[outcome] = stats.get(outcome, 0) + 1
                    pending += 1
                    lag = max(0.0, (time.time() * 1000 - message.timestamp) / 1000)
                    set_lag(lag, TOPIC_RAW)
                    if pending >= FLUSH_EVERY:
                        flush()
                        consumer.commit()
                        _save_offsets({str(tp): message.offset for tp in batch})
                        pending = 0
                    if max_messages and sum(stats.values()) >= max_messages:
                        flush()
                        consumer.commit()
                        return stats
            if not batch:
                flush()
                consumer.commit()
                if max_messages:
                    break
    finally:
        flush()
        consumer.commit()
        consumer.close()
    log.info("consumer stopped", extra={"job": "stream_consumer", "status": "SUCCESS", **stats})
    return stats


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Redpanda consumer -> Silver/Gold with DLQ")
    parser.add_argument("--duration", type=int, default=None)
    parser.add_argument("--max-messages", type=int, default=None)
    parser.add_argument("--replay-bronze", help="Replay a Bronze JSONL file without Kafka")
    args = parser.parse_args()
    if args.replay_bronze:
        print(json.dumps(replay_from_bronze(Path(args.replay_bronze), args.max_messages), indent=2))
    else:
        print(json.dumps(run_consumer(args.duration, args.max_messages), indent=2))


if __name__ == "__main__":
    main()
