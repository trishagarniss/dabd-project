"""Redpanda/Kafka producer for live OpenSky telemetry (F-04, F-05).

Every event carries event_id, event_time, ingest_time, payload_version and a partition key.
Raw events are always persisted to Bronze first, giving a replayable source of truth.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from src.common.config import (
    BRONZE_DIR, KAFKA_BOOTSTRAP, POLL_INTERVAL_SEC, RUN_ID, TOPIC_RAW, OPENSKY_BBOX, utcnow_iso,
)
from src.common.lineage import record_lineage
from src.common.logging_utils import get_logger
from src.common.metrics import count_event, measure_job
from src.common.storage import append_jsonl, read_jsonl
from src.ingestion.opensky_collector import fetch_opensky_states, parse_state_vector

log = get_logger("stream.producer")
RAW_EVENTS = BRONZE_DIR / "flight_events_raw.jsonl"


def create_producer() -> Any | None:
    try:
        from kafka import KafkaProducer
    except ImportError:
        log.warning("kafka-python not installed; broker disabled")
        return None
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            retries=3,
            acks="all",
            linger_ms=20,
            client_id=f"fdp-producer-{RUN_ID}",
        )
        log.info("producer connected", extra={"job": "stream_producer", "status": "SUCCESS"})
        return producer
    except Exception as exc:
        log.error("producer could not connect", extra={"job": "stream_producer", "status": "FAILED",
                                                       "error": str(exc)})
        return None


def build_event(raw_vector: list, server_time: int) -> dict[str, Any]:
    event = parse_state_vector(raw_vector, server_time)
    event["partition_key"] = event["icao24"]
    event["producer_run_id"] = RUN_ID
    event["source"] = "OpenSky Network /states/all"
    event["payload_version"] = "1.1"
    return event


def publish_event(event: dict[str, Any], producer: Any | None) -> str:
    """Persist to Bronze and publish to the broker. Returns published|bronze-only."""
    append_jsonl(RAW_EVENTS, event)
    count_event("raw_event", "producer")
    if producer is None:
        return "bronze-only"
    try:
        producer.send(TOPIC_RAW, key=event.get("partition_key"), value=event)
        return "published"
    except Exception as exc:
        log.error("publish failed; event retained in Bronze", extra={
            "event_id": event.get("event_id"), "status": "FAILED", "error": str(exc)})
        return "bronze-only"


def run_stream_producer(poll_interval_sec: int = POLL_INTERVAL_SEC, duration_sec: int | None = None,
                        replay_file: Path | None = None) -> dict:
    producer = create_producer()
    stats = {"published": 0, "bronze_only": 0, "replayed": 0}
    started = time.time()
    if replay_file:
        events = read_jsonl(Path(replay_file))
        with measure_job("stream_replay") as meta:
            for event in events:
                result = publish_event(event, producer)
                stats["published" if result == "published" else "bronze_only"] += 1
                stats["replayed"] += 1
            meta["rows"] = len(events)
        if producer:
            producer.flush()
        record_lineage(RUN_ID, "stream_replay", [str(replay_file)],
                       ["bronze.flight_events_raw", f"kafka.{TOPIC_RAW}"], {"replayed": len(events)})
        log.info("replay completed", extra={"job": "stream_replay", "rows": len(events),
                                             "status": "SUCCESS"})
        if producer:
            producer.close()
        return stats

    try:
        while True:
            if duration_sec and (time.time() - started) > duration_sec:
                break
            payload = fetch_opensky_states(bounding_box=OPENSKY_BBOX)
            count = 0
            if payload and payload.get("states"):
                server_time = payload.get("time", int(time.time()))
                for vector in payload["states"]:
                    result = publish_event(build_event(vector, server_time), producer)
                    stats["published" if result == "published" else "bronze_only"] += 1
                    count += 1
            if producer:
                producer.flush()
            log.info("poll completed", extra={"job": "stream_producer", "rows": count,
                                              "status": "SUCCESS" if count else "EMPTY"})
            if duration_sec is None:
                time.sleep(poll_interval_sec)
            else:
                break
    except KeyboardInterrupt:
        log.info("producer stopped by user")
    finally:
        if producer:
            producer.close()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenSky -> Redpanda producer")
    parser.add_argument("--poll-interval", type=int, default=POLL_INTERVAL_SEC)
    parser.add_argument("--duration", type=int, default=None, help="Stop after N seconds (one-shot when set)")
    parser.add_argument("--replay", help="Path to a Bronze JSONL file to replay")
    args = parser.parse_args()
    print(json.dumps(run_stream_producer(args.poll_interval, args.duration,
                                         Path(args.replay) if args.replay else None), indent=2))


if __name__ == "__main__":
    main()
