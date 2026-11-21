# DAFTAR TOOLS & TEKNOLOGI: SKYPULSE DATA PLATFORM
**TBP: Advanced Data Platform Engineering (DABD)**

Berikut adalah ringkasan seluruh teknologi dan tools yang digunakan dalam arsitektur platform data beserta fungsinya secara terstruktur:

---

### 1. Ingestion & Streaming Broker (Data Masuk)
* **OpenSky Network Live API** (REST API Publik)
  * **Fungsi**: Sumber data streaming primer untuk menarik data telemetri pesawat di wilayah Indonesia/ASEAN (koordinat latitude/longitude, altitude, ground speed, heading) secara real-time setiap 15 detik.
* **OurAirports Master Database** (Dataset Publik)
  * **Fungsi**: Sumber data batch primer berisi master 5.282 bandara komersial aktif di dunia (kode ICAO/IATA, nama bandara, elevasi, koordinat) untuk proses join enrichment.
* **Redpanda** (Streaming Broker C++ / Kafka-Compatible)
  * **Fungsi**: Message broker berkinerja tinggi untuk menampung event stream pesawat ke topic `flight-raw-stream`. Digunakan sebagai alternatif Apache Kafka yang ramah memori (~512MB RAM) tanpa dependensi JVM/ZooKeeper.

---

### 2. Processing, Quality Gate & Medallion Storage (Pengolahan & Penyimpanan)
* **Python Ingestion & Consumer Engine**
  * **Fungsi**: 
    1. **Deduplikasi**: Memfilter pesan duplikat berdasarkan hash unik SHA-256 (`icao24 + timestamp`).
    2. **Event-Time vs Processing-Time**: Memisahkan timestamp sensor pesawat dengan waktu ingest sistem.
    3. **Quality Gate**: Validasi null check, verifikasi rentang koordinat bumi, serta mengalihkan data rusak ke Dead Letter Queue (DLQ).
    4. **Geospasial Haversine**: Menghitung jarak sisa penerbangan ke bandara tujuan.
* **PostgreSQL 15** (Relational & Serving Marts)
  * **Fungsi**: Menyimpan data matang yang terstruktur pada layer Silver (data bersih) dan Gold (mart penerbangan aktif `gold.active_flights_mart` dan agregasi wilayah).
* **Parquet** (Columnar Storage Format)
  * **Fungsi**: Format penyimpanan kolumnar terkompresi di layer Bronze/Gold untuk efisiensi kueri analitik dan feeding dataset Machine Learning.

---

### 3. Machine Learning & Experiment Tracking (Kecerdasan Buatan)
* **Scikit-Learn**
  * **Fungsi**: 
    - Melatih model **Eksperimen 1 (Baseline)** dengan algoritma *Ridge Regression* (MAE: 5.14 m, RMSE: 6.62 m).
    - Melatih model **Eksperimen 2 (Retrained Candidate)** dengan *RandomForestRegressor* (MAE: 3.27 m, RMSE: 4.04 m) dengan peningkatan akurasi 38.88%.
* **MLflow / Structured JSON Tracking**
  * **Fungsi**: Melacak versioning model (v1 vs v2), menyimpan artefak `.pkl`, serta mencatat metrik evaluasi pada fixed test set bebas data leakage.

---

### 4. Serving Layer & User Interface (Penyajian Data)
* **FastAPI** (Python High-Performance REST API)
  * **Fungsi**: Menyediakan endpoint query data mart bandara/pesawat, healthcheck sistem, serta endpoint online inference `POST /api/v1/ml/predict-delay` untuk estimasi keterlambatan.
* **React + Vite** (Modern Frontend UI)
  * **Fungsi**: Cockpit dashboard radar bertema dark mode untuk memvisualisasikan telemetri pesawat, 4 kartu KPI bisnis, tabel radar pencarian bandara, serta kalkulator uji coba model ML langsung di browser.
* **Lucide React**
  * **Fungsi**: Library ikon grafis visual untuk cockpit dashboard (radar, kompas, speedometer, status live).

---

### 5. DevOps, Testing & Observability (Infrastruktur & Pengujian)
* **Docker Compose**
  * **Fungsi**: Orkestrator kontainerisasi lokal untuk menjalankan Redpanda dan PostgreSQL secara terisolasi dengan persistent volume storage.
* **Python Unittest**
  * **Fungsi**: Pengujian otomatis (automated unit testing) untuk memvalidasi fungsi matematika jarak dan aturan Quality Gate dengan coverage >= 40%.
* **Prometheus & Grafana**
  * **Fungsi**: Monitoring metrik infrastruktur (CPU/RAM, stream lag, service health) dan manajemen 3 aturan alert sistem.
