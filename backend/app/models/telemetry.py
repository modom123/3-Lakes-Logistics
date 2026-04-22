from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TelemetryPing(BaseModel):
    carrier_id: str
    truck_id: str
    eld_provider: str
    lat: float
    lng: float
    speed_mph: float | None = None
    heading_deg: float | None = None
    odometer_mi: float | None = None
    fuel_level_pct: float | None = None
    engine_hours: float | None = None
    ts: datetime | None = None


class HosStatus(BaseModel):
    carrier_id: str
    driver_code: str
    duty_status: str
    drive_remaining_min: int | None = None
    shift_remaining_min: int | None = None
    cycle_remaining_min: int | None = None
    violation_flags: list[str] = []
