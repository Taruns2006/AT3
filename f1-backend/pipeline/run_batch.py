#!/usr/bin/env python3
"""
pipeline/run_batch.py — Batch cleaning and enrichment pipeline orchestrator.

Loads raw Parquet telemetry, validates against schema, routes rejects to quarantine,
cleans, enriches with lap buckets/features, and outputs cleaned Parquet files.
[DE] Data Engineering
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from pipeline.clean import clean_telemetry
from pipeline.enrich import enrich_telemetry
from pipeline.validate import validate_telemetry_batch


def run_pipeline(race_id: str = "R001") -> int:
    raw_dir = ROOT / "data" / "raw" / race_id
    if not raw_dir.exists():
        print(f"[Error] Raw data directory does not exist: {raw_dir}")
        print("Please run: python manage.py simulate")
        return 1

    telemetry_file = raw_dir / "telemetry.parquet"
    if not telemetry_file.exists():
        print(f"[Error] Raw telemetry file not found: {telemetry_file}")
        return 1

    print(f"Loading raw telemetry from {telemetry_file}...")
    df_raw = pd.read_parquet(telemetry_file)
    rows_in = len(df_raw)
    print(f"Loaded {rows_in} raw telemetry rows.")

    # 1. Validation & Quarantine
    print("Validating raw telemetry...")
    valid_df, quarantine_records, rejection_counts = validate_telemetry_batch(
        df_raw, race_id=race_id
    )
    n_quarantined = len(quarantine_records)

    quarantine_dir = ROOT / "data" / "quarantine" / race_id
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    if quarantine_records:
        df_quarantine = pd.DataFrame(quarantine_records)
        df_quarantine.to_parquet(quarantine_dir / "quarantine.parquet", index=False)
        print(f"Quarantined {n_quarantined} invalid records in {quarantine_dir}")

    # 2. Cleaning
    print("Cleaning telemetry...")
    cleaned_df = clean_telemetry(valid_df)

    # 3. Enrichment
    print("Enriching telemetry (lap buckets, sectors, tire wear, G-load)...")
    enriched_df = enrich_telemetry(cleaned_df)
    rows_out = len(enriched_df)

    # 4. Save cleaned and enriched data
    cleaned_dir = ROOT / "data" / "cleaned" / race_id
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    enriched_file = cleaned_dir / "telemetry.parquet"
    enriched_df.to_parquet(enriched_file, index=False)
    print(f"Saved {rows_out} cleaned & enriched rows to {enriched_file}")

    # Copy cars & races & lap events to cleaned dir as well
    for extra in ["cars.parquet", "races.parquet", "lap_events.parquet", "pit_events.parquet"]:
        src = raw_dir / extra
        if src.exists():
            df_extra = pd.read_parquet(src)
            df_extra.to_parquet(cleaned_dir / extra, index=False)

    # 5. Quality report
    pct_by_reason = {}
    if rows_in > 0:
        for r_code, count in rejection_counts.items():
            pct_by_reason[r_code] = round((count / rows_in) * 100.0, 2)

    quality_summary = [
        {
            "race_id": race_id,
            "rows_in": rows_in,
            "rows_out": rows_out,
            "quarantined": n_quarantined,
            "pct_by_reason": json.dumps(pct_by_reason),
            "run_at": datetime.now(UTC),
        }
    ]
    pd.DataFrame(quality_summary).to_parquet(cleaned_dir / "quality_summary.parquet", index=False)

    print("\n-- Data Quality Summary -------------------------------------")
    print(f"  Rows In:      {rows_in}")
    print(f"  Rows Out:     {rows_out}")
    print(f"  Quarantined:  {n_quarantined}")
    print(f"  Reason Pct:   {pct_by_reason}")
    print("-------------------------------------------------------------\n")

    return 0


def main():
    parser = argparse.ArgumentParser(description="Run batch telemetry cleaning pipeline")
    parser.add_argument("--race-id", default="R001")
    args = parser.parse_args()
    rc = run_pipeline(args.race_id)
    sys.exit(rc)


if __name__ == "__main__":
    main()
