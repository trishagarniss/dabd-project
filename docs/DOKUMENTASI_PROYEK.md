# ✈️ DOKUMENTASI PROYEK: SKYPULSE DATA PLATFORM
**TBP: Advanced Data Platform Engineering (Desain Aplikasi Big Data)**

---

## 📌 1. Ringkasan & Problem Statement

### Masalah:
Pelacakan ribuan pesawat di udara secara *real-time* menghasilkan data telemetri dengan kecepatan tinggi (*high velocity*). Namun, data posisi koordinat mentah dari transponder pesawat (*ADS-B*) tidak memiliki informasi kontekstual (misal: ini menuju bandara mana, apakah penerbangan ini terlambat, berapa estimasi waktu tibanya).

### Solusi Platform:
Membangun platform data terintegrasi menggunakan **Arsitektur Lambda Modern (Medallion: Bronze $\rightarrow$ Silver $\rightarrow$ Gold)** yang menggabungkan:
1. **Jalur Streaming**: Menarik posisi *live telemetry* pesawat secara kontinu via OpenSky Network API.
2. **Jalur Batch**: Mengonsumsi dataset master bandara global (OurAirports) secara berkala.
3. **Machine Learning**: Memprediksi estimasi keterlambatan (*flight arrival delay*) secara *real-time*.
4. **Serving & Dashboard**: Antarmuka web profesional berbasis **React** dan backend **FastAPI**.

---

## 🏛️ 2. Diagram Alur & Ilustrasi Pipeline (End-to-End)

Berikut adalah visualisasi aliran data lengkap dari sumber sampai ke dashboard:

```
+-------------------------------------------------------------------------------------------------------------+
|                                           1. INGESTION SOURCES                                              |
|                                                                                                             |
|  [ Sumber Stream (Real-Time) ]                                    [ Sumber Batch (Terjadwal) ]              |
|   OpenSky Network Live API                                         OurAirports + BTS TranStats              |
|   (Polled tiap 15 detik, koordinat,                                (5.282 bandara global,                   |
|    kecepatan, altitude pesawat)                                    4.160 flight Jan 2024)                   |
+-------------------------------------------------------------------------------------------------------------+
               │                                                                   │
               ▼                                                                   ▼
       (stream_producer.py)                                               (ingest_airports.py)
               │                                                                   │
               ▼                                                                   ▼
+-----------------------------+                                    +------------------------------+
| 2. MESSAGE BROKER STREAMING |                                    | BATCH STAGING STORAGE        |
| Redpanda (Kafka-Compatible) |                                    | data/reference/              |
| Topic: `flight-raw-stream`  |                                    | airports_reference.csv       |
+-----------------------------+                                    +------------------------------+
               │                                                                   │
               ▼                                                                   │
+-------------------------------------------------------------+                    │
| 3. STREAM CONSUMER & QUALITY GATE (stream_consumer.py)      |                    │
| - Deduplikasi: Hash SHA-256(icao24 + timestamp) (F-05)      |                    │
| - Quality Gate: Null check & validasi rentang koordinat     |                    │
| - Error handling: Alihkan data anomali ke DLQ (F-08)        |                    │
+-------------------------------------------------------------+                    │
               │ (Data Bersih Tervalidasi)                                         │
               ▼                                                                   │
+----------------------------------------------------------------------------------┴--------------------------+
| 4. MEDALLION ARCHITECTURE (Penyimpanan Bertingkat)                                                          |
|                                                                                                             |
|  [ BRONZE LAYER ]  --> data/bronze/  : Raw JSON stream & raw CSV master (Bahan audit & replay)              |
|                                                                                                             |
|  [ SILVER LAYER ]  --> data/silver/  : Data pesawat bersih tervalidasi & data bandara terstandarisasi       |
|                                                                                                             |
|  [ GOLD LAYER ]    --> data/gold/    : Feature Store (Jarak pesawat ke bandara dihitung via Haversine)      |
|                                        & Mart analitik siap saji (F-06, F-07)                               |
+-------------------------------------------------------------------------------------------------------------+
                                       │
                                       ▼
+-------------------------------------------------------------------------------------------------------------+
| 5. MACHINE LEARNING ENGINE (src/ml/) (F-11 & F-12)                                                          |
|                                                                                                             |
|  - Eksperimen v1 (Baseline)  : Ridge Regression (MAE 8.06, RMSE 11.05) -> Champion                          |
|  - Eksperimen v2 / v3        : Random Forest RMSE 12.94 / Gradient Boosting RMSE 12.78                      |
|  - Model Versioning          : tracker JSONL lokal (pengganti MLflow), champion di registry                 |
+-------------------------------------------------------------------------------------------------------------+
                                       │
                                       ▼
+-------------------------------------------------------------------------------------------------------------+
| 6. SERVING API LAYER (FastAPI - src/serving/api.py) (F-10)                                                  |
|                                                                                                             |
|  - GET  /api/v1/health             : Healthcheck container & status model ML                                |
|  - GET  /api/v1/flights/active     : Mengambil hingga 500 record pesawat aktif (live tracks)                |
|  - GET  /api/v1/airports/{code}    : Query metadata bandara berdasarkan IATA/ICAO                           |
|  - POST /api/v1/ml/predict-delay   : Online inference prediksi keterlambatan (F-12)                         |
|  - GET  /api/v1/ml/experiments     : Komparasi parameter & metrik model v1/v2/v3                            |
+-------------------------------------------------------------------------------------------------------------+
                                       │
                                       ▼
+-------------------------------------------------------------------------------------------------------------+
| 7. USER INTERFACE & MONITORING (web-dashboard/ & monitoring/)                                               |
|                                                                                                             |
|  - React Web Dashboard : Visualisasi Radar Penerbangan, KPI delay, form test inference langsung (F-13)      |
|  - Prometheus & Grafana: Observability sistem, metrik latency, dan 3 alerting rules (F-14, F-15)            |
+-------------------------------------------------------------------------------------------------------------+
```

