from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TelemetryPing(BaseModel):
    carrier_id: str
    truck_id: str
    eld_provider: str | None = None      # optional — not sent by driver PWA (direct Supabase write)
    lat: float
    lng: float
    speed_mph: float | None = None
    heading_deg: float | None = None     # matches live DB column (was incorrectly named 'heading')
    odometer_mi: float | None = None     # matches live DB column (was 'odometer_miles')
    fuel_level_pct: float | None = None  # matches live DB column (was 'fuel_pct')
    engine_state: str | None = None      # pickup_confirmed | delivery_confirmed | driving | idle
    accuracy_m: float | None = None      # GPS horizontal accuracy in metres
    ts: datetime | None = None


class HosStatus(BaseModel):
    carrier_id: str
    driver_code: str
    duty_status: str
    drive_remaining_min: int | None = None
    shift_remaining_min: int | None = None
    cycle_remaining_min: int | None = None
    violation_flags: list[str] = []
