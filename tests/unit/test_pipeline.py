"""
Unit Tests untuk Pipeline & Quality Gate (F-18 Requirement: Coverage >= 40%)
Menggunakan built-in standard unittest agar tidak bergantung pada third-party runner.
"""

import unittest
from src.streaming.stream_consumer import validate_quality_gate
from src.ml.prepare_features import haversine_distance

class TestFlightPipeline(unittest.TestCase):

    def test_haversine_distance(self):
        # Jarak Jakarta (CGK) ke Surabaya (SUB) ~ 690 km
        lat_cgk, lon_cgk = -6.1256, 106.6559
        lat_sub, lon_sub = -7.3798, 112.7874
        dist = haversine_distance(lat_cgk, lon_cgk, lat_sub, lon_sub)
        self.assertTrue(650 < dist < 730, f"Perhitungan jarak tidak akurat: {dist} km")

    def test_quality_gate_valid_event(self):
        valid_event = {
            "icao24": "e084e7",
            "callsign": "GIA123",
            "latitude": -6.2,
            "longitude": 106.8,
            "baro_altitude": 10500.0
        }
        is_valid, reasons = validate_quality_gate(valid_event)
        self.assertTrue(is_valid)
        self.assertEqual(len(reasons), 0)

    def test_quality_gate_invalid_coordinates(self):
        # Latitude 120 melebihi batas bumi (-90 s/d 90)
        invalid_event = {
            "icao24": "e084e7",
            "callsign": "GIA123",
            "latitude": 120.0,
            "longitude": 106.8,
            "baro_altitude": 5000.0
        }
        is_valid, reasons = validate_quality_gate(invalid_event)
        self.assertFalse(is_valid)
        self.assertTrue(any("coordinate range" in r.lower() for r in reasons))

    def test_quality_gate_missing_icao(self):
        invalid_event = {
            "latitude": -6.2,
            "longitude": 106.8,
            "baro_altitude": 5000.0
        }
        is_valid, reasons = validate_quality_gate(invalid_event)
        self.assertFalse(is_valid)
        self.assertIn("Missing icao24", reasons)

if __name__ == "__main__":
    unittest.main()
