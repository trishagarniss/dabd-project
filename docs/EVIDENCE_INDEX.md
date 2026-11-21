# Indeks Bukti F-01 – F-20

Semua path adalah relatif kepada `dabd-project/`. Status "TERBUKTI" bermaksud fail/output
wujud dan telah dijalankan pada 2026-11-21; rujuk `docs/DEMO_SCRIPT.md` untuk arahan ulang.

| ID | Status | Bukti utama |
|---|---|---|
| F-01 | TERBUKTI | `docker-compose.yml` (9 servis, network, resource limit, restart), `Dockerfile`, `config/init_db.sql`, `evidence/docker_compose_validate.txt` |
| F-02 | TERBUKTI | `src/batch/ingest_airports.py`, `src/batch/ingest_bts_ontime.py`, `src/batch/scheduler.py`, `evidence/jobs/airports_*.json`, `data/bronze/*.snapshot.json` |
| F-03 | TERBUKTI | `src/batch/transform.py` (`--policy`, `--backfill-*`, `--retry`), `src/common/storage.py` (upsert `version=*`), `docs/RUNBOOK.md#replay--backfill` |
| F-04 | TERBUKTI | `src/streaming/stream_producer.py`, `data/bronze/flight_events_raw.jsonl` (124 event OpenSky sebenar), `evidence/metrics/job_*.jsonl` |
| F-05 | TERBUKTI | `src/streaming/stream_consumer.py` (`is_late`, dedup SQLite), `data/state/dedup.sqlite3`, `evidence/replay_first_run.json`, `evidence/replay_second_run_idempotent.json` |
| F-06 | TERBUKTI | `data/bronze/`, `data/silver/`, `data/gold/`, `data/lineage/catalog.json`, `docs/adr/ADR-003.md` |
| F-07 | TERBUKTI | `src/common/storage.py`, `data/gold/*.parquet`, `data/gold/*.snapshot.json`, `config/init_db.sql` |
| F-08 | TERBUKTI | `config/quality_rules.json`, `src/common/quality.py`, `evidence/quality/quality_report_*.json`, `data/silver/dlq_events.parquet` |
| F-09 | TERBUKTI | `data/lineage/catalog.json`, `data/lineage/lineage.jsonl`, `data/lineage/runs/*.json`, `src/common/lineage.py`, `GET /api/v1/lineage/runs` |
| F-10 | TERBUKTI | `config/serving_queries.sql` (10 query), `src/serving/api.py` (13 endpoint), `tests/unit/test_api.py` |
| F-11 | TERBUKTI | `src/ml/prepare_features.py` (dataset BTS sebenar), `src/ml/train.py`, `src/ml/tracking.py`, `evidence/ml/experiment_report.json`, `evidence/ml/comparison.json`, `data/gold/model_registry.json`, `src/ml/models/*.pkl` |
| F-12 | TERBUKTI | `POST /api/v1/ml/predict-delay`, `data/gold/predictions.jsonl`, `data/gold/predictions.parquet`, ujian 422/403 di `tests/unit/test_api.py` |
| F-13 | TERBUKTI | `web-dashboard/src/App.jsx` (Tailwind + lucide icons, 4 KPI, 3 filter, refresh 15s, insight strip, ML tab, Leaflet live ADS-B radar with 100 rotated plane icons (true_track_deg)), `web-dashboard/dist/`, `evidence/reconciliation.json` (2 rentang), `config/serving_queries.sql#Q10` |
| F-14 | TERBUKTI | `src/common/metrics.py`, `src/common/logging_utils.py`, `logs/structured.jsonl`, `logs/audit.jsonl`, `evidence/metrics/*.jsonl`, `GET /api/v1/metrics` |
| F-15 | TERBUKTI | `monitoring/prometheus/alert_rules.yml`, `monitoring/alertmanager/alertmanager.yml`, `scripts/test_alerts.py`, `evidence/alerts/alert_timeline.json`, `evidence/alerts/alert_history.jsonl`, `monitoring/grafana/dashboards/sky-pulse-operations.json` |
| F-16 | TERBUKTI | `docs/SECURITY.md`, `.env.example`, `.gitignore`, `config/init_db.sql` (3 role), `logs/audit.jsonl`, ujian 401/403 `tests/unit/test_api.py` |
| F-17 | TERBUKTI | `scripts/backup.py`, `scripts/restore.py`, `evidence/backup_manifest_latest.json` (214 fail, auto-prune keep=1), `evidence/restore_dry_run.json`, `evidence/restore_full_run.json`, `docs/RUNBOOK.md` |
| F-18 | TERBUKTI | `tests/unit/`, `tests/integration/`, `pytest.ini`, `evidence/test_output.txt` (**27 passed, coverage 55%**), `evidence/coverage.json`, `evidence/coverage_html/index.html` |
| F-19 | TERBUKTI | `scripts/profile_pipeline.py`, `docs/PROFILING.md`, `evidence/profiling/raw_metrics.csv`, `evidence/profiling/summary.json`, `evidence/profiling/profile_run.txt` |
| F-20 | TERBUKTI | `docs/DEMO_SCRIPT.md`, dokumen ini, `drive_templates/Evidence_Matrix_dan_Checklist_F01_F20.csv`, `drive_templates/Notulensi_Diskusi_dan_Standup.md` |

## Nota integriti
- Tiada baris sintetik: `src/ml/prepare_features.py` hanya membaca Parquet Gold dari BTS.
- Semua metrik/ujian dijalankan secara lokal; tiada platform cloud menggantikan komponen teras.
- `README.md` dan matrix CSV dikemaskini untuk sepadan dengan keadaan sebenar repo.
