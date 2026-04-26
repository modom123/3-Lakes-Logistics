"""Pulse — Step 40. Weekly fleet wellness check.

Scores each driver 0-100 across five dimensions:
  HOS compliance (40 pts)  — violations in last 7 days
  Speed safety   (20 pts)  — hard-brake / over-speed events
  CDL status     (20 pts)  — expiry within 60 days = penalty
  Load streak    (10 pts)  — consecutive on-time deliveries
  Idle behaviour (10 pts)  — excessive idle events
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase


_WINDOW_DAYS = 7


def _week_start() -> str:
    today = date.today()
    return (today - timedelta(days=today.weekday() + 7)).isoformat()


def score_driver(driver_id: str, carrier_id: str | None = None) -> dict[str, Any]:
    """Compute a 0-100 wellness score for a driver over the last 7 days."""
    sb = get_supabase()
    since = (date.today() - timedelta(days=_WINDOW_DAYS)).isoformat()

    # ── HOS data ──────────────────────────────────────────────────────────
    q = sb.table("driver_hos_status").select("duty_status,violation_flags,drive_remaining_min").eq("driver_id", driver_id).gte("created_at", since)
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    hos_rows = q.order("created_at", desc=True).limit(300).execute().data or []

    hos_violations = sum(1 for r in hos_rows if r.get("violation_flags"))
    low_drive_alerts = sum(1 for r in hos_rows if (r.get("drive_remaining_min") or 9999) < 60)
    hos_score = max(0, 40 - hos_violations * 8 - low_drive_alerts * 2)

    # ── Telemetry: speeding / hard-brake ──────────────────────────────────
    q2 = (
        sb.table("truck_telemetry")
        .select("speed_mph,harsh_brake,harsh_accel,idle_minutes")
        .eq("driver_id", driver_id)
        .gte("created_at", since)
    )
    if carrier_id:
        q2 = q2.eq("carrier_id", carrier_id)
    telem_rows = q2.limit(500).execute().data or []

    speed_events = sum(1 for r in telem_rows if (r.get("speed_mph") or 0) > 75)
    harsh_events = sum(1 for r in telem_rows if r.get("harsh_brake") or r.get("harsh_accel"))
    idle_minutes  = sum(r.get("idle_minutes") or 0 for r in telem_rows)

    speed_score = max(0, 20 - speed_events * 4 - harsh_events * 2)
    idle_score  = max(0, 10 - int(idle_minutes / 60))  # -1pt per idle hour

    # ── CDL expiry ────────────────────────────────────────────────────────
    cdl_rows = (
        sb.table("driver_cdl")
        .select("expiration_date,cdl_status")
        .eq("driver_id", driver_id)
        .order("expiration_date")
        .limit(5)
        .execute()
        .data or []
    )
    cdl_score = 20
    for cdl in cdl_rows:
        if not cdl.get("expiration_date"):
            continue
        days_left = (date.fromisoformat(cdl["expiration_date"]) - date.today()).days
        if days_left < 0:
            cdl_score = 0
            break
        elif days_left < 30:
            cdl_score = max(0, cdl_score - 15)
        elif days_left < 60:
            cdl_score = max(0, cdl_score - 8)
        if cdl.get("cdl_status") == "red":
            cdl_score = 0
            break

    # ── On-time delivery streak ───────────────────────────────────────────
    loads = (
        sb.table("loads")
        .select("status,delivery_at,scheduled_delivery")
        .eq("driver_id", driver_id)
        .in_("status", ["delivered", "closed"])
        .order("delivery_at", desc=True)
        .limit(5)
        .execute()
        .data or []
    )
    on_time = sum(
        1 for l in loads
        if l.get("delivery_at") and l.get("scheduled_delivery")
        and l["delivery_at"][:10] <= l["scheduled_delivery"][:10]
    )
    load_score = min(10, on_time * 2)

    total_score = hos_score + speed_score + cdl_score + load_score + idle_score

    # ── Determine risk tier ───────────────────────────────────────────────
    if total_score >= 85:
        risk = "green"
    elif total_score >= 65:
        risk = "yellow"
    elif total_score >= 45:
        risk = "orange"
    else:
        risk = "red"

    return {
        "driver_id": driver_id,
        "carrier_id": carrier_id,
        "wellness_score": total_score,
        "risk_tier": risk,
        "breakdown": {
            "hos_compliance": hos_score,
            "speed_safety": speed_score,
            "cdl_status": cdl_score,
            "on_time_streak": load_score,
            "idle_behaviour": idle_score,
        },
        "flags": {
            "hos_violations_7d": hos_violations,
            "low_drive_alerts": low_drive_alerts,
            "speed_events_7d": speed_events,
            "harsh_events_7d": harsh_events,
            "idle_hours_7d": round(idle_minutes / 60, 1),
            "loads_on_time_last5": on_time,
            "cdl_score": cdl_score,
        },
        "as_of": date.today().isoformat(),
    }


def fleet_wellness(carrier_id: str | None = None) -> dict[str, Any]:
    """Score every active driver for a carrier (or all carriers)."""
    sb = get_supabase()
    q = sb.table("active_drivers").select("id,carrier_id,driver_name")
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    drivers = q.limit(500).execute().data or []

    scores = [score_driver(d["id"], d.get("carrier_id")) for d in drivers]
    avg = round(sum(s["wellness_score"] for s in scores) / len(scores), 1) if scores else 0

    return {
        "carrier_id": carrier_id or "all",
        "driver_count": len(scores),
        "fleet_avg_wellness": avg,
        "red_flags": [s for s in scores if s["risk_tier"] == "red"],
        "drivers": scores,
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    driver_id  = payload.get("driver_id")
    carrier_id = payload.get("carrier_id")

    if driver_id:
        res = score_driver(driver_id, carrier_id)
    else:
        res = fleet_wellness(carrier_id)

    log_agent("pulse", "wellness_check",
              carrier_id=carrier_id,
              payload={"driver_id": driver_id},
              result=str(res.get("wellness_score") or res.get("fleet_avg_wellness")))
    return {"agent": "pulse", **res}
