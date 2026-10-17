"""
tests/test_pipeline.py — Unit tests for data engineering pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from pipeline.enrich import enrich_telemetry
from pipeline.validate import validate_telemetry_batch


def test_validation_out_of_range():
    data = [
        {
            "race_id": "R001",
            "car_number": 1,
            "sensor_timestamp": datetime.now(UTC),
            "speed_kmh": 450.0,  # Invalid: > 380
            "rpm": 12000,
            "throttle_pct": 100.0,
            "brake_temp_c": 500.0,
            "tire_temp_c": 100.0,
            "tire_wear_pct": 10.0,
            "g_force_lat": 1.5,
            "g_force_long": 0.5,
        }
    ]
    df = pd.DataFrame(data)
    valid_df, quarantine, rejections = validate_telemetry_batch(df, "R001")
    assert len(valid_df) == 0
    assert len(quarantine) == 1
    assert quarantine[0]["reason_code"] == "out_of_range"
    assert rejections["out_of_range"] == 1


def test_validation_duplicates():
    ts = datetime.now(UTC)
    data = [
        {
            "race_id": "R001",
            "car_number": 1,
            "sensor_timestamp": ts,
            "speed_kmh": 200.0,
            "rpm": 10000,
            "throttle_pct": 80.0,
            "brake_temp_c": 400.0,
            "tire_temp_c": 90.0,
            "tire_wear_pct": 20.0,
            "g_force_lat": 1.0,
            "g_force_long": 0.0,
        },
        {
            "race_id": "R001",
            "car_number": 1,
            "sensor_timestamp": ts,  # Duplicate
            "speed_kmh": 200.0,
            "rpm": 10000,
            "throttle_pct": 80.0,
            "brake_temp_c": 400.0,
            "tire_temp_c": 90.0,
            "tire_wear_pct": 20.0,
            "g_force_lat": 1.0,
            "g_force_long": 0.0,
        },
    ]
    df = pd.DataFrame(data)
    valid_df, quarantine, rejections = validate_telemetry_batch(df, "R001")
    assert len(valid_df) == 1
    assert len(quarantine) == 1
    assert quarantine[0]["reason_code"] == "duplicate"


def test_enrichment_lap_bucket_and_features():
    ts = datetime.now(UTC)
    data = [
        {
            "race_id": "R001",
            "car_number": 1,
            "sensor_timestamp": ts,
            "lap_number": 12,
            "speed_kmh": 200.0,
            "rpm": 10000,
            "throttle_pct": 80.0,
            "brake_temp_c": 400.0,
            "tire_temp_c": 90.0,
            "tire_wear_pct": 20.0,
            "g_force_lat": 2.5,
            "g_force_long": 0.0,
        }
    ]
    df = pd.DataFrame(data)
    enriched = enrich_telemetry(df)
    assert enriched["lap_bucket"].iloc[0] == 2  # 12 // 5 = 2
    assert "sector" in enriched.columns
    assert "brake_temp_delta" in enriched.columns
    assert "cumulative_g" in enriched.columns
