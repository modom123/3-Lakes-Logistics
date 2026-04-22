"""Atlas — Routing, geography, state transitions (step 70)."""
from __future__ import annotations

from typing import Any

from ..integrations.maps import directions, eta_minutes
from ..logging_service import log_agent

TRANSITIONS = {
    ("onboarding", "stripe_paid"):    "active",
    ("active",     "payment_failed"): "suspended",
    ("suspended",  "payment_ok"):     "active",
    ("booked",     "dispatched"):     "dispatched",
    ("dispatched", "picked_up"):      "in_transit",
    ("in_transit", "delivered"):      "delivered",
    ("delivered",  "pod_uploaded"):   "closed",
}


def advance(entity: str, entity_id: str, from_state: str, event: str) -> str | None:
    new = TRANSITIONS.get((from_state, event))
    if not new:
        return None
    table = {"carrier": "active_carriers", "load": "loads"}.get(entity)
    if not table:
        return None
    try:
        from ..supabase_client import get_supabase
        get_supabase().table(table).update({"status": new}).eq("id", entity_id).execute()
    except Exception as exc:  # noqa: BLE001
        log_agent("atlas", "advance_failed", error=str(exc))
        return None
    log_agent("atlas", f"{entity}:{event}", result=f"{from_state}→{new}")
    return new


def compute_route(origin: str, destination: str) -> dict[str, Any]:
    r = directions(origin, destination)
    if not r:
        return {"status": "stub", "reason": "maps_not_configured"}
    return {"status": "ok", "miles": r.miles, "duration_min": r.duration_min,
            "polyline": r.polyline}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    kind = payload.get("kind") or "advance"
    if kind == "route":
        return {"agent": "atlas", **compute_route(
            payload.get("origin") or "", payload.get("destination") or ""
        )}
    if kind == "eta":
        mins = eta_minutes(payload.get("origin") or "", payload.get("destination") or "")
        return {"agent": "atlas", "status": "ok" if mins is not None else "stub",
                "eta_min": mins}
    new_status = advance(
        payload.get("entity", ""),
        payload.get("entity_id", ""),
        payload.get("from_state", ""),
        payload.get("event", ""),
    )
    return {"agent": "atlas", "status": "ok", "new_status": new_status}
