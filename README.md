# Flight Data Platform (TBP Advanced Data Platform Engineering)

Platform analitik lalu lintas udara global menggunakan Arsitektur Lambda/Kappa terintegrasi dengan Batch, Stream, Machine Learning (Flight Delay Prediction), dan Observability.

## Pemetaan Functional Requirement (TBP PDF)
- **F-01 Deployment**: `docker-compose.yml`, isolasi Redpanda, Postgres, Prometheus, Grafana.
- **F-02 Batch & Scheduler**: `src/batch/` (Ingestion batch master bandara & backfill).
- **F-03 Incremental & Backfill**: Deduplikasi & upsert ke Gold/Silver.
- **F-04 Stream Processing**: `src/streaming/stream_producer.py` (OpenSky API ke Redpanda).
- **F-05 Event-time & Deduplication**: Hash-based deduplikasi `event_id`, DLQ handler.
- **F-06 Medallion Architecture**: `data/bronze`, `data/silver`, `data/gold`.
- **F-07 Parquet Storage**: Penyimpanan kolumnar dengan Parquet di layer analitik.
- **F-08 Data Quality Gate**: Validasi null, range check lat/lon/altitude pada stream & batch.
- **F-09 Metadata & Lineage**: Skema metadata, catalog, dan lineage tracking.
- **F-10 Serving SQL & API**: `src/serving/api.py` (FastAPI + SQL Marts).
- **F-11 & F-12 ML Training & Inference**: `src/ml/` (Prediksi flight delay, logging MLflow).
- **F-13 Dashboard**: `dashboard/app.py` (Streamlit visualisasi map interaktif & metrik delay).
- **F-14 & F-15 Observability & Alerting**: `monitoring/` (Prometheus metrics & Grafana alerts).
- **F-16 Security**: `.env` (Secret management), role separation di database.
- **F-17 Backup & Restore**: Script backup/restore postgres dan snapshot.
- **F-18 Tests**: `tests/` (Unit test coverage >= 40% dan integration test).
- **ADR-01 s/d ADR-05**: Dokumentasi keputusan arsitektur di `docs/adr/`.