---

## 🔄 3. Penjelasan Alur Kerja Tahap demi Tahap

### Tahap A: Pengambilan Data (Ingestion)
1. **Streaming Data**: Script `stream_producer.py` menghubungi OpenSky API setiap 30 detik. Mengambil pesawat yang sedang berada di langit **seluruh dunia** (`FDP_OPENSKY_BBOX=global`); dapat dibatasi ke wilayah tertentu lewat bbox.
2. Setiap data pesawat diberi:
   - `event_id`: ID unik turunan hash SHA-256 (`icao24 + timestamp`) agar tidak terjadi duplikasi pesan.
   - `event_time`: Waktu saat pesawat mentransmisikan sinyal.
   - `ingest_time`: Waktu saat server kita menerima data tersebut (memenuhi syarat F-05: pemisahan event-time vs processing-time).
3. Pesan dikirim ke broker streaming **Redpanda** pada topik `flight-raw-stream`.

### Tahap B: Validasi & Pembersihan (Quality Gate)
1. `stream_consumer.py` membaca data dari topik secara kontinu.
2. Melakukan **Deduplikasi**: jika `event_id` sudah pernah diproses, data dilewati (*skip*).
3. Melakukan **Quality Gate**: memeriksa apakah koordinat valid (Latitude $-90^\circ$ s/d $+90^\circ$, Longitude $-180^\circ$ s/d $+180^\circ$) dan altitude wajar. Data yang cacat dilempar ke log anomali / *Dead Letter Queue (DLQ)*.

### Tahap C: Medallion Architecture (Penyimpanan)
Data disimpan secara terstruktur ke 3 lapisan:
- **Bronze (Raw)**: Menyimpan salinan data mentah apa adanya untuk keperluan audit dan *replay* data jika terjadi kegagalan sistem.
- **Silver (Cleaned)**: Menyimpan data yang sudah lolos quality gate dan dinormalisasi.
- **Gold (Curated Mart)**: Menggabungkan (*enrichment*) data Silver pesawat dengan data Batch bandara menggunakan formula matematika *Haversine* untuk menghitung jarak sisa pesawat ke bandara tujuan.

### Tahap D: Machine Learning & Retraining
1. **Fitur yang Digunakan**: `distance_km`, `hour_of_day`, `day_of_week`, `month`, `dep_delay_min`, `taxi_out_min`, dan `crs_elapsed_min`, seluruhnya dari dataset BTS asli (tanpa data sintetis).
2. **Komparasi 3 Model**:
   - Eksperimen v1 (Ridge), v2 (Random Forest), dan v3 (Gradient Boosting) memakai test set yang sama (`random_state=42`, `test_size=0.2`).
   - Hasil terakhir: v1 RMSE 11,05; v2 RMSE 12,94; v3 RMSE 12,78. **Champion = v1 Ridge** karena RMSE terkecil.
   - Champion disimpan sebagai artefak `.pkl` dan dicatat di `data/gold/model_registry.json`.
3. **Catatan leakage**: `dep_delay_min` dan `taxi_out_min` baru diketahui setelah keberangkatan; untuk prediksi pra-keberangkatan keduanya perlu dikeluarkan.

### Tahap E: Serving & Dashboard
1. Backend **FastAPI** membaca data Gold mart dan menyediakan endpoint API yang cepat dan aman.
2. Frontend **React (Vite)** menyajikan:
   - 4 kartu KPI operasional (total flight records, rata-rata arrival delay, rata-rata jarak rute, live tracks).
   - Peta **Live ADS-B Radar** dengan ikon pesawat yang berputar mengikuti heading (`true_track_deg`).
   - Tabel radar dengan fitur pencarian instan.
   - Panel governance ML untuk melihat perbandingan akurasi model v1/v2/v3.
   - Kalkulator inference interaktif untuk menguji prediksi delay secara langsung.

---

## 🚀 4. Cara Menjalankan Proyek (Demo Guide)

### 1. Jalankan Retraining ML (Eksperimen v1/v2/v3)
```powershell
cd E:\Kuliah\S5\DABD\dabd-project
python -m src.ml.retrain
```

### 2. Jalankan Serving API (FastAPI)
```powershell
python -m uvicorn src.serving.api:app --reload --port 8000
```
*Dokumentasi Swagger API*: Buka `http://localhost:8000/docs` di browser.

### 3. Jalankan Web Dashboard (React)
Buka tab terminal baru:
```powershell
cd E:\Kuliah\S5\DABD\dabd-project\web-dashboard
npm run dev
```
*Aplikasi Dashboard*: Buka `http://localhost:5173` di browser.

### 4. Jalankan Unit Test (Quality Gate & Pipeline Validation)
```powershell
python -m pytest --cov=src --cov-report=term
```

---