"""
Stream Consumer & Quality Gate Processor (F-04, F-05, F-08)
Membaca event dari topic Kafka/Redpanda, melakukan deduplikasi,
validasi kualitas (quality gate), dan meneruskan data valid ke layer Silver & Dead Letter Queue (DLQ).
"""

import json
import logging
from datetime import datetime, timezone

try:
    from kafka import KafkaConsumer
except ImportError:
    KafkaConsumer = None

KAFKA_BOOTSTRAP_SERVERS = ["localhost:19092"]
SOURCE_TOPIC = "flight-raw-stream"
DLQ_TOPIC = "flight-stream-dlq"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# In-memory deduplication set (F-05) - menyimpan event_id unik terbaru
seen_event_ids = set()

def validate_quality_gate(event):
    """
    F-08: Data Quality Gate:
    1. Not-null checks pada identifier dan koordinat penting.
    2. Range checks: latitude (-90 s/d 90), longitude (-180 s/d 180), altitude (>= 0).
    """
    reasons = []
    
    if not event.get("icao24"):
        reasons.append("Missing icao24")
    
    lat = event.get("latitude")
    lon = event.get("longitude")
    
    if lat is None or lon is None:
        reasons.append("Missing latitude or longitude")
    elif not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        reasons.append(f"Invalid coordinate range: lat={lat}, lon={lon}")
        
    alt = event.get("baro_altitude")
    if alt is not None and alt < -500: # Dibawah permukaan laut tidak wajar
        reasons.append(f"Unrealistic altitude: {alt}m")
        
    return len(reasons) == 0, reasons

def run_consumer():
    logging.info(f"Memulai Consumer pada topic: {SOURCE_TOPIC}...")
    try:
        consumer = KafkaConsumer(
            SOURCE_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            group_id='fdp-silver-consumer-group',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
    except Exception as e:
        logging.error(f"Gagal inisialisasi Kafka Consumer: {e}")
        return

    valid_count = 0
    duplicate_count = 0
    invalid_count = 0

    try:
        for message in consumer:
            event = message.value
            event_id = event.get("event_id")

            # 1. Deduplikasi (F-05)
            if event_id in seen_event_ids:
                duplicate_count += 1
                logging.debug(f"[DEDUP] Duplikat event_id terdeteksi: {event_id}, dilewati.")
                continue
            seen_event_ids.add(event_id)

            # 2. Quality Gate (F-08)
            is_valid, reasons = validate_quality_gate(event)
            if not is_valid:
                invalid_count += 1
                logging.warning(f"[DLQ/INVALID] Record ditolak: {event.get('callsign')} -> {reasons}")
                # Pada arsitektur lengkap, record ini dikirim ke DLQ (Dead Letter Queue)
                continue

            # 3. Data Valid Siap Masuk Layer Silver
            valid_count += 1
            if valid_count % 10 == 0:
                logging.info(f"[SILVER INGEST] Terproses valid: {valid_count} | Duplikat: {duplicate_count} | Ditolak: {invalid_count}")
                
    except KeyboardInterrupt:
        logging.info("Consumer dihentikan.")
    finally:
        consumer.close()

if __name__ == "__main__":
    run_consumer()
