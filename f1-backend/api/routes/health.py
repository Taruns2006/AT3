"""
api/routes/health.py — Health check endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.database import get_health

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    """Returns cluster connectivity, model status, and service health."""
    return get_health()
