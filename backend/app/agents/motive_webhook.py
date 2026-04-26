"""Motive/Samsara/Geotab ELD webhook fan-in (used by Orbit + Pulse + dispatch).

Called from routes_webhooks.py — normalizes vendor payloads into our
truck_telemetry + driver_hos_status + load_events schema.

Supported event_type values:
  vehicle.position / ping / gps        — GPS telemetry ping
  driver.hos_status / hos              — HOS duty status change
  driver.dvir                          — pre/post-trip inspection
  vehicle.harsh_brake / harsh_brake    — hard-braking event
  vehicle.harsh_accel / harsh_accel    — harsh acceleration
  vehicle.speeding / speeding          — speed-limit breach
  vehicle.idle / idle                  — excessive idle
  vehicle.geofence / geofence          — geofence entry/exit
  driver.unassigned_driving            — unidentified driving
  driver.login / driver.logout         — ELD login events
"""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase


def _carrier_truck(body: dict) -> tuple[str | None, str | None, str | None]:
    data = body.get("data") or body
    carrier_id = body.get("carrier_id") or data.get("carrier_id")
    truck_id   = data.get("vehicle_id") or data.get("truck_id") or body.get("truck_id")
    driver_id  = data.get("driver_id") or body.get("driver_id")
    return carrier_id, truck_id, driver_id


