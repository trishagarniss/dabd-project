# SkyPulse — Platform Data Penerbangan

Platform analitik penerbangan **lokal/on-premise** yang menggabungkan data batch
(OurAirports dan BTS TranStats) dengan data stream (OpenSky → Redpanda), memakai
arsitektur medallion Bronze → Silver → Gold, lalu menyajikannya lewat FastAPI,
dashboard React, dan observability Prometheus/Grafana/Alertmanager.

> **Integritas data:** seluruh baris ML berasal dari rekaman BTS asli (public domain,
> checksum dicatat). Tidak ada data sintetis yang dipakai.

## Mulai cepat

```bash
# Linux / macOS / Git Bash
cp .env.example .env
docker compose up -d --build

# Windows PowerShell
Copy-Item .env.example .env
docker compose up -d --build
```

Setelah container hidup, jalankan pipeline batch dan stream:

```bash
python -m src.batch.ingest_airports
python -m src.batch.ingest_bts_ontime --sample-size 5000
python -m src.batch.transform
python -m src.ml.retrain
python -m src.streaming.stream_producer --duration 1
python -m src.streaming.stream_consumer --replay-bronze data/bronze/flight_events_raw.jsonl
python -m pytest --cov=src --cov-report=term
```

Alamat layanan:

- Dashboard React: `http://localhost:5173`
- Dokumentasi API: `http://localhost:8000/docs`
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`
- Alertmanager: `http://localhost:9093`

Kunci demo: `demo-viewer-key`, `demo-operator-key`, `demo-admin-key`
(kirim lewat header `x-api-key`).

## Arsitektur

```text
OpenSky API (live) ──► stream_producer ──► Redpanda ──► stream_consumer
                                                     │
OurAirports + BTS ──► batch ingestion ───────────────┤
                                                     ▼
                                        Bronze → Silver → Gold
                                                     │
                                        FastAPI + React + ML
                                                     │
                                     Prometheus / Grafana / Alertmanager
```

- **Bronze** menyimpan data mentah dan metadata asal (checksum, batch ID, waktu ingest).
- **Silver** menyimpan data yang sudah dibersihkan, dideduplikasi, dan lolos quality gate.
- **Gold** menyimpan mart analitik serta feature store untuk model prediksi delay.
- **Stream** memakai `event_id` hash, pemisahan `event_time`/`ingest_time`, deduplikasi
  SQLite, toleransi keterlambatan 300 detik, dan Dead Letter Queue (DLQ).
- **Batch** bersifat idempoten lewat `batch_id` + checksum, dengan snapshot Parquet
  berversi dan lineage per run.

## Sumber data

| Sumber | Jenis | Isi | Jumlah snapshot terakhir |
|---|---|---|---:|
| OpenSky Network `/states/all` | Stream | Posisi pesawat: `icao24`, callsign, koordinat, altitude, kecepatan | 124 event |
| OurAirports | Batch | Master bandara: kode ICAO/IATA, nama, koordinat, elevasi | 5.282 bandara |
| BTS On-Time Performance Januari 2024 | Batch | Penerbangan domestik AS: jadwal, delay, jarak, asal-tujuan | 4.160 penerbangan |

Angka mengikuti snapshot terakhir dan bisa berubah setiap kali pipeline dijalankan.
Detail asal-usul data ada di `evidence/dataset_provenance.json` dan
`data/bronze/bts_ontime_provenance.json`.

## Model prediksi delay

Target model adalah `arr_delay_min` (keterlambatan tiba dalam menit). Fitur yang dipakai:
`distance_km`, `hour_of_day`, `day_of_week`, `month`, `dep_delay_min`, `taxi_out_min`,
dan `crs_elapsed_min`. Split data 80/20 dengan `random_state=42`.

| Versi | Model | MAE | RMSE | R² |
|---|---|---:|---:|---:|
| v1 | Ridge Regression | 8,064 | 11,050 | 0,9707 |
| v2 | Random Forest | 9,2499 | 12,944 | 0,9598 |
| v3 | Gradient Boosting | 8,781 | 12,782 | 0,9608 |

Model juara dipilih otomatis berdasarkan RMSE terkecil dan dicatat di
`data/gold/model_registry.json`. Pada snapshot terakhir, **v1 Ridge** menjadi juara.
Hasil bisa berubah setelah retraining.

> Catatan: `dep_delay_min` dan `taxi_out_min` baru diketahui setelah pesawat berangkat.
> Jika prediksi dilakukan sebelum keberangkatan, dua fitur itu perlu dikeluarkan agar
> tidak terjadi kebocoran data.

## Endpoint utama

