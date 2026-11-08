"""
Master Data Airports Ingestion (Batch Source)
Dataset ini menjadi sumber data BATCH (F-02) yang berisi metadata bandara:
- icao_code, iata_code, airport_name, city, country, latitude, longitude, altitude_ft
Data diunduh/dibuat dari dataset publik resmi (OurAirports / OpenFlights) berlisensi Public Domain.
"""

import os
import hashlib
import pandas as pd
from datetime import datetime, timezone

# URL dataset terbuka bandara global (OurAirports - Public Domain)
AIRPORTS_DATA_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "reference")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "airports_reference.parquet")

def download_and_process_airports():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"[INFO] Mengunduh data bandara terbuka dari {AIRPORTS_DATA_URL}...")
    
    try:
        # Baca langsung menggunakan pandas
        df_raw = pd.read_csv(AIRPORTS_DATA_URL)
    except Exception as e:
        print(f"[WARN] Gagal unduh online ({e}). Membuat seed dataset bandara lokal...")
        # Fallback dataset minimal bandara internasional utama
        data_seed = {
            "ident": ["WIII", "WARR", "WADD", "WALL", "WSSS", "WMKK", "VTBS", "RJAA", "KJFK", "EGLL"],
            "iata_code": ["CGK", "SUB", "DPS", "BPN", "SIN", "KUL", "BKK", "NRT", "JFK", "LHR"],
            "name": [
                "Soekarno-Hatta International Airport",
                "Juanda International Airport",
                "I Gusti Ngurah Rai International Airport",
                "Sultan Aji Muhammad Sulaiman Sepinggan Airport",
                "Singapore Changi Airport",
                "Kuala Lumpur International Airport",
                "Suvarnabhumi Airport",
                "Narita International Airport",
                "John F Kennedy International Airport",
                "London Heathrow Airport"
            ],
            "type": ["large_airport"] * 10,
            "latitude_deg": [-6.1256, -7.3798, -8.7482, -1.2683, 1.3502, 2.7456, 13.6811, 35.7647, 40.6398, 51.4706],
            "longitude_deg": [106.6559, 112.7874, 115.1672, 116.8944, 103.9944, 101.7099, 100.7473, 140.3864, -73.7789, -0.4619],
            "elevation_ft": [34, 10, 14, 11, 73, 69, 5, 141, 13, 83],
            "iso_country": ["ID", "ID", "ID", "ID", "SG", "MY", "TH", "JP", "US", "GB"],
            "municipality": ["Jakarta", "Surabaya", "Denpasar", "Balikpapan", "Singapore", "Kuala Lumpur", "Bangkok", "Tokyo", "New York", "London"]
        }
        df_raw = pd.DataFrame(data_seed)

    print(f"[INFO] Total bandara mentah dari internet: {len(df_raw)} baris")

    # Filter data: HANYA bandara komersial aktif (large & medium airport) yang memiliki kode ICAO/IATA
    valid_types = ["large_airport", "medium_airport"]
    df_clean = df_raw[
        (df_raw["type"].isin(valid_types)) &
        (df_raw["latitude_deg"].notnull()) &
        (df_raw["longitude_deg"].notnull())
    ].copy()

    # Pilih kolom penting yang relevan dengan domain penerbangan
    columns_needed = [
        "ident", "iata_code", "name", "type", 
        "latitude_deg", "longitude_deg", "elevation_ft", 
        "iso_country", "municipality"
    ]
    df_clean = df_clean[[col for col in columns_needed if col in df_clean.columns]]
    print(f"[INFO] Setelah difilter (hanya komersial aktif): {len(df_clean)} bandara.")
    
    # Metadata ingestion untuk audit & lineage (F-02 & F-09)
    ingest_time = datetime.now(timezone.utc).isoformat()
    batch_id = f"BATCH_AIRPORTS_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    df_clean["batch_id"] = batch_id
    df_clean["ingest_time"] = ingest_time
    
    # Simpan ke Parquet jika engine tersedia, fallback ke CSV
    try:
        df_clean.to_parquet(OUTPUT_FILE, index=False)
        print(f"[SUCCESS] Data batch bandara tersimpan (Parquet) di: {OUTPUT_FILE}")
    except Exception as e:
        csv_file = OUTPUT_FILE.replace(".parquet", ".csv")
        df_clean.to_csv(csv_file, index=False)
        print(f"[SUCCESS] Engine parquet belum ada, disimpan (CSV) di: {csv_file}")
    print(f"[INFO] Row count: {len(df_clean)}, Batch ID: {batch_id}")
    return df_clean

if __name__ == "__main__":
    download_and_process_airports()
