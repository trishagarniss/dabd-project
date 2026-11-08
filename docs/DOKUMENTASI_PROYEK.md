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
|   OpenSky Network Live API                                         OurAirports Master Database              |
|   (Polled tiap 15 detik, koordinat,                                (5.282 bandara komersial global,         |
|    kecepatan, altitude pesawat)                                     kode ICAO/IATA, elevasi)                |
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
|  - Eksperimen 1 (Baseline)  : Model Ridge Regression (MAE: 5.14 menit, RMSE: 6.62)                          |
|  - Eksperimen 2 (Candidate) : Model Random Forest (MAE: 3.27 menit, RMSE: 4.04) -> [Peningkatan 38.88%]    |
|  - Model Versioning & MLflow: Model v2 otomatis dipromosikan sebagai Champion                               |
+-------------------------------------------------------------------------------------------------------------+
                                       │
                                       ▼
+-------------------------------------------------------------------------------------------------------------+
| 6. SERVING API LAYER (FastAPI - src/serving/api.py) (F-10)                                                  |
|                                                                                                             |
|  - GET  /api/v1/health             : Healthcheck container & status model ML                                |
|  - GET  /api/v1/flights/active     : Mengambil 50 record data mart penerbangan aktif                        |
|  - GET  /api/v1/airports/{code}    : Query metadata bandara berdasarkan IATA/ICAO                           |
|  - POST /api/v1/ml/predict-delay   : Online inference prediksi keterlambatan (F-12)                         |
|  - GET  /api/v1/ml/experiments     : Komparasi parameter & metrik model v1 vs v2                           |
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
1. **Streaming Data**: Script `stream_producer.py` menghubungi OpenSky API setiap 15 detik. Mengambil pesawat yang sedang berada di langit Indonesia/ASEAN.
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
1. **Fitur yang Digunakan**: Jarak sisa penerbangan (`distance_to_dest_km`), ketinggian (`altitude_m`), kecepatan (`velocity_kmh`), dan jam sibuk operasional bandara (`hour_of_day`).
2. **Komparasi 2 Model**:
   - Dibuat 2 eksperimen dengan test set yang sama persis (bebas data leakage, `random_state=42`).
   - Model v2 (Random Forest) mengungguli Model v1 (Ridge) dengan penurunan eror RMSE sebesar **38.88%**.
   - Model v2 disimpan sebagai artefak `.pkl` untuk melayani request prediksi.

### Tahap E: Serving & Dashboard
1. Backend **FastAPI** membaca data Gold mart dan menyediakan endpoint API yang cepat dan aman.
2. Frontend **React (Vite)** menyajikan:
   - 4 kartu KPI operasional (*total pesawat, estimasi delay, kecepatan rata-rata, ketinggian*).
   - Tabel radar dengan fitur pencarian instan.
   - Panel governance ML untuk melihat perbandingan akurasi model v1 vs v2.
   - Kalkulator inference interaktif untuk menguji prediksi delay secara langsung.

---

## 🚀 4. Cara Menjalankan Proyek (Demo Guide)

### 1. Jalankan Retraining ML (Eksperimen v1 vs v2)
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
python -m unittest discover -s tests/unit
```

---