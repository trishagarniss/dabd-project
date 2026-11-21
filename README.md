# SkyPulse — Flight Data Platform (TBP Advanced Data Platform Engineering)

Platform analitik penerbangan **local/on-premise** yang menggabungkan batch (OurAirports,
BTS TranStats) dan stream (OpenSky → Redpanda), seni bina medallion, tiga mart analitik,
ML ramalan delay, FastAPI, dashboard React, Prometheus/Grafana/Alertmanager.

> **Integriti data:** semua baris ML berasal dari rekod BTS sebenar (public domain,
> checksum direkod). Tiada data sintetik digunakan.

## Pantas mula
```bash
cp .env.example .env
docker compose up -d --build
python -m src.batch.ingest_airports
python -m src.batch.ingest_bts_ontime --sample-size 5000
python -m src.batch.transform
python -m src.ml.retrain
python -m src.streaming.stream_producer --duration 1
python -m src.streaming.stream_consumer --replay-bronze data/bronze/flight_events_raw.jsonl
python -m pytest --cov=src --cov-report=term
```

API: `http://localhost:8000/docs` · Dashboard: `http://localhost:5173` ·
Grafana: `http://localhost:3000` · Prometheus: `http://localhost:9090`.
Kunci demo: `demo-viewer-key`, `demo-operator-key`, `demo-admin-key` (header `x-api-key`).

## Pemetaan Functional Requirement (F-01 – F-20)
| ID | Ringkasan | Bukti utama |
|---|---|---|
| F-01 | Deployment & isolasi 9 servis | `docker-compose.yml`, `Dockerfile`, `config/init_db.sql` |
| F-02 | Batch + penjadualan | `src/batch/ingest_airports.py`, `ingest_bts_ontime.py`, `scheduler.py` |
| F-03 | Incremental, retry, backfill | `src/batch/transform.py`, `src/common/storage.py` |
| F-04 | Stream processing | `src/streaming/stream_producer.py`, `data/bronze/flight_events_raw.jsonl` |
| F-05 | Event-time, lateness, dedup | `src/streaming/stream_consumer.py`, `data/state/dedup.sqlite3` |
| F-06 | Medallion Bronze/Silver/Gold | `data/bronze`, `data/silver`, `data/gold` |
| F-07 | Parquet + jadual ACID | `src/common/storage.py`, `config/init_db.sql` |
| F-08 | Quality gate + DLQ | `config/quality_rules.json`, `src/common/quality.py`, `evidence/quality/` |
| F-09 | Metadata, owner, lineage | `data/lineage/`, `src/common/lineage.py` |
| F-10 | 10 query SQL + 13 endpoint | `config/serving_queries.sql`, `src/serving/api.py` |
| F-11 | Dataset ML + versioning | `src/ml/prepare_features.py`, `train.py`, `tracking.py`, `evidence/ml/` |
| F-12 | Inference ML + audit | `POST /api/v1/ml/predict-delay`, `data/gold/predictions.jsonl` |
| F-13 | Dashboard Tailwind + peta live + insight + reconciliasi | `web-dashboard/src/App.jsx`, `evidence/reconciliation.json` |
| F-14 | Metrics + structured logs | `src/common/metrics.py`, `logging_utils.py`, `logs/` |
| F-15 | 3 alert firing + resolved | `monitoring/prometheus/alert_rules.yml`, `scripts/test_alerts.py` |
| F-16 | RBAC, secret, audit | `.env.example`, `docs/SECURITY.md`, `logs/audit.jsonl` |
| F-17 | Backup & restore | `scripts/backup.py`, `scripts/restore.py`, `docs/RUNBOOK.md` |
| F-18 | Ujian + reproducibility | `tests/`, `pytest.ini`, `evidence/test_output.txt` (27 PASS, 55%) |
| F-19 | Profiling & trade-off | `scripts/profile_pipeline.py`, `docs/PROFILING.md` |
| F-20 | Demo & laporan | `docs/DEMO_SCRIPT.md`, `docs/EVIDENCE_INDEX.md` |

Indeks bukti lengkap: `docs/EVIDENCE_INDEX.md`. Keputusan seni bina: `docs/adr/ADR-001.md` – `ADR-005.md`.
Skrip demo: `docs/DEMO_SCRIPT.md`. Nota operasi: `docs/RUNBOOK.md`.
