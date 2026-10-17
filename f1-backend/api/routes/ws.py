"""
api/routes/ws.py — High-frequency WebSocket streaming endpoint.

Streams telemetry at ~10 Hz, predictions at ~1 Hz, leaderboard at ~0.5 Hz,
and quality summaries at ~0.1 Hz to the frontend dashboard.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.database import (
    get_cars,
    get_latest_telemetry,
    get_leaderboard,
    get_prediction,
    get_quality,
)

log = logging.getLogger("api_ws")
router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/telemetry")
@router.websocket("/ws/{race_id}")
async def websocket_telemetry_endpoint(websocket: WebSocket, race_id: str = "R001"):
    await websocket.accept()
    log.info(f"WebSocket client connected for race {race_id}")

    selected_car = 1
    cars = get_cars(race_id)
    if cars:
        selected_car = cars[0]["car_number"]

    loop_count = 0
    try:
        while True:
            # Check for non-blocking client messages (e.g. changing car_number)
            try:
                msg_text = await asyncio.wait_for(websocket.receive_text(), timeout=0.01)
                data = json.loads(msg_text)
                if "car_number" in data:
                    selected_car = int(data["car_number"])
                if "race_id" in data:
                    race_id = str(data["race_id"])
            except TimeoutError:
                pass
            except json.JSONDecodeError:
                pass

            # 1. Telemetry stream (every 100 ms = 10 Hz)
            tel = get_latest_telemetry(race_id, selected_car)
            if tel:
                # Ensure ISO-8601 serializable
                if hasattr(tel.get("sensor_timestamp"), "isoformat"):
                    tel["sensor_timestamp"] = tel["sensor_timestamp"].isoformat()
                await websocket.send_json(
                    {
                        "type": "telemetry",
                        "data": tel,
                    }
                )

            # 2. Prediction stream (every 1 s = 1 Hz)
            if loop_count % 10 == 0:
                pred = get_prediction(race_id, selected_car)
                if hasattr(pred.get("generated_at"), "isoformat"):
                    pred["generated_at"] = pred["generated_at"].isoformat()
                await websocket.send_json(
                    {
                        "type": "prediction",
                        "data": pred,
                    }
                )

            # 3. Leaderboard stream (every 2 s = 0.5 Hz)
            if loop_count % 20 == 0:
                lb = get_leaderboard(race_id)
                await websocket.send_json(
                    {
                        "type": "leaderboard",
                        "data": lb,
                    }
                )

            # 4. Quality stream (every 10 s = 0.1 Hz)
            if loop_count % 100 == 0:
                q = get_quality(race_id)
                await websocket.send_json(
                    {
                        "type": "quality",
                        "data": q,
                    }
                )

            loop_count += 1
            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        log.info(f"WebSocket client disconnected for race {race_id}")
    except Exception as exc:
        log.warning(f"WebSocket streaming error: {exc}")
