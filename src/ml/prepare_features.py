"""Feature preparation from the Gold mart (F-11).

The dataset is built exclusively from real BTS on-time records joined to real OurAirports
coordinates. No synthetic rows and no formula-generated target values are used.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pandas as pd

from src.common.config import DATA_GOLD_DIR, GOLD_DIR

FEATURES = [
    "distance_km", "hour_of_day", "day_of_week", "month",
    "dep_delay_min", "taxi_out_min", "crs_elapsed_min",
]
TARGET = "arr_delay_min"
FEATURE_PATH = GOLD_DIR / "flight_delay_features.parquet"


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def dataset_version() -> str:
    if not FEATURE_PATH.exists():
        return "unavailable"
    return hashlib.sha256(FEATURE_PATH.read_bytes()).hexdigest()[:16]


def generate_flight_ml_dataset(n_samples: int | None = None, random_seed: int = 42) -> pd.DataFrame:
    """Backward-compatible entry point. Loads the real Gold mart; never generates data."""
    if not FEATURE_PATH.exists():
        from src.batch.transform import run_transform
        run_transform()
    frame = pd.read_parquet(FEATURE_PATH)
    needed = set(FEATURES + [TARGET, "flight_record_id"])
    missing = needed - set(frame.columns)
    if missing:
        raise ValueError(f"Gold feature mart is missing columns: {sorted(missing)}")
    frame = frame.dropna(subset=FEATURES + [TARGET]).reset_index(drop=True)
    if n_samples is not None and 0 < n_samples < len(frame):
        frame = frame.sample(n=n_samples, random_state=random_seed).reset_index(drop=True)
    print(f"[INFO] Loaded {len(frame)} real flight records from {FEATURE_PATH}")
    return frame


if __name__ == "__main__":
    df = generate_flight_ml_dataset()
    print(df[FEATURES + [TARGET]].describe().to_string())
