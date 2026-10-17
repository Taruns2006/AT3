"""
api/routes/prediction.py — ML pit stop prediction endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.database import get_prediction

router = APIRouter(tags=["ML Prediction"])


@router.get("/races/{race_id}/cars/{car_number}/prediction")
def get_car_prediction(race_id: str, car_number: int):
    """Returns real-time ML pit stop prediction with confidence and severity level."""
    return get_prediction(race_id, car_number)
