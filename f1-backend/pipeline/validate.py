"""
pipeline/validate.py — Raw telemetry validation and quarantine routing.

Applies Pydantic and physical range validation to incoming raw telemetry.
Invalid rows are routed to quarantine with descriptive reason codes.
[DE] Data Engineering
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

PHYSICAL_LIMITS = {
    "speed_kmh": (0.0, 380.0),
    "rpm": (0, 15000),
    "throttle_pct": (0.0, 100.0),
    "brake_temp_c": (100.0, 1100.0),
    "tire_temp_c": (30.0, 200.0),
    "tire_wear_pct": (0.0, 100.0),
    "g_force_lat": (-7.0, 7.0),
    "g_force_long": (-7.0, 7.0),
}


def validate_telemetry_batch(
    df: pd.DataFrame,
    race_id: str,
) -> tuple[pd.DataFrame, list[dict], dict[str, int]]:
    """
    Validates a batch of raw telemetry.
    Returns (valid_df, quarantine_records, rejection_counts).
    """
    if df.empty:
        return df, [], {}

    rejection_counts: dict[str, int] = {
        "out_of_range": 0,
        "missing": 0,
        "duplicate": 0,
        "out_of_order": 0,
        "bad_type": 0,
    }

    n_rows = len(df)
    now = datetime.now(UTC)
    quarantine_list: list[dict] = []
    is_valid = np.ones(n_rows, dtype=bool)

    # 1. Check for duplicates on (car_number, sensor_timestamp)
    dup_mask = df.duplicated(subset=["car_number", "sensor_timestamp"], keep="first")
    if dup_mask.any():
        dup_indices = df.index[dup_mask].tolist()
        for idx in dup_indices:
            is_valid[idx] = False
            rejection_counts["duplicate"] += 1
            row_dict = df.iloc[idx].to_dict()
            quarantine_list.append(
                {
                    "race_id": race_id,
                    "car_number": int(row_dict.get("car_number", 0)),
                    "sensor_timestamp": row_dict.get("sensor_timestamp"),
                    "reason_code": "duplicate",
                    "raw_payload": json.dumps(row_dict, default=str),
                    "rejected_at": now,
                }
            )

    # 2. Check for missing / null required fields
    required_fields = [
        "car_number",
        "sensor_timestamp",
        "speed_kmh",
        "rpm",
        "throttle_pct",
        "brake_temp_c",
        "tire_temp_c",
        "tire_wear_pct",
        "g_force_lat",
        "g_force_long",
    ]
    null_mask = df[required_fields].isnull().any(axis=1) & is_valid
    if null_mask.any():
        null_indices = df.index[null_mask].tolist()
        for idx in null_indices:
            is_valid[idx] = False
            rejection_counts["missing"] += 1
            row_dict = df.iloc[idx].to_dict()
            quarantine_list.append(
                {
                    "race_id": race_id,
                    "car_number": int(row_dict.get("car_number", 0))
                    if pd.notnull(row_dict.get("car_number"))
                    else 0,
                    "sensor_timestamp": row_dict.get("sensor_timestamp")
                    if pd.notnull(row_dict.get("sensor_timestamp"))
                    else None,
                    "reason_code": "missing",
                    "raw_payload": json.dumps(row_dict, default=str),
                    "rejected_at": now,
                }
            )

    # 3. Check for out_of_range physical values
    for col, (low, high) in PHYSICAL_LIMITS.items():
        if col in df.columns:
            oor_mask = ((df[col] < low) | (df[col] > high)) & is_valid
            if oor_mask.any():
                oor_indices = df.index[oor_mask].tolist()
                for idx in oor_indices:
                    is_valid[idx] = False
                    rejection_counts["out_of_range"] += 1
                    row_dict = df.iloc[idx].to_dict()
                    quarantine_list.append(
                        {
                            "race_id": race_id,
                            "car_number": int(row_dict.get("car_number", 0)),
                            "sensor_timestamp": row_dict.get("sensor_timestamp"),
                            "reason_code": "out_of_range",
                            "raw_payload": json.dumps(row_dict, default=str),
                            "rejected_at": now,
                        }
                    )

    valid_df = df[is_valid].copy()
    return valid_df, quarantine_list, rejection_counts
