# Runbook Operasi SkyPulse (F-17)

## Persiapan
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
- **Tindakan:** jalankan ulang job terkait dengan `--retry 2`; periksa sumber
  (OurAirports/BTS) dan checksum. Rerun bersifat idempoten karena `batch_id` dan `keys`.
- **Clear:** metrik FAILED berhenti, status alert `resolved`, dicatat oleh webhook.

## B. StreamLagOrFreshnessHigh
- **Trigger:** `fdp_stream_lag_seconds > 120` ATAU freshness `> 300s` selama 2m,
  severity `warning`, owner `streaming`.
- **Diagnosis:** `evidence/metrics/job_*.jsonl`, `logs/structured.jsonl`,
  `GET /api/v1/flights/active` → field `freshness`.
- **Tindakan:** periksa `fdp-producer` (poll 15s), `rpk group describe`, dan dedup SQLite
  (`data/state/dedup.sqlite3`). Jika broker hilang, jalankan
  `python -m src.streaming.stream_consumer --replay-bronze data/bronze/flight_events_raw.jsonl`.
- **Clear:** lag/freshness kembali di bawah threshold; resolved dicatat.

## C. ServiceResourceUnhealthy
- **Trigger:** CPU > 90% ATAU memory > 1500 MB ATAU `up{job="fdp-api"} == 0` selama 3m,
  severity `critical`, owner `platform`.
- **Diagnosis:** Grafana "SkyPulse Operations", `GET /api/v1/metrics`, Docker stats.
- **Tindakan:** `docker compose restart api` (atau komponen lain), periksa healthcheck,
  batas resource `deploy.resources.limits` di `docker-compose.yml`.
- **Clear:** metrik kembali normal; resolved dicatat.

## Backup / Restore / Restart
```bash
python -m scripts.backup
python -m scripts.restore --manifest backups/<stamp>/manifest.json --dry-run
python -m scripts.restore --manifest backups/<stamp>/manifest.json --target restore_test
docker compose restart api                     # uji restart satu komponen
```
Manifest dan checksum: `evidence/backup_manifest_latest.json`,
`evidence/restore_report.json`, `evidence/restore_dry_run.json`.

**Retensi:** `python -m scripts.backup` menyimpan hanya backup terbaru (`--keep 1`).
Gunakan `--keep 3` bila ingin 3 versi, atau `--keep 0` agar tidak menghapus apa pun.
Snapshot Parquet juga dibatasi 5 versi per dataset (`FDP_MAX_SNAPSHOT_VERSIONS`),
supaya aliran 15 detik tidak membengkakkan `data/silver` dan `data/gold`.

## Cakupan OpenSky
Default producer mem-poll **seluruh dunia** (`FDP_OPENSKY_BBOX=global`). Untuk membatasi
wilayah, set `FDP_OPENSKY_BBOX=lamin,lomin,lamax,lomax` di `.env` lalu
`docker compose up -d producer`.
Dashboard meminta semua pesawat aktif (batas API 20.000; 5.651 pada uji global);
jumlah sebenarnya mengikuti trafik OpenSky. Catatan: cakupan global menulis sekitar
5.000 event ke Bronze tiap poll 15 detik, jadi pantau ukuran
`data/bronze/flight_events_raw.jsonl`. Producer global memakai interval 30 detik
 agar laju ~5.000 event/poll masih bisa dikejar consumer; dashboard tetap refresh 15 detik.

## Replay / Backfill
```bash
python -m src.streaming.stream_producer --replay data/bronze/flight_events_raw.jsonl
python -m src.streaming.stream_consumer --replay-bronze data/bronze/flight_events_raw.jsonl
python -m src.batch.transform --backfill-start 2024-01-01 --backfill-end 2024-01-14
```
Replay kedua menghasilkan `DUPLICATE` untuk semua event (idempoten).
