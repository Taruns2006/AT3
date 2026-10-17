-- ============================================================
-- F1 Telemetry — Cassandra Schema
-- Keyspace: f1_telemetry
-- Cassandra version: 4.1
-- All statements are idempotent (IF NOT EXISTS).
--
-- DESIGN PHILOSOPHY [AD]
-- Cassandra is a wide-column, partitioned store.  Every table is
-- designed around ONE query (query-first modelling).  There are no
-- JOINs; denormalisation is intentional.
--
-- SimpleStrategy vs NetworkTopologyStrategy [AD]
--   SimpleStrategy  — replication factor applied uniformly;
--     used here (RF=1) for single-node dev.  Simple to configure.
--   NetworkTopologyStrategy — replication per DC; mandatory for
--     multi-DC or production clusters (see docker-compose.cluster.yml
--     and docs/data_model.md for the RF=3 example).
--
-- PARTITION SIZE ANALYSIS [AD]
-- At 20 Hz, a single car over a 2-hour race emits:
--   20 readings/s × 7 200 s = 144 000 rows per partition.
-- Estimated row size:
--   ~8 (timestamp) + ~8 (race_id, car_number UUIDs) +
--   8 numeric doubles × 8 B + 4 ints × 4 B + 2 text flags × ~6 B
--   ≈ 140 bytes per row (rough; snappy compression halves this).
-- Uncompressed partition size: 144 000 × 140 B ≈ 20 MB.
-- Compressed (≈2× ratio): ~10 MB.
-- Cassandra guidance: keep partitions well under 100 MB and 100 k rows.
-- At RF=1, 20 MB fits; at 20 cars × 20 MB = 400 MB total for one race.
-- DECISION: Add a LAP BUCKET to the partition key.
--   Partition key: (race_id, car_number, lap_bucket)
--   where lap_bucket = lap_number DIV 5 (groups of 5 laps).
--   A 50-lap race with 5-lap buckets = 10 buckets per car.
--   Rows per bucket: 144 000 / 10 = 14 400 — well inside limits.
--   Trade-off: history queries spanning bucket boundaries require
--   ALLOW FILTERING or multiple partition reads (handled in
--   ingestion/writer.py by computing affected buckets).
--   This is acceptable because the history window is ≤ 600 s (10 min)
--   and at 20 Hz that is at most 12 000 rows per query — one bucket.
-- ============================================================

-- ── Keyspace ─────────────────────────────────────────────────────────
CREATE KEYSPACE IF NOT EXISTS f1_telemetry
  WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
  }
  AND durable_writes = true;

USE f1_telemetry;

-- ── races ─────────────────────────────────────────────────────────────
-- Query: "give me metadata for race R001"
-- PK: race_id only — one row per race; full-table scan acceptable
-- because there are at most ~50 races in the system at any time.
CREATE TABLE IF NOT EXISTS races (
    race_id        text,
    name           text,
    circuit        text,
    laps_total     int,
    status         text,          -- 'live' | 'finished'
    started_at     timestamp,
    finished_at    timestamp,
    PRIMARY KEY (race_id)
) WITH comment = 'Race metadata — one row per race';

-- ── cars ──────────────────────────────────────────────────────────────
-- Query: "give me all cars in race R001"
-- PK: (race_id) + clustering(car_number) — one partition per race
-- lets us fetch all cars with a single partition read.
CREATE TABLE IF NOT EXISTS cars (
    race_id        text,
    car_number     int,
    driver         text,
    team           text,
    PRIMARY KEY (race_id, car_number)
) WITH comment = 'Car/driver roster per race';

