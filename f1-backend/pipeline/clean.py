"""
pipeline/clean.py — Telemetry cleaning, deduplication, and imputation.

Prepares validated telemetry for enrichment. Shared between batch and streaming.
[DE] Data Engineering
"""

from __future__ import annotations

import pandas as pd


def clean_telemetry(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cleans telemetry data:
    1. Deduplicates on (car_number, sensor_timestamp).
    2. Sorts chronologically per car.
    3. Forward-fills any non-critical gaps and marks quality_flag='imputed'.
    4. Ensures quality_flag defaults to 'ok'.
    """
    if df.empty:
        return df

    cleaned = df.copy()

    # Drop any remaining duplicates
    cleaned = cleaned.drop_duplicates(subset=["car_number", "sensor_timestamp"], keep="first")

    # Sort
    cleaned["sensor_timestamp"] = pd.to_datetime(cleaned["sensor_timestamp"], utc=True)
    cleaned = cleaned.sort_values(by=["car_number", "sensor_timestamp"]).reset_index(drop=True)

    if "quality_flag" not in cleaned.columns:
        cleaned["quality_flag"] = "ok"
    else:
        cleaned["quality_flag"] = cleaned["quality_flag"].fillna("ok")

    # Fill any nullable extension channels with defaults if needed
    if "gear" in cleaned.columns:
        cleaned["gear"] = cleaned["gear"].fillna(1).astype(int)
    if "lap_number" in cleaned.columns:
        cleaned["lap_number"] = cleaned["lap_number"].fillna(1).astype(int)
    if "compound" in cleaned.columns:
        cleaned["compound"] = cleaned["compound"].fillna("MEDIUM")
    if "tyre_age_laps" in cleaned.columns:
        cleaned["tyre_age_laps"] = cleaned["tyre_age_laps"].fillna(0).astype(int)

    return cleaned
