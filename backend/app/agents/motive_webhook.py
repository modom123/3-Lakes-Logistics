"""Motive/Samsara ELD webhook fan-in (used by Orbit + Pulse + dispatch).

Called from routes_webhooks.py — normalizes vendor payloads into our
truck_telemetry + driver_hos_status schema.
"""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase


def handle(body: dict[str, Any]) -> None:
    vendor = body.get("source") or body.get("vendor") or "motive"
    kind = body.get("event_type") or body.get("type") or "ping"

    if kind in {"vehicle.position", "ping", "gps"}:
        ping = body.get("data") or body
        get_supabase().table("truck_telemetry").insert({
            "carrier_id": body.get("carrier_id"),
            "truck_id": ping.get("vehicle_id") or ping.get("truck_id"),
            "eld_provider": vendor,
            "lat": ping.get("lat") or ping.get("latitude"),
            "lng": ping.get("lng") or ping.get("longitude"),
            "speed_mph": ping.get("speed_mph") or ping.get("speed"),
            "heading_deg": ping.get("heading"),
            "odometer_mi": ping.get("odometer"),
            "fuel_level_pct": ping.get("fuel_pct"),
        }).execute()
        log_agent("orbit", "telemetry_in", payload={"vendor": vendor}, result="ingested")
        return

    if kind in {"driver.hos_status", "hos"}:
        hos = body.get("data") or body
        get_supabase().table("driver_hos_status").insert({
            "carrier_id": body.get("carrier_id"),
            "driver_code": hos.get("driver_id"),
            "duty_status": hos.get("duty_status"),
            "drive_remaining_min": hos.get("drive_remaining_min"),
            "shift_remaining_min": hos.get("shift_remaining_min"),
            "cycle_remaining_min": hos.get("cycle_remaining_min"),
            "violation_flags": hos.get("violations") or [],
        }).execute()
        log_agent("pulse", "hos_in", payload={"vendor": vendor}, result="ingested")
        return

    log_agent("orbit", f"webhook:{kind}", payload={"vendor": vendor}, result="unhandled")
