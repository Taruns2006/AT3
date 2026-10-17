"""
pipeline/schemas.py — Pydantic v2 data schemas for the F1 telemetry pipeline.

These are the canonical field definitions. Every other module imports from here.
Validation ranges are documented inline with the business rationale.
[DE] Data Engineering
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Raw telemetry (simulator output, before cleaning) ───────────────────────
class RawTelemetry(BaseModel):
    """Single sensor reading as emitted by the simulator. [DE]

    Validation enforces physical plausibility ranges. Records outside these
    ranges are quarantined with reason code 'out_of_range'.
    """

    race_id: str
    car_number: int = Field(..., ge=1, le=99)
    sensor_timestamp: datetime  # UTC, ms precision

    # ── Sensor channels (with physical range validation) ─────────────────
    speed_kmh: float = Field(
        ..., ge=0.0, le=380.0, description="km/h; 380 is ~100 m/s, the absolute max for F1"
    )
    rpm: int = Field(
        ..., ge=0, le=15_000, description="Revolutions per minute; 0 = engine off / pit"
    )
    throttle_pct: float = Field(..., ge=0.0, le=100.0, description="Throttle position 0–100 %")
    brake_temp_c: float = Field(
        ..., ge=100.0, le=1_100.0, description="Brake disc temperature; cold ~100 °C, hot ~1000 °C"
    )
    tire_temp_c: float = Field(
        ..., ge=30.0, le=200.0, description="Tyre surface temperature; working range 80–120 °C"
    )
    tire_wear_pct: float = Field(
        ..., ge=0.0, le=100.0, description="Tyre wear percentage; 100 = fully worn"
    )
    g_force_lat: float = Field(
        ..., ge=-7.0, le=7.0, description="Lateral G-force; F1 corners ~4–5 g"
    )
    g_force_long: float = Field(
        ..., ge=-7.0, le=7.0, description="Longitudinal G-force; braking ~5 g, acceleration ~2 g"
    )

    # ── Optional / nullable (present from simulator; NULL from FastF1) ──
    gear: int | None = Field(None, ge=0, le=8)
    lap_number: int | None = Field(None, ge=0)
    compound: str | None = None  # 'SOFT'|'MEDIUM'|'HARD'|'INTER'|'WET'
    tyre_age_laps: int | None = Field(None, ge=0)
    source: str | None = None  # None = simulator; 'fastf1' = real data

    @field_validator("compound")
    @classmethod
    def validate_compound(cls, v: str | None) -> str | None:
        allowed = {"SOFT", "MEDIUM", "HARD", "INTER", "WET", None}
        if v not in allowed:
            msg = f"compound must be one of {allowed}, got {v!r}"
            raise ValueError(msg)
        return v

    @field_validator("sensor_timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: object) -> datetime:
        """Accept ISO-8601 strings or datetime objects."""
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        msg = f"Cannot parse timestamp: {v!r}"
        raise ValueError(msg)

    class Config:
        json_encoders = {datetime: lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"}


# ── Cleaned telemetry (after cleaning pipeline) ──────────────────────────────
QualityFlag = Literal["ok", "imputed", "corrected", "suspect"]


class CleanedTelemetry(BaseModel):
    """Telemetry after deduplication, imputation and outlier correction. [DE]"""

    race_id: str
    car_number: int
    sensor_timestamp: datetime

    speed_kmh: float
    rpm: int
    throttle_pct: float
    brake_temp_c: float
    tire_temp_c: float
    tire_wear_pct: float
    g_force_lat: float
    g_force_long: float

    quality_flag: QualityFlag = "ok"

    # Nullable extension columns
    gear: int | None = None
    lap_number: int | None = None
    compound: str | None = None
    tyre_age_laps: int | None = None
    source: str | None = None


# ── Enriched telemetry (after enrichment pipeline) ───────────────────────────
class EnrichedTelemetry(CleanedTelemetry):
    """Telemetry after lap/sector/tire enrichment. [DE]"""

    sector: int | None = None
    stint_number: int | None = None
    tire_wear_rate: float | None = None  # wear % per lap
    brake_temp_delta: float | None = None  # delta from previous reading
    cumulative_g: float | None = None  # cumulative lateral G this stint
    pit_in: bool | None = None
    pit_out: bool | None = None
    lap_bucket: int = 0  # lap_number // 5


# ── Quarantine record ─────────────────────────────────────────────────────────
ReasonCode = Literal[
    "out_of_range",
    "missing",
    "bad_type",
    "duplicate",
    "out_of_order",
    "wrong_unit",
]


class QuarantineRecord(BaseModel):
    """A record that failed validation, stored with a reason code. [DE]"""

    race_id: str
    car_number: int
    sensor_timestamp: datetime | None = None
    reason_code: ReasonCode
    raw_payload: str  # JSON-encoded original row
    rejected_at: datetime  # when rejection was recorded


# ── Lap summary ───────────────────────────────────────────────────────────────
class LapSummary(BaseModel):
    """Aggregated per-lap statistics written at lap completion. [AD]"""

    race_id: str
    car_number: int
    lap_number: int
    lap_time_ms: int | None = None
    avg_speed_kmh: float | None = None
    tire_wear_pct: float | None = None
    compound: str | None = None
    pit_flag: bool = False
    completed_at: datetime


# ── Quality report ────────────────────────────────────────────────────────────
class QualityReport(BaseModel):
    """Data quality statistics for one pipeline run. [DE]"""

    race_id: str
    rows_in: int
    rows_out: int
    quarantined: int
    pct_by_reason: dict[str, float]  # reason_code → percentage of rows_in
    run_at: datetime

    @model_validator(mode="after")
    def check_totals(self) -> QualityReport:
        if self.rows_out + self.quarantined > self.rows_in:
            msg = "rows_out + quarantined cannot exceed rows_in"
            raise ValueError(msg)
        return self


# ── Simulation event types (used for counter triggers) ───────────────────────
class LapEvent(BaseModel):
    """Emitted by simulator when a car completes a lap. [DE]"""

    race_id: str
    car_number: int
    lap_number: int
    lap_time_ms: int
    completed_at: datetime


class PitEvent(BaseModel):
    """Emitted by simulator on pit exit. [DE]"""

    race_id: str
    car_number: int
    lap_number: int
    pit_time_ms: int
    new_compound: str
    exited_at: datetime
