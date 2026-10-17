"""
api/routes/leaderboard.py — Live race standings and counter aggregation.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.database import get_leaderboard

router = APIRouter(tags=["Leaderboard"])


@router.get("/races/{race_id}/leaderboard")
def get_race_leaderboard(race_id: str):
    """
    Returns current race leaderboard.
    Reads from counter tables and lap summaries, sorted by laps DESC, best_lap ASC.
    """
    return get_leaderboard(race_id)
