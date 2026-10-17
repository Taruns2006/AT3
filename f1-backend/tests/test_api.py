"""
tests/test_api.py — Integration and endpoint tests for FastAPI.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_endpoint():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "cassandra" in data
    assert "model_loaded" in data


def test_races_endpoint():
    res = client.get("/api/races")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["race_id"] == "R001"


def test_cars_endpoint():
    res = client.get("/api/races/R001/cars")
    assert res.status_code == 200
    cars = res.json()
    assert isinstance(cars, list)
    assert len(cars) >= 1
    assert "car_number" in cars[0]
    assert "driver" in cars[0]


def test_latest_telemetry_endpoint():
    res = client.get("/api/races/R001/cars/1/latest")
    assert res.status_code == 200
    tel = res.json()
    assert tel["car_number"] == 1
    assert "speed_kmh" in tel
    assert "tire_wear_pct" in tel
    assert "g_force_lat" in tel
    assert "g_force_long" in tel


def test_history_telemetry_endpoint():
    res = client.get("/api/races/R001/cars/1/history?seconds=10")
    assert res.status_code == 200
    hist = res.json()
    assert isinstance(hist, list)


def test_prediction_endpoint():
    res = client.get("/api/races/R001/cars/1/prediction")
    assert res.status_code == 200
    pred = res.json()
    assert "probability" in pred
    assert "level" in pred
    assert pred["level"] in ("green", "amber", "red")


def test_leaderboard_endpoint():
    res = client.get("/api/races/R001/leaderboard")
    assert res.status_code == 200
    lb = res.json()
    assert isinstance(lb, list)
    assert len(lb) >= 1
    assert "total_pit_ms" in lb[0]
    assert "position" in lb[0]


def test_quality_endpoint():
    res = client.get("/api/races/R001/quality")
    assert res.status_code == 200
    q = res.json()
    assert "rows_in" in q
    assert "rows_out" in q
    assert "quarantined" in q
    assert "pct_by_reason" in q
