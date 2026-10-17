"""
api/routes/quality.py — Data quality report endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.database import get_quality

router = APIRouter(tags=["Data Quality"])


@router.get("/races/{race_id}/quality")
def get_race_quality(race_id: str):
    """Returns data quality breakdown (rows in, out, quarantined, reason percentages)."""
    return get_quality(race_id)
