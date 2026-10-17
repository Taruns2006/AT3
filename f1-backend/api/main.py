"""
api/main.py — FastAPI application entry point.

Serves REST endpoints and high-frequency WebSocket streams for the F1 telemetry pipeline.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import health, leaderboard, prediction, quality, races, telemetry, ws

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
log = logging.getLogger("api_main")

app = FastAPI(
    title="F1 Telemetry Real-Time Pipeline API",
    description="High-frequency telemetry pipeline with Cassandra, XGBoost ML, and WebSocket streaming.",
    version="1.0.0",
)

# ── CORS Middleware ──────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Router Registration ──────────────────────────────────────────────────────
app.include_router(health.router, prefix="/api")
app.include_router(races.router, prefix="/api")
app.include_router(telemetry.router, prefix="/api")
app.include_router(prediction.router, prefix="/api")
app.include_router(leaderboard.router, prefix="/api")
app.include_router(quality.router, prefix="/api")
app.include_router(ws.router)

# ── Serve Frontend Static Files ─────────────────────────────────────────────
frontend_dir = ROOT.parent / "f1-frontend"
if frontend_dir.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
else:
    @app.get("/")
    def root():
        return {
            "title": "F1 Telemetry Real-Time Pipeline API",
            "docs": "/docs",
            "health": "/api/health",
            "races": "/api/races",
        }
