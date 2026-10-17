#!/usr/bin/env python3
"""
simulator/simulator.py — F1 Telemetry Simulator (20 Hz, 5–20 cars).

Generates physically plausible Formula 1 telemetry at 20 Hz per car.
Supports historical batch generation (fast Parquet dump) and live streaming.
Injects controlled data quality defects when --dirty is specified.
[DE] Data Engineering
"""

from __future__ import annotations

import argparse
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Root project dir
ROOT = Path(__file__).resolve().parent.parent

# ── Car Rosters ─────────────────────────────────────────────────────────────
ROSTER = [
    {"car_number": 1, "driver": "Max Verstappen", "team": "Red Bull Racing", "base_pace": 1.000},
    {"car_number": 11, "driver": "Sergio Perez", "team": "Red Bull Racing", "base_pace": 1.008},
    {"car_number": 16, "driver": "Charles Leclerc", "team": "Ferrari", "base_pace": 1.002},
    {"car_number": 55, "driver": "Carlos Sainz", "team": "Ferrari", "base_pace": 1.004},
    {"car_number": 44, "driver": "Lewis Hamilton", "team": "Mercedes-AMG", "base_pace": 1.003},
    {"car_number": 63, "driver": "George Russell", "team": "Mercedes-AMG", "base_pace": 1.005},
    {"car_number": 4, "driver": "Lando Norris", "team": "McLaren", "base_pace": 1.001},
    {"car_number": 81, "driver": "Oscar Piastri", "team": "McLaren", "base_pace": 1.006},
    {"car_number": 14, "driver": "Fernando Alonso", "team": "Aston Martin", "base_pace": 1.007},
    {"car_number": 18, "driver": "Lance Stroll", "team": "Aston Martin", "base_pace": 1.014},
    {"car_number": 10, "driver": "Pierre Gasly", "team": "Alpine", "base_pace": 1.012},
    {"car_number": 31, "driver": "Esteban Ocon", "team": "Alpine", "base_pace": 1.013},
    {"car_number": 23, "driver": "Alexander Albon", "team": "Williams", "base_pace": 1.011},
    {"car_number": 2, "driver": "Logan Sargeant", "team": "Williams", "base_pace": 1.020},
    {"car_number": 3, "driver": "Daniel Ricciardo", "team": "RB", "base_pace": 1.010},
    {"car_number": 22, "driver": "Yuki Tsunoda", "team": "RB", "base_pace": 1.009},
    {"car_number": 77, "driver": "Valtteri Bottas", "team": "Kick Sauber", "base_pace": 1.015},
    {"car_number": 24, "driver": "Zhou Guanyu", "team": "Kick Sauber", "base_pace": 1.018},
    {"car_number": 27, "driver": "Nico Hulkenberg", "team": "Haas", "base_pace": 1.012},
    {"car_number": 20, "driver": "Kevin Magnussen", "team": "Haas", "base_pace": 1.014},
]

PRESETS = {
    "small": {"cars": 5, "laps": 5},
    "demo": {"cars": 10, "laps": 15},
    "full": {"cars": 20, "laps": 50},
}

WEAR_RATE_PER_LAP = {
    "SOFT": 3.8,
    "MEDIUM": 2.3,
    "HARD": 1.5,
}


class CarSimulationState:
    def __init__(self, car_info: dict, seed: int):
        self.car_number = car_info["car_number"]
        self.driver = car_info["driver"]
        self.team = car_info["team"]
        self.base_pace = car_info["base_pace"]
        self.rng = random.Random(seed + self.car_number)

        self.compound = self.rng.choice(["SOFT", "MEDIUM"])
        self.tire_wear_pct = 0.0
        self.tyre_age_laps = 0
        self.lap_number = 1
        self.lap_progress = self.rng.uniform(0.0, 0.05)  # track progress 0.0 to 1.0
        self.stint_number = 1

        self.in_pit = False
        self.pit_stop_timer = 0.0
        self.pit_laps_done = 0
        self.total_pit_ms = 0
        self.pit_stops = 0

        self.speed_kmh = 240.0
        self.rpm = 11000
        self.throttle_pct = 85.0
        self.brake_temp_c = 400.0
        self.tire_temp_c = 95.0
        self.g_force_lat = 0.0
        self.g_force_long = 0.0
        self.gear = 6

        self.lap_start_time: datetime | None = None


