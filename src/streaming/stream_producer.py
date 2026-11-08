"""
Kafka / Redpanda Producer untuk Streaming Data Pesawat (F-04)
Menarik live state vector secara periodik dari OpenSky Network dan mem-publish ke topic Kafka/Redpanda.
"""

import time
import json
import logging
from kafka import KafkaProducer
from src.ingestion.opensky_collector import fetch_opensky_states, parse_state_vector

# Konfigurasi Broker
KAFKA_BOOTSTRAP_SERVERS = ["localhost:19092"]
TOPIC_NAME = "flight-raw-stream"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def create_producer():
    """Membuat instance KafkaProducer dengan serialisasi JSON."""
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            retries=3,
            acks="all" # Sesuai ADR-01 reliabilitas delivery
        )
        logging.info(f"Terhubung ke broker Kafka di {KAFKA_BOOTSTRAP_SERVERS}")
        return producer
    except Exception as e:
        logging.error(f"Gagal koneksi ke Kafka Broker: {e}")
        return None

def run_stream_producer(poll_interval_sec=15, duration_sec=None):
    """
    Menjalankan loop pengambilan data dan streaming.
    Area: Indonesia & sekitarnya [-11.0, 95.0, 6.0, 141.0]
    """
    producer = create_producer()
    if not producer:
        logging.warning("Berjalan dalam mode simulasi / logging lokal (broker belum aktif).")
    
    bbox = [-11.0, 95.0, 6.0, 141.0]
    start_time = time.time()
    
    try:
        while True:
            if duration_sec and (time.time() - start_time) > duration_sec:
                break
                
            logging.info("Mengambil live telemetry dari OpenSky...")
            payload = fetch_opensky_states(bounding_box=bbox)
            
            if payload and "states" in payload and payload["states"]:
                server_time = payload.get("time", int(time.time()))
                count = 0
                for raw_vector in payload["states"]:
                    # Parsing dan penambahan event_id, event_time, ingest_time (F-04 & F-05)
                    event = parse_state_vector(raw_vector, server_time)
                    
                    if producer:
                        # Key berdasarkan icao24 agar terpartisi konsisten per pesawat
                        producer.send(TOPIC_NAME, key=event["icao24"], value=event)
                    count += 1
                
                if producer:
                    producer.flush()
                logging.info(f"Berhasil memproses {count} data pesawat.")
            else:
                logging.warning("Data kosong atau limit API OpenSky.")
                
            time.sleep(poll_interval_sec)
    except KeyboardInterrupt:
        logging.info("Producer dihentikan oleh user.")
    finally:
        if producer:
            producer.close()

if __name__ == "__main__":
    run_stream_producer()
