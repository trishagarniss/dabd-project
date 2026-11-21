# 📝 NOTULENSI DISKUSI & STANDUP TIM TBP DABD
**Proyek: SkyPulse Analytics Platform (Flight Data Platform)**

---

## 📌 DAFTAR ANGGOTA & PERAN
- **Alvian Damar Budhi Hernowo (L0224014)**: Data Engineer (Infrastruktur, Streaming, API)
- **Stefani Ayudya Prasetyo (L0224011)**: Frontend & Quality Engineer (React Dashboard, Quality Gate, Testing)
- **Trisha Garnis Wahningyun (L0224012)**: Machine Learning Engineer (Feature Store, Training, Retrain, Model Evaluation)
- **Talitha Sukma Mahardika (L0224037)**: Data Architect & Governance (Batch Pipeline, Medallion Storage, ADR & Dokumentasi)

---

## 📅 LOG NOTULENSI PERTEMUAN / STANDUP

### [Pertemuan 01 - Kickoff & Finalisasi Arsitektur]
- **Hari/Tanggal**: Minggu, 08 November 2026
- **Media**: Google Meet / Tatap Muka
- **Peserta Hadir**: Stefani, Trisha, Alvian, Talitha (Lengkap)
- **Agenda Diskusi**:
  1. Sinkronisasi rencana PPT awal dengan lembar rubrik TBP dosen.
  2. Penyesuaian Machine Learning: sepakat menambahkan use case *Prediksi Delay Pesawat* (F-11 & F-12).
  3. Pemilihan Stack Hemat RAM: mengganti NiFi/Spark dengan Redpanda, Postgres, dan FastAPI.
  4. Perubahan UI dari Streamlit menjadi React + Vite untuk dashboard profesional.
- **Hasil & Keputusan**:
  - Sumber stream disepakati: **OpenSky Live API (ASEAN Bounding Box)**.
  - Sumber batch disepakati: **OurAirports Master Database (5.282 bandara komersial)**.
  - Struktur folder proyek di GitHub dan Google Drive resmi dibuat.
- **Action Items (To-Do Sprint Ini)**:
  - [x] Alvian: Setup Docker Compose & script live stream producer.
  - [x] Talitha: Ingest dataset batch bandara & siapkan skema medallion.
  - [x] Trisha: Buat feature store & retrain model ML v1 vs v2.
  - [x] Stefani: Buat UI React cockpit & unit test pipeline.

---

### [Template: Pertemuan Berkala / Sprint Standup]
> *(Salin template di bawah ini untuk setiap kali kelompokmu mengadakan diskusi/standup berikutnya)*

#### Pertemuan [Nomor Pertemuan] - [Topik Pertemuan]
- **Hari/Tanggal**: [Contoh: Rabu, 11 November 2026]
- **Waktu**: [Contoh: 19.30 - 20.30 WIB]
- **Media**: [Google Meet / Discord / Offline Lab]
- **Peserta Hadir**: 
  - [ ] Alvian Damar
  - [ ] Stefani Ayudya
  - [ ] Trisha Garnis
  - [ ] Talitha Sukma
- **Agenda Pembahasan**:
  1. ...
  2. ...
- **Progress Report Tiap Anggota (Apa yang sudah dikerjakan?)**:
  - **Alvian**: ...
  - **Stefani**: ...
  - **Trisha**: ...
  - **Talitha**: ...
- **Kendala / Blocker (Hambatan teknis yang dihadapi)**:
  - ...
- **Keputusan / Action Items untuk Hari Selanjutnya**:
  - [ ] PIC: [Nama] - [Tugas yang harus diselesaikan]
  - [ ] PIC: [Nama] - [Tugas yang harus diselesaikan]