def generate_race_data(
    race_id: str = "R001",
    preset: str = "small",
    cars_count: int | None = None,
    laps_total: int | None = None,
    seed: int = 42,
    dirty: bool = False,
    historical: bool = True,
    speed_multiplier: float = 1.0,
    out_dir: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict], list[dict]]:
    """Simulates an F1 race and returns (telemetry_df, cars_df, races_df, lap_events, pit_events)."""
    cfg = PRESETS.get(preset, PRESETS["small"])
    n_cars = cars_count or cfg["cars"]
    n_laps = laps_total or cfg["laps"]

    selected_cars = ROSTER[:n_cars]
    cars_data = [
        {
            "race_id": race_id,
            "car_number": c["car_number"],
            "driver": c["driver"],
            "team": c["team"],
        }
        for c in selected_cars
    ]
    cars_df = pd.DataFrame(cars_data)

    start_time = datetime(2026, 10, 17, 14, 0, 0, tzinfo=UTC)
    current_time = start_time

    races_df = pd.DataFrame(
        [
            {
                "race_id": race_id,
                "name": f"Formula 1 Grand Prix 2026 - {race_id}",
                "circuit": "Silverstone Circuit",
                "laps_total": n_laps,
                "status": "finished" if historical else "live",
                "started_at": start_time,
                "finished_at": None,
            }
        ]
    )

    car_states = [CarSimulationState(c, seed) for c in selected_cars]
    for s in car_states:
        s.lap_start_time = current_time

    telemetry_rows: list[dict] = []
    lap_events: list[dict] = []
    pit_events: list[dict] = []

    dt = 0.05  # 20 Hz
    step = 0
    all_finished = False

    while not all_finished:
        current_time += timedelta(seconds=dt)
        step += 1
        active_cars = 0

        for state in car_states:
            if state.lap_number > n_laps:
                continue
            active_cars += 1

            # Pit stop handling
            if state.in_pit:
                state.pit_stop_timer += dt
                state.speed_kmh = 80.0 + state.rng.gauss(0, 1.5)
                state.gear = 2
                state.throttle_pct = 40.0
                state.rpm = 4500
                state.brake_temp_c = max(180.0, state.brake_temp_c - 1.2)
                state.tire_temp_c = max(65.0, state.tire_temp_c - 0.5)
                state.g_force_lat = state.rng.gauss(0, 0.1)
                state.g_force_long = 0.0

                if state.pit_stop_timer >= 22.0:  # ~22 s pit stop duration
                    state.in_pit = False
                    state.tire_wear_pct = 0.0
                    state.tyre_age_laps = 0
                    state.compound = "HARD" if state.compound in ("SOFT", "MEDIUM") else "MEDIUM"
                    state.stint_number += 1
                    pit_duration_ms = int(state.pit_stop_timer * 1000)
                    state.total_pit_ms += pit_duration_ms
                    state.pit_stops += 1
                    pit_events.append(
                        {
                            "race_id": race_id,
                            "car_number": state.car_number,
                            "lap_number": state.lap_number,
                            "pit_time_ms": pit_duration_ms,
                            "new_compound": state.compound,
                            "exited_at": current_time,
                        }
                    )
                    state.pit_stop_timer = 0.0
                continue

            # Standard track driving physics
            # Track length ~5891 m, typical lap time ~90 s. Average lap progress speed ~ 1/90 per sec
            lap_speed_factor = (1.0 / (88.0 * state.base_pace)) * (
                1.0 - state.tire_wear_pct * 0.0015
            )
            progress_inc = lap_speed_factor * dt
            state.lap_progress += progress_inc

            # Track profile (0.0 to 1.0)
            p = state.lap_progress
            if 0.0 <= p < 0.28:
                # Sector 1: Straight, high speed turn 1-2, braking into Turn 3
                if p < 0.12:  # Main straight
                    target_speed = 315.0
                    throttle = 100.0
                    g_lat = state.rng.gauss(0.1, 0.2)
                    g_long = 1.2
                    gear = 7
                elif p < 0.20:  # Fast sweep
                    target_speed = 260.0
                    throttle = 90.0
                    g_lat = 3.8
                    g_long = -0.4
                    gear = 6
                else:  # Heavy braking
                    target_speed = 110.0
                    throttle = 0.0
                    g_lat = 1.5
                    g_long = -4.2
                    gear = 3
            elif 0.28 <= p < 0.65:
                # Sector 2: Technical, twisting turns
                if p < 0.40:
                    target_speed = 160.0
                    throttle = 65.0
                    g_lat = -4.1
                    g_long = 0.2
                    gear = 4
                elif p < 0.52:
                    target_speed = 285.0
                    throttle = 100.0
                    g_lat = 0.5
                    g_long = 1.5
                    gear = 7
                else:
                    target_speed = 135.0
                    throttle = 20.0
                    g_lat = 3.9
                    g_long = -3.2
                    gear = 3
            else:
                # Sector 3: Medium turns, pit entry, start/finish straight
                if p < 0.85:
                    target_speed = 210.0
                    throttle = 80.0
                    g_lat = -3.5
                    g_long = -0.5
                    gear = 5
                else:
                    target_speed = 320.0
                    throttle = 100.0
                    g_lat = 0.2
                    g_long = 1.6
                    gear = 8

            # Smooth speed transition
            state.speed_kmh += (target_speed - state.speed_kmh) * (dt * 3.5) + state.rng.gauss(
                0, 0.8
            )
            state.speed_kmh = max(60.0, min(350.0, state.speed_kmh))
            state.gear = gear
            state.throttle_pct = max(0.0, min(100.0, throttle + state.rng.gauss(0, 2.0)))
            state.rpm = int(4500 + (state.speed_kmh / 350.0) * 8500 + state.rng.gauss(0, 100))

            # Temperature and G dynamics
            if g_long < -1.0:
                state.brake_temp_c += abs(g_long) * 4.5 * dt
            else:
                state.brake_temp_c -= 1.8 * dt
            state.brake_temp_c = max(180.0, min(950.0, state.brake_temp_c))

            state.tire_temp_c += (abs(g_lat) * 0.8 - 0.4) * dt
            state.tire_temp_c = max(75.0, min(135.0, state.tire_temp_c))

            # Wear
            wear_rate = WEAR_RATE_PER_LAP.get(state.compound, 2.0)
            wear_delta = (wear_rate / 90.0) * dt * (1.0 + abs(g_lat) * 0.1)
            state.tire_wear_pct = min(100.0, state.tire_wear_pct + wear_delta)

            state.g_force_lat = g_lat + state.rng.gauss(0, 0.1)
            state.g_force_long = g_long + state.rng.gauss(0, 0.1)

            # Record telemetry point
            row = {
                "race_id": race_id,
                "car_number": state.car_number,
                "sensor_timestamp": current_time,
                "speed_kmh": round(state.speed_kmh, 2),
                "rpm": int(state.rpm),
                "throttle_pct": round(state.throttle_pct, 2),
                "brake_temp_c": round(state.brake_temp_c, 2),
                "tire_temp_c": round(state.tire_temp_c, 2),
                "tire_wear_pct": round(state.tire_wear_pct, 2),
                "g_force_lat": round(state.g_force_lat, 3),
                "g_force_long": round(state.g_force_long, 3),
                "gear": state.gear,
                "lap_number": state.lap_number,
                "compound": state.compound,
                "tyre_age_laps": state.tyre_age_laps,
                "source": "simulator",
                "quality_flag": "ok",
            }

            # Lap completion check
            if state.lap_progress >= 1.0:
                lap_time_ms = int((current_time - state.lap_start_time).total_seconds() * 1000)
                lap_events.append(
                    {
                        "race_id": race_id,
                        "car_number": state.car_number,
                        "lap_number": state.lap_number,
                        "lap_time_ms": lap_time_ms,
                        "avg_speed_kmh": round(235.0 / state.base_pace, 2),
                        "tire_wear_pct": round(state.tire_wear_pct, 2),
                        "compound": state.compound,
                        "pit_flag": False,
                        "completed_at": current_time,
                    }
                )
                state.lap_progress = 0.0
                state.lap_number += 1
                state.tyre_age_laps += 1
                state.lap_start_time = current_time

                # Check if pit stop needed: when wear > 65% and remaining laps > 1
                if state.tire_wear_pct >= 62.0 and state.lap_number <= n_laps:
                    state.in_pit = True
                    state.pit_stop_timer = 0.0

            telemetry_rows.append(row)

        if active_cars == 0:
            all_finished = True

    telemetry_df = pd.DataFrame(telemetry_rows)

    # ── Inject controlled data quality defects if dirty flag is passed ────────
    if dirty and not telemetry_df.empty:
        n_rows = len(telemetry_df)
        rng = np.random.default_rng(seed)

        # 1. out_of_range speed (> 380 km/h or < 0)
        idx_speed = rng.choice(n_rows, size=int(n_rows * 0.01), replace=False)
        telemetry_df.loc[idx_speed, "speed_kmh"] = rng.choice(
            [420.5, 490.0, -15.0], size=len(idx_speed)
        )

        # 2. out_of_range brake_temp (< 100 or > 1100)
        idx_brake = rng.choice(n_rows, size=int(n_rows * 0.008), replace=False)
        telemetry_df.loc[idx_brake, "brake_temp_c"] = rng.choice(
            [1450.0, 50.0, -20.0], size=len(idx_brake)
        )

        # 3. out_of_range tire_wear (> 100 or < 0)
        idx_wear = rng.choice(n_rows, size=int(n_rows * 0.005), replace=False)
        telemetry_df.loc[idx_wear, "tire_wear_pct"] = rng.choice([-5.0, 115.0], size=len(idx_wear))

        # 4. missing / null values
        idx_null = rng.choice(n_rows, size=int(n_rows * 0.01), replace=False)
        telemetry_df.loc[idx_null, "rpm"] = np.nan

        # 5. duplicate rows
        idx_dup = rng.choice(n_rows, size=int(n_rows * 0.01), replace=False)
        dups = telemetry_df.iloc[idx_dup].copy()
        telemetry_df = pd.concat([telemetry_df, dups], ignore_index=True)

        # 6. bad timestamp / out_of_order
        idx_ts = rng.choice(len(telemetry_df), size=int(n_rows * 0.005), replace=False)
        telemetry_df.loc[idx_ts, "sensor_timestamp"] = current_time + timedelta(hours=2)

    races_df["finished_at"] = current_time

    # Save to parquet if out_dir specified
    if out_dir:
        raw_path = out_dir / "data" / "raw" / race_id
        raw_path.mkdir(parents=True, exist_ok=True)
        telemetry_df.to_parquet(raw_path / "telemetry.parquet", index=False)
        cars_df.to_parquet(raw_path / "cars.parquet", index=False)
        races_df.to_parquet(raw_path / "races.parquet", index=False)
        if lap_events:
            pd.DataFrame(lap_events).to_parquet(raw_path / "lap_events.parquet", index=False)
        if pit_events:
            pd.DataFrame(pit_events).to_parquet(raw_path / "pit_events.parquet", index=False)
        print(f"[Simulator] Generated {len(telemetry_df)} telemetry rows in {raw_path}")

    return telemetry_df, cars_df, races_df, lap_events, pit_events


def main():
    parser = argparse.ArgumentParser(description="F1 Telemetry Simulator")
    parser.add_argument("--preset", choices=["small", "demo", "full"], default="small")
    parser.add_argument("--cars", type=int)
    parser.add_argument("--laps", type=int)
    parser.add_argument("--race-id", default="R001")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dirty", action="store_true")
    parser.add_argument("--historical", action="store_true", default=True)
    parser.add_argument("--speed-multiplier", type=float, default=1.0)
    args = parser.parse_args()

    print(f"Running simulator for race {args.race_id} (preset={args.preset}, dirty={args.dirty})")
    generate_race_data(
        race_id=args.race_id,
        preset=args.preset,
        cars_count=args.cars,
        laps_total=args.laps,
        seed=args.seed,
        dirty=args.dirty,
        historical=args.historical,
        speed_multiplier=args.speed_multiplier,
        out_dir=ROOT,
    )
    print("Simulation finished successfully.")


if __name__ == "__main__":
    main()
