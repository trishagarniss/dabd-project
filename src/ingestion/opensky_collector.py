"""
OpenSky Network API Collector & Stream Producer
Menarik data state vector dari OpenSky API dan memformatnya dengan event_id, event_time, & ingest_time.
Sesuai requirement F-04 & F-05:
- event_id unik (hash icao24 + time_position)
- event_time vs ingest_time
"""

import time
import json
import hashlib
import requests
from datetime import datetime, timezone

# URL API OpenSky (endpoint publik untuk live states)
OPENSKY_URL = "https://opensky-network.org/api/states/all"

def fetch_opensky_states(bounding_box=None):
    """
    Fetch state vectors dari OpenSky.
    Optional bounding_box: [lamin, lomin, lamax, lomax]
    Contoh area Indonesia & sekitarnya: [-11.0, 95.0, 6.0, 141.0]
    """
    params = {}
    if bounding_box:
        params = {
            "lamin": bounding_box[0],
            "lomin": bounding_box[1],
            "lamax": bounding_box[2],
            "lomax": bounding_box[3]
        }
    
    headers = {"User-Agent": "AcademicDataPlatform/1.0"}
    try:
        response = requests.get(OPENSKY_URL, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[ERROR] Gagal fetch dari OpenSky API: {e}")
        return None

def parse_state_vector(raw_vector, server_time):
    """
    OpenSky state vector format:
    0: icao24, 1: callsign, 2: origin_country, 3: time_position, 4: last_contact,
    5: longitude, 6: latitude, 7: baro_altitude, 8: on_ground, 9: velocity,
    10: true_track, 11: vertical_rate, 12: sensors, 13: geo_altitude, 14: squawk,
    15: spi, 16: position_source
    """
    icao24 = raw_vector[0]
    time_pos = raw_vector[3] or raw_vector[4] or server_time
    callsign = raw_vector[1].strip() if raw_vector[1] else "UNKNOWN"
    
    # Generate unique event_id (F-04 requirement)
    event_raw_id = f"{icao24}_{time_pos}"
    event_id = hashlib.sha256(event_raw_id.encode('utf-8')).hexdigest()[:16]
    
    ingest_time = datetime.now(timezone.utc).isoformat()
    event_time = datetime.fromtimestamp(time_pos, tz=timezone.utc).isoformat()

    return {
        "event_id": event_id,
        "payload_version": "1.0",
        "icao24": icao24,
        "callsign": callsign,
        "origin_country": raw_vector[2],
        "time_position": raw_vector[3],
        "last_contact": raw_vector[4],
        "longitude": raw_vector[5],
        "latitude": raw_vector[6],
        "baro_altitude": raw_vector[7],
        "on_ground": raw_vector[8],
        "velocity": raw_vector[9],
        "true_track": raw_vector[10],
        "vertical_rate": raw_vector[11],
        "geo_altitude": raw_vector[13],
        "event_time": event_time,
        "ingest_time": ingest_time
    }

if __name__ == "__main__":
    print("[INFO] Menguji koneksi ke OpenSky Network API...")
    # Bounding box Asia Tenggara / Indonesia untuk mengurangi beban data & rate limit
    INDONESIA_BBOX = [-11.0, 95.0, 6.0, 141.0]
    
    data = fetch_opensky_states(bounding_box=INDONESIA_BBOX)
    if data and "states" in data and data["states"]:
        server_time = data.get("time", int(time.time()))
        sample_raw = data["states"][0]
        parsed = parse_state_vector(sample_raw, server_time)
        print(f"[SUCCESS] Berhasil mengambil {len(data['states'])} pesawat di wilayah pantauan!")
        print(f"[SAMPLE EVENT]:\n{json.dumps(parsed, indent=2)}")
    else:
        print("[WARN] Tidak ada data pesawat saat ini atau kena limit.")
