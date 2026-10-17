# API Contract Diff — Frontend Files vs. Section 9 Spec

> **Rule**: Where the frontend and the spec differ, **the frontend wins**.

## 1. Files Read

| File | Notes |
|------|-------|
| `mock.js` | Stub returning empty arrays — no shape info |
| `api.js` | Stub — function signatures reveal endpoint intent |
| `config.js` | Source of truth for base URLs and thresholds |
| `dashboard.html` | DOM element IDs reveal exact field names |
| `utils.js` | Helper functions reveal exact field names and level strings |
| `state.js` | State keys confirm top-level response fields |

## 2. Confirmed from Frontend (matches Section 9 exactly)

| Item | Source | Value |
|------|--------|-------|
| API_BASE | config.js:12 | http://localhost:8000 |
| WS_BASE | config.js:15 | ws://localhost:8000 |
| HISTORY_SECONDS | config.js:25 | 60 (default) |
| Prediction level values | utils.js:132 | green, amber, red |
| Prediction confidence values | utils.js:141 | low, medium, high |
| Quality endpoint fields | dashboard.html:252-262 | rows_in, rows_out, quarantined, pct_by_reason |
| KPI telemetry fields | dashboard.html:86-115 | speed_kmh, rpm, throttle_pct, tire_wear_pct, tire_temp_c, brake_temp_c, g_force_lat, lap_number |
| total_pit_ms in leaderboard | utils.js:11-17 | In milliseconds, formatted with formatPitTime() |

## 3. Divergences Found and Resolutions

### 3.1 fetchHealth return shape
- Frontend api.js:12: { status: 'ok' } only
- Section 9 spec: {"status":"ok","cassandra":"up","model_loaded":true}
- **Resolution**: Spec is a superset. Backend returns full spec shape. No conflict.

### 3.2 G-force: both axes required
- dashboard.html:109: KPI shows only G-Lat
- charts.js:7: pushGForce() scatter plot exists
- Section 9 spec: both g_force_lat AND g_force_long
- **Resolution**: G-G scatter requires both. Backend returns both fields as per spec.

### 3.3 WebSocket message type strings
- state.js:6-16: latestTelemetry, latestPrediction, leaderboard, quality (JS camelCase keys)
- Section 9 spec: type "telemetry|prediction|leaderboard|quality"
- **Resolution**: WS type strings are "telemetry", "prediction", "leaderboard", "quality" matching spec.

### 3.4 connectionStatus in state.js
- state.js:15: 'live' | 'reconnecting' | 'offline' | 'mock'
- Frontend-only state. Backend does not return this field.

### 3.5 Tire wear thresholds
- config.js: TIRE_WARN_PCT=60, TIRE_DANGER_PCT=80
- Frontend display thresholds only. Backend does not return threshold metadata.

## 4. Summary — Backend Adaptations Required

| # | Adaptation | Reason |
|---|-----------|--------|
| 1 | Return total_pit_ms (integer, milliseconds) in leaderboard | Confirmed by formatPitTime() in utils.js |
| 2 | Return both g_force_lat AND g_force_long in Telemetry | G-G scatter chart in dashboard.html |
| 3 | WS type strings: telemetry, prediction, leaderboard, quality | Matches state.js keys |
| 4 | Health response: full status+cassandra+model_loaded shape | Safe superset of frontend need |

**No other divergences. Section 9 spec is accurate and complete.**

## 5. Frontend API Function to Endpoint Mapping

| api.js function | REST endpoint |
|-----------------|--------------|
| fetchHealth() | GET /api/health |
| fetchRaces() | GET /api/races |
| fetchCars() | GET /api/races/{race_id}/cars |
| fetchLatest() | GET /api/races/{race_id}/cars/{car_number}/latest |
| fetchHistory() | GET /api/races/{race_id}/cars/{car_number}/history?seconds=60 |
| fetchPrediction() | GET /api/races/{race_id}/cars/{car_number}/prediction |
| fetchLeaderboard() | GET /api/races/{race_id}/leaderboard |
| fetchQuality() | GET /api/races/{race_id}/quality |
