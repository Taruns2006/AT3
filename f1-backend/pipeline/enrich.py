"""
pipeline/enrich.py — Telemetry feature enrichment and bucket calculation.

Computes lap_bucket, sectors, stint numbers, tire wear rates, brake temp deltas,
and cumulative G-loads.
[DE] Data Engineering
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def enrich_telemetry(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enriches cleaned telemetry with:
    - lap_bucket (lap_number // 5) for Cassandra wide-column partitioning
    - sector (1, 2, 3)
    - stint_number
    - tire_wear_rate (% per lap)
    - brake_temp_delta (diff from previous reading per car)
    - cumulative_g (rolling cumulative sum of |g_force_lat| per car)
    - pit_in, pit_out flags
    """
    if df.empty:
        return df

    enriched = df.copy()

    # Lap bucket for Cassandra partition sizing
    enriched["lap_bucket"] = (enriched["lap_number"] // 5).astype(int)

    # Sector: assign based on lap timestamp progression or estimate
    # In F1 Silverstone, Lap is split into ~3 equal-duration sectors
    enriched["brake_temp_delta"] = 0.0
    enriched["cumulative_g"] = 0.0
    enriched["sector"] = 1
    enriched["stint_number"] = 1
    enriched["tire_wear_rate"] = 2.2
    enriched["pit_in"] = False
    enriched["pit_out"] = False

    enriched_groups = []
    for _car_number, group in enriched.groupby("car_number", sort=False):
        grp = group.sort_values("sensor_timestamp").copy()

        # Brake temperature delta
        grp["brake_temp_delta"] = grp["brake_temp_c"].diff().fillna(0.0).round(2)

        # Cumulative G-force (sum of absolute lateral G)
        grp["cumulative_g"] = grp["g_force_lat"].abs().cumsum().round(2)

        # Estimate sector by dividing each lap's timestamps into 3 equal quantiles
        for _lap_num, lap_grp in grp.groupby("lap_number", sort=False):
            n_lap_rows = len(lap_grp)
            if n_lap_rows > 0:
                s1_end = int(n_lap_rows * 0.33)
                s2_end = int(n_lap_rows * 0.66)
                sectors = np.ones(n_lap_rows, dtype=int)
                sectors[s1_end:s2_end] = 2
                sectors[s2_end:] = 3
                grp.loc[lap_grp.index, "sector"] = sectors

                # Tire wear rate for this lap
                min_wear = lap_grp["tire_wear_pct"].min()
                max_wear = lap_grp["tire_wear_pct"].max()
                wear_delta = max(0.0, max_wear - min_wear)
                grp.loc[lap_grp.index, "tire_wear_rate"] = round(wear_delta, 2)

        # Detect pit entry / exit if speed drops around pit speed limit (80 km/h)
        speed_below_85 = grp["speed_kmh"] <= 82.0
        grp["pit_in"] = speed_below_85 & (~speed_below_85.shift(1, fill_value=False))
        grp["pit_out"] = (~speed_below_85) & speed_below_85.shift(1, fill_value=False)

        enriched_groups.append(grp)

    return pd.concat(enriched_groups, ignore_index=True)
