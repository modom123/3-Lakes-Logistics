"""Atlas — Step 37. Master orchestrator. Moves data between tables on
lifecycle events.
"""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase


TRANSITIONS = {
    # carrier status
    ("onboarding", "stripe_paid"): "active",
    ("active", "payment_failed"): "suspended",
    # load status
    ("booked", "dispatched"): "dispatched",
    ("dispatched", "picked_up"): "in_transit",
    ("in_transit", "delivered"): "delivered",
    ("delivered", "pod_uploaded"): "closed",
}


def advance(entity: str, entity_id: str, from_state: str, event: str) -> str | None:
    """Resolve the new status and persist it."""
    new = TRANSITIONS.get((from_state, event))
    if not new:
        return None
    table = {"carrier": "active_carriers", "load": "loads"}.get(entity)
    if not table:
        return None
    get_supabase().table(table).update({"status": new}).eq("id", entity_id).execute()
    log_agent("atlas", f"{entity}:{event}", payload={"id": entity_id}, result=f"{from_state}→{new}")
    return new


def run(payload: dict[str, Any]) -> dict[str, Any]:
    new_status = advance(
        payload.get("entity", ""),
        payload.get("entity_id", ""),
        payload.get("from_state", ""),
        payload.get("event", ""),
    )
    return {"agent": "atlas", "new_status": new_status}
