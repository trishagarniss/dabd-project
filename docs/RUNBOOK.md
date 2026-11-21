# Runbook Operasi SkyPulse (F-17)

## Persediaan
```bash
cp .env.example .env          # isi kunci sendiri; .env tidak di-commit
docker compose up -d --build
docker compose ps             # semua service healthy
python -m pytest --cov=src --cov-report=term
```

## A. BatchJobFailed
- **Trigger:** `increase(fdp_job_rows_total{status="FAILED"}[10m]) > 0` selama 1m,
  severity `critical`, owner `data-engineering`.
- **Diagnosis:** `logs/structured.jsonl` (cari `"status":"FAILED"`, `job`, `run_id`),
  `evidence/jobs/airports_<batch_id>.json`, `evidence/metrics/job_*.jsonl`.
- **Tindakan:** jalankan semula kerja berkenaan dengan `--retry 2`; semak sumber
  (OurAirports/BTS) dan checksum. Rerun adalah idempoten kerana `batch_id` dan `keys`.
- **Clear:** metrik FAILED berhenti, alert status `resolved`, direkod oleh webhook.

## B. StreamLagOrFreshnessHigh
- **Trigger:** `fdp_stream_lag_seconds > 120` ATAU freshness `> 300s` selama 2m,
  severity `warning`, owner `streaming`.
- **Diagnosis:** `evidence/metrics/job_*.jsonl`, `logs/structured.jsonl`,
  `GET /api/v1/flights/active` → medan `freshness`.
- **Tindakan:** semak `fdp-producer` (poll 15s), `rpk group describe`, dan dedup SQLite
  (`data/state/dedup.sqlite3`). Jika broker hilang, jalankan
  `python -m src.streaming.stream_consumer --replay-bronze data/bronze/flight_events_raw.jsonl`.
- **Clear:** lag/freshness kembali di bawah threshold; resolved direkod.

## C. ServiceResourceUnhealthy
- **Trigger:** CPU > 90% ATAU memory > 1500 MB ATAU `up{job="fdp-api"} == 0` selama 3m,
  severity `critical`, owner `platform`.
- **Diagnosis:** Grafana "SkyPulse Operations", `GET /api/v1/metrics`, Docker stats.
- **Tindakan:** `docker compose restart api` (atau komponen lain), semak healthcheck,
  had resource `deploy.resources.limits` dalam `docker-compose.yml`.
- **Clear:** metrik kembali normal; resolved direkod.

## Backup / Restore / Restart
```bash
python -m scripts.backup
python -m scripts.restore --manifest backups/<stamp>/manifest.json --dry-run
python -m scripts.restore --manifest backups/<stamp>/manifest.json --target restore_test
docker compose restart api                     # ujian restart satu komponen
```
Manifest dan checksum: `evidence/backup_manifest_latest.json`,
`evidence/restore_report.json`, `evidence/restore_dry_run.json`.

**Retensi:** `python -m scripts.backup` menyimpan hanya backup terbaru (`--keep 1`).
Guna `--keep 3` jika mahu 3 versi, atau `--keep 0` untuk tidak membuang apa-apa.
Snapshot Parquet juga dihadkan kepada 5 versi per dataset (`FDP_MAX_SNAPSHOT_VERSIONS`),
supaya aliran 15s tidak membengkakkan `data/silver` dan `data/gold`.

## Replay / Backfill
```bash
python -m src.streaming.stream_producer --replay data/bronze/flight_events_raw.jsonl
python -m src.streaming.stream_consumer --replay-bronze data/bronze/flight_events_raw.jsonl
python -m src.batch.transform --backfill-start 2024-01-01 --backfill-end 2024-01-14
```
Replay kedua menghasilkan `DUPLICATE` untuk semua event (idempoten).