-- ── telemetry ─────────────────────────────────────────────────────────
-- Query: "give me the last N seconds of readings for car X in race R"
--
-- PARTITION KEY: (race_id, car_number, lap_bucket)
--   lap_bucket = CAST(lap_number / 5 AS INT)  (computed by the writer)
--   This keeps each partition to ~14 400 rows (≈ 5 laps × 2 880 rows/lap).
--
-- CLUSTERING: sensor_timestamp DESC
--   Allows LIMIT N to return the most-recent readings cheaply.
--
-- TWCS COMPACTION [AD]
--   TimeWindowCompactionStrategy merges SSTables written in the same
--   time window into one SSTable, then never rewrites old windows.
--   This is ideal for time-series data because:
--     1. Writes are always to the current window (no rewrite of old data).
--     2. TTL expiry aligns with window boundaries — expired SSTables are
--        dropped as whole files instead of requiring tombstone compaction.
--   compaction_window_size = 1, compaction_window_unit = HOURS means
--   one SSTable file per hour of data.
--
-- TTL [AD]
--   default_time_to_live = 604800 (7 days in seconds).
--   Raw 20 Hz telemetry is bulky; we keep 7 days for replay/demo.
--   The lap_summary table holds aggregated data permanently.
--   TTL causes tombstone generation; TWCS's window-drop handles this
--   efficiently without compaction overhead.
--
-- NULLABLE COLUMNS [DE]
--   source, gear, compound, tyre_age_laps are nullable so that a
--   FastF1 real-data adapter (Phase 8) can be added without a schema
--   migration.
CREATE TABLE IF NOT EXISTS telemetry (
    race_id          text,
    car_number       int,
    lap_bucket       int,            -- lap_number DIV 5; partition key component
    sensor_timestamp timestamp,      -- UTC ms precision
    lap_number       int,
    speed_kmh        double,
    rpm              int,
    throttle_pct     double,
    brake_temp_c     double,
    tire_temp_c      double,
    tire_wear_pct    double,
    g_force_lat      double,
    g_force_long     double,
    quality_flag     text,           -- 'ok' | 'imputed' | 'corrected' | 'suspect'
    -- nullable extension columns (Phase 8 FastF1 adapter)
    source           text,           -- NULL for simulator, 'fastf1' for real data
    gear             int,            -- nullable; available from simulator, NULL in FastF1
    compound         text,           -- e.g. 'SOFT','MEDIUM','HARD','INTER','WET'
    tyre_age_laps    int,            -- laps on current set; nullable if unknown
    -- enrichment columns (populated by pipeline/enrich.py)
    sector           int,            -- 1, 2, or 3
    stint_number     int,
    tire_wear_rate   double,         -- wear_pct per lap
    brake_temp_delta double,         -- delta from previous reading
    cumulative_g     double,         -- cumulative lateral G-load this stint
    pit_in           boolean,
    pit_out          boolean,
    PRIMARY KEY ((race_id, car_number, lap_bucket), sensor_timestamp)
) WITH CLUSTERING ORDER BY (sensor_timestamp DESC)
  AND comment      = 'Raw 20 Hz telemetry. Partitioned by (race,car,lap_bucket) for size control.'
  AND default_time_to_live = 604800
  AND compaction = {
    'class'                  : 'TimeWindowCompactionStrategy',
    'compaction_window_size' : 1,
    'compaction_window_unit' : 'HOURS',
    'expired_sstable_check_frequency_seconds': 3600
  }
  AND compression = {
    'class'              : 'LZ4Compressor',
    'chunk_length_in_kb' : 64
  };

-- ── telemetry_latest ─────────────────────────────────────────────────
-- Query: "give me the single latest reading for car X in race R"
-- Denormalized: one row per (race_id, car_number), upserted on every
-- write batch.  Single-row lookup = O(1) in Cassandra (one partition
-- read, no clustering column scan).  This avoids a LIMIT 1 query on
-- the telemetry table which would touch the partition index.
--
-- NOTE: This table intentionally omits lap_bucket because it always
-- holds exactly one row per car — no partition-size concern.
CREATE TABLE IF NOT EXISTS telemetry_latest (
    race_id          text,
    car_number       int,
    sensor_timestamp timestamp,
    lap_number       int,
    speed_kmh        double,
    rpm              int,
    throttle_pct     double,
    brake_temp_c     double,
    tire_temp_c      double,
    tire_wear_pct    double,
    g_force_lat      double,
    g_force_long     double,
    quality_flag     text,
    source           text,
    gear             int,
    compound         text,
    tyre_age_laps    int,
    sector           int,
    stint_number     int,
    tire_wear_rate   double,
    brake_temp_delta double,
    cumulative_g     double,
    pit_in           boolean,
    pit_out          boolean,
    PRIMARY KEY (race_id, car_number)
) WITH comment = 'Latest telemetry reading per car — O(1) lookup for the dashboard KPI strip.';

