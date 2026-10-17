"""
tests/test_ml.py — Unit tests for ML features and pit stop inference.
"""

from __future__ import annotations

from ml.features import build_single_inference_vector
from ml.inference import predict_pit_stop


def test_build_inference_vector():
    row = {
        "tire_wear_pct": 65.0,
        "tire_temp_c": 105.0,
        "brake_temp_c": 550.0,
        "speed_kmh": 280.0,
        "rpm": 11500,
        "throttle_pct": 100.0,
        "g_force_lat": -3.5,
        "tire_wear_rate": 2.5,
        "tyre_age_laps": 15,
        "lap_number": 20,
    }
    df = build_single_inference_vector(row)
    assert df.shape == (1, 10)
    assert df["g_force_lat_abs"].iloc[0] == 3.5


def test_predict_pit_stop_structure():
    row = {
        "race_id": "R001",
        "car_number": 1,
        "tire_wear_pct": 72.0,
        "tire_wear_rate": 3.0,
        "lap_number": 18,
    }
    pred = predict_pit_stop(row)
    assert "pit_needed_within_3_laps" in pred
    assert "probability" in pred
    assert "confidence" in pred
    assert pred["confidence"] in ("low", "medium", "high")
    assert "level" in pred
    assert pred["level"] in ("green", "amber", "red")
    assert "estimated_laps_to_pit" in pred
    assert pred["level"] == "red"  # wear >= 65% should trigger red
