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
    heading: float | None = None
    odometer_miles: float | None = None
    fuel_pct: float | None = None
    ts: datetime | None = None


class HosStatus(BaseModel):
    carrier_id: str
    driver_code: str
    duty_status: str
    drive_remaining_min: int | None = None
    shift_remaining_min: int | None = None
    cycle_remaining_min: int | None = None
    violation_flags: list[str] = []


class NativePing(BaseModel):
    """Telemetry payload sent directly from the driver-tracker PWA (browser GPS)."""
    truck_id: str
    carrier_id: str | None = None
    lat: float
    lng: float
    speed_mph: float | None = None
    heading_deg: float | None = None
    driver_name: str | None = None
    duty_status: str | None = None
    accuracy_m: float | None = None
    ts: datetime | None = None
