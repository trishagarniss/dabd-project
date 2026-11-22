# Skrip Demo & Laporan Ringkas (F-20)

## 1. Arsitektur (2 menit)
Tunjukkan `docs/DOKUMENTASI_PROYEK.md` + `docs/adr/ADR-001..005.md`.
Alur: **OurAirports + BTS (batch)** dan **OpenSky (stream, 30s)** →
Redpanda/Bronze → Silver (quality gate + DLQ) → Gold (3 mart + feature store) →
FastAPI → dashboard React. Prometheus/Grafana/Alertmanager memantau semua komponen.

## 2. Deploy & kesehatan (2 menit)
```bash
docker compose up -d --build
docker compose ps
curl -H 'x-api-key: demo-viewer-key' http://localhost:8000/api/v1/health
```
Ekspektasi: 10 service berjalan (`node-exporter` opsional lewat profile `host-metrics`);
health mengembalikan `model_version`, `dataset_version`.

## 3. Batch + kualitas (3 menit)
```bash
python -m src.batch.ingest_airports
python -m src.batch.ingest_bts_ontime --sample-size 5000
python -m src.batch.transform --backfill-start 2024-01-01 --backfill-end 2024-01-14
```
Tunjukkan `evidence/quality/quality_report_*.json` — 4.571 bandara (99,98% PASS),
3.934 penerbangan (100% row PASS, 50 peringatan kode IATA lama) dan 3 mart Gold.

## 4. Stream, event-time, dedup (3 menit)
```bash
python -m src.streaming.stream_producer --duration 1
python -m src.streaming.stream_consumer --replay-bronze data/bronze/flight_events_raw.jsonl
python -m src.streaming.stream_consumer --replay-bronze data/bronze/flight_events_raw.jsonl
```
Tunjukkan `evidence/replay_first_run.json` (116 ACCEPTED, 8 LATE/DLQ) dan
`evidence/replay_second_run_idempotent.json` (124 DUPLICATE, 0 tulisan baru).

## 5. ML & inference (3 menit)
```bash
python -m src.ml.retrain
curl -H 'x-api-key: demo-operator-key' -H 'Content-Type: application/json' \
  -X POST http://localhost:8000/api/v1/ml/predict-delay \
  -d '{"input_record_id":"FL_2024_00001","distance_km":820.5,"hour_of_day":14,"day_of_week":2,"month":1,"dep_delay_min":5,"taxi_out_min":18,"crs_elapsed_min":140}'
```
Tunjukkan `evidence/ml/comparison.json`: baseline RMSE 11.05, candidate 12.94,
champion `v1`. Data dari BTS asli (tanpa sintetis).

## 6. Dashboard & SQL (2 menit)
Buka `http://localhost:5173` (`npm run dev` di `web-dashboard/`, Tailwind + ikon lucide).
Tunjukkan peta **Live ADS-B Radar** (ikon pesawat OpenSky asli, berputar mengikuti
`true_track_deg`, refresh 15s), header/main/footer yang jelas, 4 KPI, filter
tanggal/jam/destinasi, freshness, panel reconciliation, dan `POST` inference di tab ML.
Bandingkan `evidence/reconciliation.json` dengan `config/serving_queries.sql#Q10`.

## 7. Observability, alert, keamanan (3 menit)
- Grafana `http://localhost:3000` → dashboard "SkyPulse Operations".
- `python -m scripts.test_alerts` → `evidence/alerts/alert_timeline.json` (3 firing + 3 resolved).
- `curl -i http://localhost:8000/api/v1/flights/active` → 401; dengan viewer key → 200;
  viewer POST inference → 403. Tunjukkan `logs/audit.jsonl`.

## 8. Recovery & pengujian (2 menit)
```bash
python -m scripts.backup
python -m scripts.restore --manifest backups/<stamp>/manifest.json --dry-run
python -m pytest --cov=src --cov-report=term
docker compose restart api
```
Ekspektasi: 238 file checksum cocok; 27 test PASS; coverage 55%; API kembali healthy.

## Kontribusi tim
| Nama | Komponen utama |
|---|---|
| Alvian Damar | Deployment/isolasi, Redpanda, producer, API, observability, backup |
| Talitha Sukma | Batch ingestion, transform/backfill, medallion, storage, lineage |
| Stefani Ayudya | Quality gate/DLQ, event-time, dashboard, unit test |
| Trisha Garnis | Dataset ML, eksperimen/versioning, inference |
| Semua anggota | ADR, laporan, demo, evidence matrix |

Catatan: daftar di atas diambil dari `drive_templates/Project_Tracker_dan_Pembagian_Tugas.csv`;
nama dapat disesuaikan dengan pembagian kelas sebenarnya sebelum pengumpulan.