def handle(body: dict[str, Any]) -> None:  # noqa: C901 (intentionally comprehensive)
    vendor = body.get("source") or body.get("vendor") or "motive"
    kind   = (body.get("event_type") or body.get("type") or "ping").lower()
    sb     = get_supabase()
    carrier_id, truck_id, driver_id = _carrier_truck(body)
    data   = body.get("data") or body

    # ── GPS / Position ────────────────────────────────────────────────────
    if kind in {"vehicle.position", "ping", "gps", "location"}:
        sb.table("truck_telemetry").insert({
            "carrier_id":    carrier_id,
            "truck_id":      truck_id,
            "driver_id":     driver_id,
            "eld_provider":  vendor,
            "lat":           data.get("lat") or data.get("latitude"),
            "lng":           data.get("lng") or data.get("longitude"),
            "speed_mph":     data.get("speed_mph") or data.get("speed"),
            "heading_deg":   data.get("heading"),
            "odometer_mi":   data.get("odometer"),
            "fuel_level_pct":data.get("fuel_pct") or data.get("fuel_level"),
        }).execute()
        log_agent("orbit", "telemetry_in", carrier_id=carrier_id, result="ingested")
        return

    # ── HOS Status ────────────────────────────────────────────────────────
    if kind in {"driver.hos_status", "hos", "hos_update"}:
        sb.table("driver_hos_status").insert({
            "carrier_id":          carrier_id,
            "driver_code":         driver_id,
            "driver_id":           driver_id,
            "duty_status":         data.get("duty_status"),
            "drive_remaining_min": data.get("drive_remaining_min") or data.get("drive_remaining"),
            "shift_remaining_min": data.get("shift_remaining_min") or data.get("shift_remaining"),
            "cycle_remaining_min": data.get("cycle_remaining_min") or data.get("cycle_remaining"),
            "violation_flags":     data.get("violations") or [],
        }).execute()
        log_agent("pulse", "hos_in", carrier_id=carrier_id, result="ingested")
        return

    # ── DVIR (Driver Vehicle Inspection Report) ───────────────────────────
    if kind in {"driver.dvir", "dvir", "inspection"}:
        defects = data.get("defects") or []
        has_defects = bool(defects)
        sb.table("agent_log").insert({
            "agent":      "pulse",
            "action":     "dvir",
            "carrier_id": carrier_id,
            "payload":    {
                "truck_id":    truck_id,
                "driver_id":   driver_id,
                "dvir_type":   data.get("type") or data.get("inspection_type", "pre_trip"),
                "defects":     defects,
                "has_defects": has_defects,
                "odometer":    data.get("odometer"),
                "vendor":      vendor,
            },
            "result": "defects_found" if has_defects else "clean",
        }).execute()
        if has_defects:
            _try_signal_alert(carrier_id, driver_id, "breakdown",
                              f"DVIR defects reported: {', '.join(str(d) for d in defects[:3])}")
        log_agent("pulse", "dvir_in", carrier_id=carrier_id, result="ingested")
        return

    # ── Harsh Braking ─────────────────────────────────────────────────────
    if kind in {"vehicle.harsh_brake", "harsh_brake", "hard_brake"}:
        sb.table("truck_telemetry").insert({
            "carrier_id":  carrier_id,
            "truck_id":    truck_id,
            "driver_id":   driver_id,
            "eld_provider":vendor,
            "lat":         data.get("lat"),
            "lng":         data.get("lng"),
            "speed_mph":   data.get("speed_mph"),
            "harsh_brake": True,
            "event_severity": data.get("severity") or "medium",
        }).execute()
        log_agent("pulse", "harsh_brake", carrier_id=carrier_id, result="logged")
        return

    # ── Harsh Acceleration ────────────────────────────────────────────────
    if kind in {"vehicle.harsh_accel", "harsh_accel", "hard_acceleration"}:
        sb.table("truck_telemetry").insert({
            "carrier_id":  carrier_id,
            "truck_id":    truck_id,
            "driver_id":   driver_id,
            "eld_provider":vendor,
            "lat":         data.get("lat"),
            "lng":         data.get("lng"),
            "harsh_accel": True,
        }).execute()
        log_agent("pulse", "harsh_accel", carrier_id=carrier_id, result="logged")
        return

    # ── Speeding ──────────────────────────────────────────────────────────
    if kind in {"vehicle.speeding", "speeding", "speed_violation"}:
        speed    = data.get("speed_mph") or data.get("speed", 0)
        limit    = data.get("speed_limit", 65)
        sb.table("truck_telemetry").insert({
            "carrier_id":     carrier_id,
            "truck_id":       truck_id,
            "driver_id":      driver_id,
            "eld_provider":   vendor,
            "lat":            data.get("lat"),
            "lng":            data.get("lng"),
            "speed_mph":      speed,
            "event_severity": "high" if speed > limit + 15 else "medium",
        }).execute()
        if speed > limit + 20:
            _try_signal_alert(carrier_id, driver_id, "hos_warning",
                              f"Speed alert: {speed} mph in a {limit} mph zone")
        log_agent("pulse", "speed_event", carrier_id=carrier_id, result="logged")
        return

    # ── Idle ──────────────────────────────────────────────────────────────
    if kind in {"vehicle.idle", "idle", "excessive_idle"}:
        idle_min = data.get("idle_minutes") or data.get("duration_minutes", 0)
        sb.table("truck_telemetry").insert({
            "carrier_id":   carrier_id,
            "truck_id":     truck_id,
            "driver_id":    driver_id,
            "eld_provider": vendor,
            "lat":          data.get("lat"),
            "lng":          data.get("lng"),
            "idle_minutes": idle_min,
        }).execute()
        log_agent("pulse", "idle_event", carrier_id=carrier_id,
                  result=f"{idle_min}min")
        return

    # ── Geofence ──────────────────────────────────────────────────────────
    if kind in {"vehicle.geofence", "geofence", "geofence_enter", "geofence_exit"}:
        event_dir = "enter" if "enter" in kind else ("exit" if "exit" in kind else data.get("direction", "enter"))
        sb.table("agent_log").insert({
            "agent":      "orbit",
            "action":     f"geofence_{event_dir}",
            "carrier_id": carrier_id,
            "payload":    {
                "truck_id":     truck_id,
                "driver_id":    driver_id,
                "geofence_id":  data.get("geofence_id") or data.get("zone_id"),
                "geofence_name":data.get("geofence_name") or data.get("zone_name"),
                "lat":          data.get("lat"),
                "lng":          data.get("lng"),
                "load_id":      data.get("load_id"),
                "vendor":       vendor,
            },
            "result": event_dir,
        }).execute()
        # Trigger orbit agent for delivery confirmation on exit
        if event_dir == "exit" and data.get("load_id"):
            try:
                from . import orbit
                orbit.run({"load_id": data["load_id"], "lat": data.get("lat"), "lng": data.get("lng"), "driver_id": driver_id})
            except Exception:
                pass
        log_agent("orbit", f"geofence_{event_dir}", carrier_id=carrier_id, result="processed")
        return

    # ── Unidentified / Unassigned Driving ─────────────────────────────────
    if kind in {"driver.unassigned_driving", "unidentified_driving"}:
        sb.table("agent_log").insert({
            "agent":      "pulse",
            "action":     "unassigned_driving",
            "carrier_id": carrier_id,
            "payload":    {"truck_id": truck_id, "duration_min": data.get("duration_minutes"), "vendor": vendor},
            "result":     "flagged",
        }).execute()
        log_agent("pulse", "unassigned_driving", carrier_id=carrier_id, result="flagged")
        return

    # ── Driver Login / Logout ─────────────────────────────────────────────
    if kind in {"driver.login", "driver.logout", "eld_login", "eld_logout"}:
        action = "login" if "login" in kind else "logout"
        sb.table("agent_log").insert({
            "agent":      "pulse",
            "action":     f"eld_{action}",
            "carrier_id": carrier_id,
            "payload":    {"driver_id": driver_id, "truck_id": truck_id, "vendor": vendor},
            "result":     action,
        }).execute()
        return

    # ── Unhandled ─────────────────────────────────────────────────────────
    log_agent("orbit", f"webhook:{kind}", payload={"vendor": vendor, "carrier_id": carrier_id}, result="unhandled")


def _try_signal_alert(carrier_id: str | None, driver_id: str | None, action: str, message: str) -> None:
    try:
        from . import signal as signal_agent
        signal_agent.run({"action": action, "carrier_id": carrier_id,
                          "driver_id": driver_id, "message": message})
    except Exception:
        pass