| Method | Endpoint | Fungsi |
|---|---|---|
| GET | `/api/v1/health` | Status API dan model |
| GET | `/api/v1/flights/active` | Pesawat yang sedang dilacak |
| GET | `/api/v1/flights/date-range` | Data historis berdasarkan rentang tanggal |
| GET | `/api/v1/airports/{code}` | Metadata bandara |
| POST | `/api/v1/ml/predict-delay` | Prediksi delay |
| GET | `/api/v1/ml/experiments` | Perbandingan eksperimen model |

Query SQL siap pakai ada di `config/serving_queries.sql`.

## Struktur repository

```text
.
├── compose.yaml / docker-compose.yml
├── Dockerfile
├── config/                  # inisialisasi DB, aturan kualitas, query serving
├── data/
│   ├── bronze/              # data mentah + metadata asal
│   ├── silver/              # data bersih
│   ├── gold/                # mart analitik + feature store
│   ├── lineage/             # lineage per run
│   └── reference/           # cache master bandara
├── docs/                    # dokumentasi, ADR, runbook
├── evidence/                # bukti kualitas, metrik, eksperimen ML
├── monitoring/              # Prometheus, Grafana, Alertmanager
├── scripts/                 # backup, restore, profiling, demo
├── src/
│   ├── batch/               # ingest bandara/BTS + transform
│   ├── streaming/           # producer/consumer OpenSky
│   ├── serving/             # FastAPI
│   ├── ml/                  # training, retraining, inference
│   └── common/              # config, storage, quality, lineage, metrics
├── tests/                   # unit + integration test
└── web-dashboard/           # React + Vite + Tailwind + Leaflet
```

## Pemetaan Functional Requirement (F-01 – F-20)

| ID | Ringkasan | Bukti utama |
|---|---|---|
| F-01 | Deployment dan isolasi layanan | `docker-compose.yml`, `Dockerfile`, `config/init_db.sql` |
| F-02 | Batch dan penjadwalan | `src/batch/ingest_airports.py`, `ingest_bts_ontime.py`, `scheduler.py` |
| F-03 | Incremental, retry, backfill | `src/batch/transform.py`, `src/common/storage.py` |
| F-04 | Stream processing | `src/streaming/stream_producer.py`, `data/bronze/flight_events_raw.jsonl` |
| F-05 | Event-time, lateness, deduplikasi | `src/streaming/stream_consumer.py`, `data/state/dedup.sqlite3` |
| F-06 | Medallion Bronze/Silver/Gold | `data/bronze`, `data/silver`, `data/gold` |
| F-07 | Parquet dan tabel ACID | `src/common/storage.py`, `config/init_db.sql` |
| F-08 | Quality gate dan DLQ | `config/quality_rules.json`, `src/common/quality.py`, `evidence/quality/` |
| F-09 | Metadata, owner, lineage | `data/lineage/`, `src/common/lineage.py` |
| F-10 | Query SQL dan endpoint | `config/serving_queries.sql`, `src/serving/api.py` |
| F-11 | Dataset ML dan versioning | `src/ml/prepare_features.py`, `train.py`, `tracking.py`, `evidence/ml/` |
| F-12 | Inference ML dan audit | `POST /api/v1/ml/predict-delay`, `data/gold/predictions.jsonl` |
| F-13 | Dashboard React, peta live, insight, rekonsiliasi | `web-dashboard/src/App.jsx`, `evidence/reconciliation.json` |
| F-14 | Metrics dan structured log | `src/common/metrics.py`, `logging_utils.py`, `logs/` |
| F-15 | 3 alert firing dan resolved | `monitoring/prometheus/alert_rules.yml`, `scripts/test_alerts.py` |
| F-16 | RBAC, secret, audit | `.env.example`, `docs/SECURITY.md`, `logs/audit.jsonl` |
| F-17 | Backup dan restore | `scripts/backup.py`, `scripts/restore.py`, `docs/RUNBOOK.md` |
| F-18 | Pengujian dan reproducibility | `tests/`, `pytest.ini`, `evidence/test_output.txt` |
| F-19 | Profiling dan trade-off | `scripts/profile_pipeline.py`, `docs/PROFILING.md` |
| F-20 | Demo dan laporan | `docs/DEMO_SCRIPT.md`, `docs/EVIDENCE_INDEX.md` |

## Batasan

- BTS hanya mencakup penerbangan domestik AS dan satu bulan (Januari 2024).
- Belum ada join data cuaca.
- Data OpenSky bergantung pada ketersediaan API publik dan rate limit.
- `ArrDelay` dapat bernilai negatif (tiba lebih awal).
- Jam tiba tidak tersedia langsung di sampel BTS; yang ada `ArrDelay` dan durasi terjadwal.

## Dokumentasi lanjutan

- Indeks bukti: `docs/EVIDENCE_INDEX.md`
- Keputusan arsitektur: `docs/adr/ADR-001.md` – `ADR-005.md`
- Skrip demo: `docs/DEMO_SCRIPT.md`
- Runbook operasi: `docs/RUNBOOK.md`
- Keamanan: `docs/SECURITY.md`
