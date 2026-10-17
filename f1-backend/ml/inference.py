"""
ml/inference.py — Real-time inference engine for pit stop predictions.

Loads the champion XGBoost model and delivers low-latency predictions
for REST and WebSocket consumers.
[ML] Machine Learning
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import joblib

from ml.features import build_single_inference_vector

log = logging.getLogger("ml_inference")

_model = None
_metadata = None


def load_model() -> Any:
    global _model, _metadata
    if _model is not None:
        return _model

    model_path = ROOT / "ml" / "models" / "xgb_pit_classifier.joblib"
    meta_path = ROOT / "ml" / "models" / "model_metadata.json"

    if model_path.exists():
        try:
            _model = joblib.load(model_path)
            if meta_path.exists():
                _metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            log.info(f"Loaded ML model from {model_path}")
        except Exception as exc:
            log.warning(f"Could not load ML model: {exc}")

    return _model


def predict_pit_stop(telemetry_row: dict) -> dict:
    """
    Computes pit stop prediction from a telemetry dictionary:
    Returns {
        "race_id": str,
        "car_number": int,
        "pit_needed_within_3_laps": bool,
        "probability": float,
        "confidence": "low" | "medium" | "high",
        "estimated_laps_to_pit": int,
        "level": "green" | "amber" | "red",
        "model_version": str,
        "generated_at": datetime,
    }
    """
    model = load_model()
    wear = float(telemetry_row.get("tire_wear_pct", 0.0))
    wear_rate = max(0.5, float(telemetry_row.get("tire_wear_rate", 2.2)))

    # Fallback heuristic if model is not yet loaded
    if model is None:
        prob = min(1.0, max(0.0, (wear - 30.0) / 45.0))
    else:
        try:
            X = build_single_inference_vector(telemetry_row)
            if hasattr(model, "predict_proba"):
                prob = float(model.predict_proba(X)[0][1])
            else:
                prob = float(model.predict(X)[0])
        except Exception as exc:
            log.warning(f"Model prediction error: {exc}")
            prob = min(1.0, max(0.0, (wear - 30.0) / 45.0))

    prob = round(float(prob), 4)
    pit_needed = prob >= 0.50

    # Severity level for UI color coding
    if prob >= 0.70 or wear >= 65.0:
        level = "red"
    elif prob >= 0.40 or wear >= 45.0:
        level = "amber"
    else:
        level = "green"

    # Confidence rating
    if prob >= 0.85 or prob <= 0.15:
        confidence = "high"
    elif prob >= 0.65 or prob <= 0.35:
        confidence = "medium"
    else:
        confidence = "low"

    # Estimated laps to pit
    remaining_wear = max(0.0, 68.0 - wear)
    est_laps = max(1, int(round(remaining_wear / wear_rate)))

    return {
        "race_id": telemetry_row.get("race_id", "R001"),
        "car_number": int(telemetry_row.get("car_number", 1)),
        "generated_at": datetime.now(UTC),
        "pit_needed_within_3_laps": pit_needed,
        "probability": prob,
        "confidence": confidence,
        "estimated_laps_to_pit": est_laps,
        "level": level,
        "model_version": _metadata.get("version", "1.0.0") if _metadata else "1.0.0",
    }
