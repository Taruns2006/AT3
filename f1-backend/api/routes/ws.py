import asyncio
import random
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

# Global race state for continuous live ticking
state = {
    "lap": 1,
    "last_update": time.time(),
}

def get_live_tick(race_id="monza_2026", car_number="1"):
    now = time.time()
    # Advance lap every 10 seconds
    if now - state["last_update"] > 10:
        state["lap"] = (state["lap"] % 53) + 1
        state["last_update"] = now

    current_lap = state["lap"]
    stint_lap = ((current_lap - 1) % 18) + 1
    
    # Tyre wear increases steadily with lap progression
    tyre_wear = min(98.5, round((stint_lap * 5.1) + random.uniform(0.1, 0.8), 1))
    tyre_temp = round(random.uniform(94.0, 107.0), 1)
    brake_temp = round(random.uniform(490.0, 680.0), 1)
    
    speed_val = random.randint(288, 342)
    rpm_val = random.randint(11900, 14750)
    throttle_val = round(random.uniform(80.0, 100.0), 1)
    
    g_lat_val = round(random.uniform(-3.6, 3.6), 2)
    g_lon_val = round(random.uniform(-4.1, 2.3), 2)

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

    try:
        clean_car_num = int(''.join(filter(str.isdigit, str(car_number)))) if car_number else 1
    except ValueError:
        clean_car_num = 1

    return {
        "race_id": str(race_id or "monza_2026"),
        "car_number": clean_car_num,
        "timestamp": int(time.time() * 1000),
        
        # Telemetry metrics
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
        
        # Embedded prediction data
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
        
        # Data Quality
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
async def websocket_telemetry(websocket: WebSocket):
    await websocket.accept()
    query_params = dict(websocket.query_params)
    race_id = query_params.get("race_id", "monza_2026")
    car_number = query_params.get("car_number", "1")
    
    try:
        while True:
            data = get_live_tick(race_id, car_number)
            await websocket.send_json(data)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket streaming error: {e}")
