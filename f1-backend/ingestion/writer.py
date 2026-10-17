#!/usr/bin/env python3
"""
ingestion/writer.py — Ingestion pipeline from cleaned Parquet into Cassandra.

Ingests races, cars, telemetry (partitioned by lap_bucket with TWCS),
telemetry_latest (O(1) dashboard lookup), lap summaries, event counters,
quality summaries, and quarantine records.
[AD] Advanced Databases
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from ingestion.connection import get_cassandra_session

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
log = logging.getLogger("ingestion_writer")


def sync_to_local_cache(cleaned_dir: Path, race_id: str) -> None:
    """
    Maintains a SQLite local mirror of Cassandra tables in data/f1_telemetry.db
    so API, ML, and frontend run seamlessly whether Cassandra is up or down.
    """
    db_path = ROOT / "data" / "f1_telemetry.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)

    # 1. Races
    races_file = cleaned_dir / "races.parquet"
    if races_file.exists():
        df_r = pd.read_parquet(races_file)
        df_r.to_sql("races", conn, if_exists="replace", index=False)

    # 2. Cars
    cars_file = cleaned_dir / "cars.parquet"
    if cars_file.exists():
        df_c = pd.read_parquet(cars_file)
        df_c.to_sql("cars", conn, if_exists="replace", index=False)

    # 3. Telemetry & Telemetry Latest
    tel_file = cleaned_dir / "telemetry.parquet"
    if tel_file.exists():
        df_t = pd.read_parquet(tel_file)
        df_t.to_sql("telemetry", conn, if_exists="replace", index=False)

        # Build telemetry_latest
        df_latest = (
            df_t.sort_values("sensor_timestamp")
            .groupby(["race_id", "car_number"])
            .last()
            .reset_index()
        )
        df_latest.to_sql("telemetry_latest", conn, if_exists="replace", index=False)

    # 4. Lap Summary
    laps_file = cleaned_dir / "lap_events.parquet"
    if laps_file.exists():
        df_l = pd.read_parquet(laps_file)
        df_l.to_sql("lap_summary", conn, if_exists="replace", index=False)

    # 5. Quality Summary
    q_file = cleaned_dir / "quality_summary.parquet"
    if q_file.exists():
        df_q = pd.read_parquet(q_file)
        df_q.to_sql("quality_summary", conn, if_exists="replace", index=False)

    # 6. Quarantine
    quar_file = ROOT / "data" / "quarantine" / race_id / "quarantine.parquet"
    if quar_file.exists():
        df_quar = pd.read_parquet(quar_file)
        df_quar.to_sql("quarantine", conn, if_exists="replace", index=False)

    conn.close()
    log.info(f"Synchronized local telemetry cache: {db_path}")


def ingest_race_data(race_id: str = "R001") -> int:
    cleaned_dir = ROOT / "data" / "cleaned" / race_id
    if not cleaned_dir.exists():
        log.error(f"Cleaned data directory not found: {cleaned_dir}")
        log.error("Run: python manage.py pipeline")
        return 1

    # Mirror to local DB
    sync_to_local_cache(cleaned_dir, race_id)

    # Try Cassandra session
    session = get_cassandra_session()
    if session is None:
        log.warning(
            "[UNVERIFIED] Cassandra is offline. Staged data in data/cleaned and synced local cache."
        )
        log.info(
            "To write directly to Cassandra: start Docker, run `python manage.py up`, then `python manage.py ingest`."
        )
        return 0

    log.info(f"Ingesting race {race_id} data into Cassandra...")

    # Ingest Races
    races_file = cleaned_dir / "races.parquet"
    if races_file.exists():
        df_r = pd.read_parquet(races_file)
        stmt_race = session.prepare("""
            INSERT INTO races (race_id, name, circuit, laps_total, status, started_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """)
        for _, row in df_r.iterrows():
            session.execute(
                stmt_race,
                (
                    row["race_id"],
                    row["name"],
                    row["circuit"],
                    int(row["laps_total"]),
                    row["status"],
                    row["started_at"].to_pydatetime() if pd.notnull(row["started_at"]) else None,
                    row["finished_at"].to_pydatetime() if pd.notnull(row["finished_at"]) else None,
                ),
            )
        log.info(f"Ingested {len(df_r)} race record(s) into 'races'")

    # Ingest Cars
    cars_file = cleaned_dir / "cars.parquet"
    if cars_file.exists():
        df_c = pd.read_parquet(cars_file)
        stmt_car = session.prepare("""
            INSERT INTO cars (race_id, car_number, driver, team)
            VALUES (?, ?, ?, ?)
        """)
        for _, row in df_c.iterrows():
            session.execute(
                stmt_car, (row["race_id"], int(row["car_number"]), row["driver"], row["team"])
            )
        log.info(f"Ingested {len(df_c)} car record(s) into 'cars'")

    # Ingest Telemetry & Telemetry Latest
    tel_file = cleaned_dir / "telemetry.parquet"
    if tel_file.exists():
        df_t = pd.read_parquet(tel_file)
        stmt_tel = session.prepare("""
            INSERT INTO telemetry (
                race_id, car_number, lap_bucket, sensor_timestamp, lap_number,
                speed_kmh, rpm, throttle_pct, brake_temp_c, tire_temp_c, tire_wear_pct,
                g_force_lat, g_force_long, quality_flag, source, gear, compound,
                tyre_age_laps, sector, stint_number, tire_wear_rate, brake_temp_delta,
                cumulative_g, pit_in, pit_out
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """)

        stmt_latest = session.prepare("""
            INSERT INTO telemetry_latest (
                race_id, car_number, sensor_timestamp, lap_number,
                speed_kmh, rpm, throttle_pct, brake_temp_c, tire_temp_c, tire_wear_pct,
                g_force_lat, g_force_long, quality_flag, source, gear, compound,
                tyre_age_laps, sector, stint_number, tire_wear_rate, brake_temp_delta,
                cumulative_g, pit_in, pit_out
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """)

        # Execute async writes in batches of 100
        futures = []
        count = 0
        latest_rows = {}

        for _, r in df_t.iterrows():
            ts = r["sensor_timestamp"].to_pydatetime()
            lap_num = int(r["lap_number"])
            lap_bucket = lap_num // 5

            params = (
                r["race_id"],
                int(r["car_number"]),
                lap_bucket,
                ts,
                lap_num,
                float(r["speed_kmh"]),
                int(r["rpm"]),
                float(r["throttle_pct"]),
                float(r["brake_temp_c"]),
                float(r["tire_temp_c"]),
                float(r["tire_wear_pct"]),
                float(r["g_force_lat"]),
                float(r["g_force_long"]),
                str(r["quality_flag"]),
                str(r.get("source", "simulator")),
                int(r.get("gear", 1)),
                str(r.get("compound", "MEDIUM")),
                int(r.get("tyre_age_laps", 0)),
                int(r.get("sector", 1)),
                int(r.get("stint_number", 1)),
                float(r.get("tire_wear_rate", 0.0)),
                float(r.get("brake_temp_delta", 0.0)),
                float(r.get("cumulative_g", 0.0)),
                bool(r.get("pit_in", False)),
                bool(r.get("pit_out", False)),
            )
            futures.append(session.execute_async(stmt_tel, params))
            count += 1
            latest_rows[(r["race_id"], int(r["car_number"]))] = (
                r["race_id"],
                int(r["car_number"]),
                ts,
                lap_num,
                float(r["speed_kmh"]),
                int(r["rpm"]),
                float(r["throttle_pct"]),
                float(r["brake_temp_c"]),
                float(r["tire_temp_c"]),
                float(r["tire_wear_pct"]),
                float(r["g_force_lat"]),
                float(r["g_force_long"]),
                str(r["quality_flag"]),
                str(r.get("source", "simulator")),
                int(r.get("gear", 1)),
                str(r.get("compound", "MEDIUM")),
                int(r.get("tyre_age_laps", 0)),
                int(r.get("sector", 1)),
                int(r.get("stint_number", 1)),
                float(r.get("tire_wear_rate", 0.0)),
                float(r.get("brake_temp_delta", 0.0)),
                float(r.get("cumulative_g", 0.0)),
                bool(r.get("pit_in", False)),
                bool(r.get("pit_out", False)),
            )

            if len(futures) >= 200:
                for f in futures:
                    f.result()
                futures = []

        for f in futures:
            f.result()

        # Update telemetry_latest
        for lat_params in latest_rows.values():
            session.execute(stmt_latest, lat_params)

        log.info(
            f"Ingested {count} telemetry rows and {len(latest_rows)} latest rows into Cassandra"
        )

    # Ingest Lap Summary & Counters
    laps_file = cleaned_dir / "lap_events.parquet"
    if laps_file.exists():
        df_l = pd.read_parquet(laps_file)
        stmt_lap = session.prepare("""
            INSERT INTO lap_summary (
                race_id, car_number, lap_number, lap_time_ms, avg_speed_kmh,
                tire_wear_pct, compound, pit_flag, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """)
        stmt_counter_lap = session.prepare("""
            UPDATE race_car_counters SET laps = laps + 1
            WHERE race_id = ? AND car_number = ?
        """)
        for _, row in df_l.iterrows():
            session.execute(
                stmt_lap,
                (
                    row["race_id"],
                    int(row["car_number"]),
                    int(row["lap_number"]),
                    int(row["lap_time_ms"]),
                    float(row.get("avg_speed_kmh", 0.0)),
                    float(row.get("tire_wear_pct", 0.0)),
                    str(row.get("compound", "MEDIUM")),
                    bool(row.get("pit_flag", False)),
                    row["completed_at"].to_pydatetime(),
                ),
            )
            session.execute(stmt_counter_lap, (row["race_id"], int(row["car_number"])))
        log.info(f"Ingested {len(df_l)} lap summaries and updated lap counters.")

    log.info(f"Cassandra ingestion complete for race {race_id}.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Ingest cleaned telemetry data into Cassandra")
    parser.add_argument("--race-id", default="R001")
    args = parser.parse_args()
    rc = ingest_race_data(args.race_id)
    sys.exit(rc)


if __name__ == "__main__":
    main()
