"""
ml/extract.py — Extracts feature datasets from Cassandra or local Parquet stores.

Provides unified feature loading for offline model training and evaluation.
[ML] Machine Learning
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingestion.connection import get_cassandra_session
from ml.features import extract_features_from_dataframe

log = logging.getLogger("ml_extract")


def load_training_dataset(race_id: str = "R001") -> tuple[pd.DataFrame, pd.Series]:
    """
    Loads telemetry from Cassandra if available, or falls back to cleaned Parquet files.
    Returns (X, y).
    """
    session = get_cassandra_session()
    df = None

    if session:
        try:
            log.info("Querying training data from Cassandra telemetry table...")
            rows = session.execute(f"SELECT * FROM telemetry WHERE race_id = '{race_id}'")
            records = list(rows)
            if records:
                df = pd.DataFrame(records)
                log.info(f"Loaded {len(df)} rows from Cassandra")
        except Exception as exc:
            log.warning(f"Failed to query Cassandra for training: {exc}")

    if df is None or df.empty:
        # Fallback to cleaned parquet files
        cleaned_path = ROOT / "data" / "cleaned" / race_id / "telemetry.parquet"
        if not cleaned_path.exists():
            # If R001 doesn't exist, search any cleaned directory
            all_parquets = list(ROOT.glob("data/cleaned/*/telemetry.parquet"))
            if all_parquets:
                cleaned_path = all_parquets[0]
            else:
                raise FileNotFoundError(f"No cleaned telemetry found at {cleaned_path}")

        log.info(f"Loading training data from Parquet: {cleaned_path}")
        df = pd.read_parquet(cleaned_path)

    return extract_features_from_dataframe(df)
