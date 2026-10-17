-- ============================================================
-- F1 Telemetry — Sample Queries
-- Run these in cqlsh after applying schema.cql
-- ============================================================

USE f1_telemetry;

-- ── 1. List all races ─────────────────────────────────────
SELECT race_id, name, status, laps_total FROM races;

-- ── 2. List cars in a specific race ──────────────────────
SELECT car_number, driver, team FROM cars WHERE race_id = 'R001';

-- ── 3. Latest telemetry for a car (single row read) ──────
SELECT * FROM telemetry_latest
WHERE race_id = 'R001' AND car_number = 44;

-- ── 4. Last 60 seconds of telemetry (history endpoint) ───
-- At 20 Hz, 60 s = 1200 rows. LIMIT 1200 is used in production.
-- lap_bucket must be computed from current lap in application code.
SELECT sensor_timestamp, speed_kmh, rpm, throttle_pct,
       brake_temp_c, tire_temp_c, tire_wear_pct,
       g_force_lat, g_force_long, quality_flag
FROM telemetry
WHERE race_id = 'R001' AND car_number = 44 AND lap_bucket = 2
  AND sensor_timestamp >= '2026-10-16T14:00:00.000Z'
ORDER BY sensor_timestamp DESC
LIMIT 1200;

-- ── 5. Lap summary for a car ─────────────────────────────
SELECT lap_number, lap_time_ms, avg_speed_kmh, tire_wear_pct,
       compound, pit_flag, completed_at
FROM lap_summary
WHERE race_id = 'R001' AND car_number = 44
LIMIT 20;

-- ── 6. Counter values for leaderboard ────────────────────
SELECT car_number, laps, pit_stops, total_pit_ms
FROM race_car_counters
WHERE race_id = 'R001';

-- ── 7. Latest prediction for a car ───────────────────────
SELECT generated_at, pit_needed_within_3_laps, probability,
       confidence, estimated_laps_to_pit, level, model_version
FROM predictions
WHERE race_id = 'R001' AND car_number = 44
LIMIT 1;

-- ── 8. Data quality summary ───────────────────────────────
SELECT rows_in, rows_out, quarantined, pct_by_reason, run_at
FROM quality_summary
WHERE race_id = 'R001';

-- ── 9. Quarantine records (inspect dirty data) ───────────
SELECT car_number, sensor_timestamp, reason_code, raw_payload
FROM quarantine
WHERE race_id = 'R001' AND car_number = 44
LIMIT 20;

-- ── 10. Partition token (showcase: prove data locality) ──
SELECT token(race_id, car_number, lap_bucket),
       race_id, car_number, lap_bucket
FROM telemetry
WHERE race_id = 'R001' AND car_number = 44 AND lap_bucket = 0
LIMIT 1;

-- ── 11. Row count per partition (approximate) ────────────
-- (Run this in cqlsh to demonstrate partition growth)
SELECT race_id, car_number, lap_bucket, COUNT(*)
FROM telemetry
WHERE race_id = 'R001' AND car_number = 44 AND lap_bucket = 0;

-- ── 12. Tunable consistency demo ─────────────────────────
-- Run in cqlsh:
CONSISTENCY ONE;
SELECT * FROM telemetry_latest WHERE race_id = 'R001' AND car_number = 44;

CONSISTENCY QUORUM;
SELECT * FROM telemetry_latest WHERE race_id = 'R001' AND car_number = 44;
