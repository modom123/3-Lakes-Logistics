"""Orbit — Lifecycle / reactivation (step 70) + geofencing."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from ..integrations.email import send_email
from ..logging_service import log_agent

GEOFENCE_RADIUS_MI = 0.50


def haversine_mi(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def inside_fence(lat, lng, fence_lat, fence_lng, radius_mi=GEOFENCE_RADIUS_MI) -> bool:
    return haversine_mi(lat, lng, fence_lat, fence_lng) <= radius_mi


def reactivate_dormant(days_idle: int = 30) -> dict[str, Any]:
    """Step 70c — reach out to carriers that haven't dispatched in N days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_idle)).isoformat()
    try:
        from ..supabase_client import get_supabase
        rows = (
            get_supabase().table("active_carriers")
            .select("id, email, company_name, last_active_at")
            .lte("last_active_at", cutoff).eq("status", "active").limit(200).execute()
        ).data or []
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    sent = 0
    for c in rows:
        if not c.get("email"):
            continue
        send_email(
            c["email"], "We miss you at 3 Lakes Logistics",
            f"<p>Hi {c.get('company_name') or 'there'},</p>"
            f"<p>We noticed it's been a bit — here's a quick list of open loads that fit your fleet.</p>",
            tag="reactivation",
        )
        sent += 1
    log_agent("orbit", "reactivate_dormant", result=f"sent={sent}")
    return {"status": "ok", "sent": sent}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    kind = payload.get("kind") or "geofence"
    if kind == "reactivate_dormant":
        return {"agent": "orbit", **reactivate_dormant(payload.get("days_idle") or 30)}
    try:
        arrived = inside_fence(
            payload["lat"], payload["lng"],
            payload["fence_lat"], payload["fence_lng"],
            payload.get("radius_mi", GEOFENCE_RADIUS_MI),
        )
    except KeyError as exc:
        return {"agent": "orbit", "status": "error", "error": f"missing {exc}"}
    return {"agent": "orbit", "status": "ok", "arrived": arrived}
