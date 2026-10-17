"""
api/routes/races.py — Race and car roster endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.database import get_cars, get_races

router = APIRouter(tags=["Races"])


@router.get("/races")
def list_races():
    """List all available races in the system."""
    return get_races()


@router.get("/races/{race_id}/cars")
def list_cars_for_race(race_id: str):
    """List all cars and drivers competing in the specified race."""
    cars = get_cars(race_id)
    if not cars:
        # Fallback to general roster if race_id not found in DB
        cars = get_cars("R001")
    return cars
