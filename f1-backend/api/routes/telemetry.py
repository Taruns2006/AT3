"""
api/routes/telemetry.py — Telemetry latest and history endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.database import get_latest_telemetry, get_telemetry_history

router = APIRouter(tags=["Telemetry"])


@router.get("/races/{race_id}/cars/{car_number}/latest")
def get_car_latest(race_id: str, car_number: int):
    """O(1) lookup of latest telemetry reading for a car in a race."""
    data = get_latest_telemetry(race_id, car_number)
    if not data:
        # Fallback to car in default race
        data = get_latest_telemetry("R001", car_number)
    if not data:
        raise HTTPException(status_code=404, detail=f"No telemetry found for car {car_number}")
    return data


@router.get("/races/{race_id}/cars/{car_number}/history")
def get_car_history(
    race_id: str,
    car_number: int,
    seconds: int = Query(60, ge=1, le=600, description="History window in seconds"),
):
    """Fetches historical time-series telemetry over the requested duration."""
    history = get_telemetry_history(race_id, car_number, seconds=seconds)
    if not history:
        history = get_telemetry_history("R001", car_number, seconds=seconds)
    return history