-- ── lap_summary ───────────────────────────────────────────────────────
-- Query: "give me all laps for car X in race R, most-recent first"
-- Aggregated per-lap statistics written at lap completion events.
-- Held indefinitely (no TTL) as it is the historical record.
CREATE TABLE IF NOT EXISTS lap_summary (
    race_id          text,
    car_number       int,
    lap_number       int,
    lap_time_ms      bigint,         -- milliseconds; NULL if lap not complete
    avg_speed_kmh    double,
    tire_wear_pct    double,         -- wear at lap end
    compound         text,
    pit_flag         boolean,
    completed_at     timestamp,
    PRIMARY KEY ((race_id, car_number), lap_number)
) WITH CLUSTERING ORDER BY (lap_number DESC)
  AND comment = 'Per-lap summary — written at lap completion. Used for ML feature extraction.';

-- ── race_car_counters ─────────────────────────────────────────────────
-- COUNTER TABLE [AD]
--
-- WHY a separate table?
--   Cassandra does not allow mixing COUNTER columns with regular
--   (non-counter) columns in the same table.  Counters use a special
--   internal CRDT representation that is incompatible with regular
--   column storage.
--
-- COUNTER IDEMPOTENCY WARNING [AD]
--   Cassandra counters are NOT idempotent.  A counter UPDATE that
--   succeeds on the server but times out on the client MUST NOT be
--   retried — doing so would double-count.  This is why counters are
--   incremented only on discrete, once-per-event triggers (lap_completed,
--   pit_exit), never on every 20 Hz sensor reading, and never with
--   unconditional retries.  The writer uses a dead-letter queue for
--   counter failures and requires human review.
--
-- Query: "give me laps, pit_stops, total_pit_ms for all cars in R001"
-- Used by the leaderboard endpoint.
--
-- LEADERBOARD NOTE: Cassandra cannot ORDER BY a counter column.
-- The API reads counters for all cars in a race (one CQL read per car
-- or a multi-partition read) and sorts in Python — laps DESC,
-- then last lap completion time ASC.  This is documented as a known
-- trade-off of using a counter table.
CREATE TABLE IF NOT EXISTS race_car_counters (
    race_id        text,
    car_number     int,
    laps           counter,
    pit_stops      counter,
    total_pit_ms   counter,
    PRIMARY KEY (race_id, car_number)
) WITH comment = 'Event-driven counters. See docs/data_model.md for idempotency warning.';

-- ── predictions ───────────────────────────────────────────────────────
-- Query: "give me the latest prediction for car X in race R"
-- TTL: 300 s (5 min) — predictions older than 5 min are stale.
CREATE TABLE IF NOT EXISTS predictions (
    race_id                  text,
    car_number               int,
    generated_at             timestamp,
    pit_needed_within_3_laps boolean,
    probability              double,
    confidence               text,    -- 'low' | 'medium' | 'high'
    estimated_laps_to_pit    int,
    level                    text,    -- 'green' | 'amber' | 'red'
    model_version            text,
    PRIMARY KEY ((race_id, car_number), generated_at)
) WITH CLUSTERING ORDER BY (generated_at DESC)
  AND default_time_to_live = 300
  AND comment = 'ML pit-stop predictions. TTL=5 min — stale predictions auto-expire.';

-- ── quality_summary ───────────────────────────────────────────────────
-- Query: "give me data-quality stats for race R"
-- Written once per pipeline run.
CREATE TABLE IF NOT EXISTS quality_summary (
    race_id         text,
    rows_in         bigint,
    rows_out        bigint,
    quarantined     bigint,
    pct_by_reason   text,    -- JSON-encoded map e.g. '{"out_of_range":1.2,"duplicate":0.6}'
    run_at          timestamp,
    PRIMARY KEY (race_id)
) WITH comment = 'Data quality report per race — powers the /quality endpoint.';

-- ── quarantine ────────────────────────────────────────────────────────
-- Stores all rejected records with reason codes.
-- Useful for the "dirty vs cleaned" ML experiment and viva demo.
CREATE TABLE IF NOT EXISTS quarantine (
    race_id          text,
    car_number       int,
    sensor_timestamp timestamp,
    reason_code      text,    -- 'out_of_range'|'missing'|'bad_type'|'duplicate'|'out_of_order'|'wrong_unit'
    raw_payload      text,    -- JSON-encoded original row
    rejected_at      timestamp,
    PRIMARY KEY ((race_id, car_number), rejected_at, sensor_timestamp)
) WITH CLUSTERING ORDER BY (rejected_at DESC, sensor_timestamp DESC)
  AND default_time_to_live = 604800
  AND comment = 'Rejected records with reason codes — never silently dropped.';
