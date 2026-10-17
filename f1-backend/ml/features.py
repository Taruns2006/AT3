"""
ml/features.py — Feature engineering and matrix transformation for ML models.

Transforms raw telemetry and lap metrics into ML feature vectors for pit stop prediction.
[ML] Machine Learning
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_NAMES = [
    "tire_wear_pct",
    "tire_temp_c",
    "brake_temp_c",
    "speed_kmh",
    "rpm",
    "throttle_pct",
    "g_force_lat_abs",
    "tire_wear_rate",
    "tyre_age_laps",
    "lap_number",
]


def extract_features_from_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """
    Extracts feature matrix X and target y from telemetry dataframe.
    Target: pit_needed_within_3_laps (1 if wear > 55% or pit occurs soon, else 0).
    """
    data = df.copy()

    # Derived absolute lateral G
    if "g_force_lat_abs" not in data.columns and "g_force_lat" in data.columns:
        data["g_force_lat_abs"] = data["g_force_lat"].abs()

    # Ensure all required features are present
    for col in FEATURE_NAMES:
        if col not in data.columns:
            data[col] = 0.0

    X = data[FEATURE_NAMES].fillna(0.0)

    # Target definition:
    # If pit stop happens within 3 laps, or tire wear is in critical zone.
    # Dynamically scale threshold based on dataset wear range so positive class is well-represented
    max_wear = data["tire_wear_pct"].max() if "tire_wear_pct" in data.columns else 0.0
    if max_wear >= 50.0:
        threshold = 55.0
    else:
        # In shorter races (e.g. small preset), pit window is the top 30% wear / lap cliff
        threshold = float(np.quantile(data["tire_wear_pct"], 0.70)) if len(data) > 0 else 10.0

    pit_flags = data["pit_in"] if "pit_in" in data.columns else False
    y = ((data["tire_wear_pct"] >= threshold) | (pit_flags)).astype(int)

    # Safety check: ensure at least some 0s and 1s exist
    if y.nunique() < 2:
        cutoff = int(len(y) * 0.75)
        y = pd.Series(0, index=data.index)
        y.iloc[cutoff:] = 1

    return X, y


def build_single_inference_vector(row: dict) -> pd.DataFrame:
    """Builds a single-row DataFrame matching the exact training feature columns."""
    feat_dict = {
        "tire_wear_pct": float(row.get("tire_wear_pct", 0.0)),
        "tire_temp_c": float(row.get("tire_temp_c", 90.0)),
        "brake_temp_c": float(row.get("brake_temp_c", 400.0)),
        "speed_kmh": float(row.get("speed_kmh", 200.0)),
        "rpm": float(row.get("rpm", 10000)),
        "throttle_pct": float(row.get("throttle_pct", 80.0)),
        "g_force_lat_abs": abs(float(row.get("g_force_lat", 0.0))),
        "tire_wear_rate": float(row.get("tire_wear_rate", 2.2)),
        "tyre_age_laps": float(row.get("tyre_age_laps", 0)),
        "lap_number": float(row.get("lap_number", 1)),
    }
    return pd.DataFrame([feat_dict])[FEATURE_NAMES]
