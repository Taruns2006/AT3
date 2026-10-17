#!/usr/bin/env python3
"""
ml/predict_live.py — Batch / live inference worker.

Fetches latest telemetry from Cassandra (or cache), generates predictions,
and writes to the Cassandra predictions table (TTL 300s).
[ML] Machine Learning
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
from ml.inference import predict_pit_stop

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
log = logging.getLogger("predict_live")


def run_live_predictions(race_id: str = "R001") -> int:
    session = get_cassandra_session()
    latest_rows = []

    if session:
        try:
            rows = session.execute(f"SELECT * FROM telemetry_latest WHERE race_id = '{race_id}'")
            latest_rows = [r._asdict() for r in rows]
        except Exception as exc:
            log.warning(f"Failed to fetch telemetry_latest from Cassandra: {exc}")

    if not latest_rows:
        # Fallback to local DB
        db_path = ROOT / "data" / "f1_telemetry.db"
        if db_path.exists():
            conn = sqlite3.connect(db_path)
            try:
                df = pd.read_sql_query(
                    f"SELECT * FROM telemetry_latest WHERE race_id = '{race_id}'", conn
                )
                latest_rows = df.to_dict(orient="records")
            except Exception:
                pass
            finally:
                conn.close()

    if not latest_rows:
        # Fallback to parquet
        parquet_file = ROOT / "data" / "cleaned" / race_id / "telemetry.parquet"
        if parquet_file.exists():
            df = pd.read_parquet(parquet_file)
            latest_rows = (
                df.sort_values("sensor_timestamp")
                .groupby("car_number")
                .last()
                .reset_index()
                .to_dict(orient="records")
            )

    log.info(f"Generating predictions for {len(latest_rows)} cars in race {race_id}...")
    predictions = [predict_pit_stop(row) for row in latest_rows]

    # Save to Cassandra if available
    if session:
        stmt = session.prepare("""
            INSERT INTO predictions (
                race_id, car_number, generated_at, pit_needed_within_3_laps,
                probability, confidence, estimated_laps_to_pit, level, model_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """)
        for p in predictions:
            session.execute(
                stmt,
                (
                    p["race_id"],
                    p["car_number"],
                    p["generated_at"],
                    p["pit_needed_within_3_laps"],
                    p["probability"],
                    p["confidence"],
                    p["estimated_laps_to_pit"],
                    p["level"],
                    p["model_version"],
                ),
            )
        log.info(
            f"Wrote {len(predictions)} predictions to Cassandra table 'predictions' (TTL 300s)"
        )

    # Mirror to local DB
    db_path = ROOT / "data" / "f1_telemetry.db"
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        df_p = pd.DataFrame(predictions)
        df_p.to_sql("predictions", conn, if_exists="replace", index=False)
        conn.close()

    return 0


def main():
    parser = argparse.ArgumentParser(description="Generate live ML predictions")
    parser.add_argument("--race-id", default="R001")
    args = parser.parse_args()
    rc = run_live_predictions(args.race_id)
    sys.exit(rc)


if __name__ == "__main__":
    main()
