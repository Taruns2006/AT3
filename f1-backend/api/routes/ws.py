import asyncio
import random
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from api import database

router = APIRouter()

# Global race state for live WebSocket streaming
state = {
    "lap": 1,
    "last_update": time.time(),
    "stint_lap": 1
}

def get_live_tick(race_id="monza_2026", car_number=1):
    now = time.time()
    # Advance lap every 10 seconds
    if now - state["last_update"] > 10:
        state["lap"] = (state["lap"] % 53) + 1
        state["stint_lap"] = ((state["lap"] - 1) % 18) + 1
        state["last_update"] = now

    current_lap = state["lap"]
    stint_lap = state["stint_lap"]
    
    # Tyre wear increases gradually with lap count
    tyre_wear = min(98.5, round((stint_lap * 5.1) + random.uniform(0.1, 0.8), 1))
    tyre_temp = round(random.uniform(94.0, 107.0), 1)
    brake_temp = round(random.uniform(490.0, 680.0), 1)
    
    speed_val = random.randint(288, 342)
    rpm_val = random.randint(11900, 14750)
    throttle_val = round(random.uniform(80.0, 100.0), 1)
    
    # Lateral & Longitudinal G-Forces for G-G Diagram
    g_lat_val = round(random.uniform(-3.6, 3.6), 2)
    g_lon_val = round(random.uniform(-4.1, 2.3), 2)

    # Pitstop Prediction logic
    predicted_pit_lap = (((current_lap - 1) // 18) + 1) * 18
    laps_remaining = max(1, predicted_pit_lap - current_lap)
    
    if tyre_wear > 70.0:
        action = "BOX THIS LAP — PIT WINDOW OPEN"
        recommended_tyre = "HARD"
        confidence = 0.95
    else:
        action = "STAY OUT — TYRES NOMINAL"
        recommended_tyre = "MEDIUM"
        confidence = 0.89

    stint_pct = min(100, int((tyre_wear / 80.0) * 100))

    # Comprehensive payload supplying all key formats expected by dashboard.js
    return {
        "race_id": race_id,
        "car_number": int(car_number) if car_number else 1,
        "timestamp": int(time.time() * 1000),
        
        # Telemetry metrics (dual keys for camelCase and snake_case compatibility)
        "speed": speed_val,
        "speed_kmh": speed_val,
        "speedKmh": speed_val,
        "rpm": rpm_val,
        "throttle": throttle_val,
        "throttle_pct": throttle_val,
        "throttlePct": throttle_val,
        
        "tyre_wear": tyre_wear,
        "tyreWear": tyre_wear,
        "tyre_wear_pct": tyre_wear,
        "tyreWearPct": tyre_wear,
        
        "tyre_temp": tyre_temp,
        "tyreTemp": tyre_temp,
        "tyre_temp_c": tyre_temp,
        "tyreTempC": tyre_temp,
        
        "brake_temp": brake_temp,
        "brakeTemp": brake_temp,
        "brake_temp_c": brake_temp,
        "brakeTempC": brake_temp,
        
        "g_lat": g_lat_val,
        "gLat": g_lat_val,
        "lat_g": g_lat_val,
        "latG": g_lat_val,
        "g_lon": g_lon_val,
        "gLon": g_lon_val,
        "lon_g": g_lon_val,
        "lonG": g_lon_val,
        
        "lap": current_lap,
        "current_lap": current_lap,
        "currentLap": current_lap,
        "lap_number": current_lap,
        
        # Embedded prediction data for live widget updates
        "prediction": {
            "action": action,
            "recommendation": action,
            "confidence": confidence,
            "confidence_pct": int(confidence * 100),
            "predicted_pit_lap": predicted_pit_lap,
            "laps_remaining": laps_remaining,
            "recommended_tyre": recommended_tyre,
            "stint_progress": stint_pct,
            "recent_predictions": [
                {"action": "STAY OUT", "confidence": 89, "prob": 89, "type": "STAY", "label": "STAY OUT (89%)"},
                {"action": "STAY OUT", "confidence": 87, "prob": 87, "type": "STAY", "label": "STAY OUT (87%)"},
                {"action": "STAY OUT", "confidence": 85, "prob": 85, "type": "STAY", "label": "STAY OUT (85%)"}
            ]
        },
        
        # Embedded quality metrics
        "quality": {
            "status": "ok",
            "quality_score": 99.2,
            "rows_in": 15420,
            "rows_out": 15400,
            "quarantined": 20,
            "reasons": {"schema_mismatch": 12, "out_of_bounds": 8},
            "by_reason": [
                {"reason": "Schema Mismatch", "count": 12},
                {"reason": "Out of Bounds", "count": 8}
            ]
        }
    }

@router.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket, race_id: str = "monza_2026", car_number: int = 1):
    await websocket.accept()
    try:
        while True:
            data = get_live_tick(race_id, car_number)
            await websocket.send_json(data)
            await asyncio.sleep(0.5)  # Send tick every 500ms
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
