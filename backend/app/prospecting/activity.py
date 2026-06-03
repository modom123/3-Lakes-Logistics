"""Lead activity logger — single helper imported by all agents.

Writes to lead_activities table (permanent, per-lead touchpoint history).
Also auto-advances lead stage based on channel action.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


_STAGE_PROGRESSION = {
    # channel+status → new status (only advances, never regresses)
    ("call",  "sent"):         "Contacted",
    ("call",  "answered"):     "Contacted",
    ("call",  "no_answer"):    "Contacted",
    ("call",  "voicemail"):    "Contacted",
    ("call",  "interested"):   "Interested",
    ("sms",   "sent"):         "Contacted",
    ("sms",   "delivered"):    "Contacted",
    ("email", "sent"):         "Contacted",
    ("email", "delivered"):    "Contacted",
}

_STAGE_RANK = {
    "new": 0, "New": 0,
    "Contacted": 1, "contacted": 1,
    "Interested": 2, "interested": 2,
    "Qualified": 3, "qualified": 3,
    "Converted": 4, "converted": 4,
    "Won": 4, "won": 4,
}


def log_activity(
    lead_id: str,
    channel: str,
    status: str,
    summary: str | None = None,
    agent: str | None = None,
    payload: dict[str, Any] | None = None,
    direction: str = "outbound",
) -> None:
    """Insert a lead_activity row and optionally advance the lead's stage."""
    from ..supabase_client import get_supabase
    db = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    db.table("lead_activities").insert({
        "lead_id":    lead_id,
        "created_at": now,
        "channel":    channel,
        "direction":  direction,
        "status":     status,
        "summary":    summary,
        "agent":      agent,
        "payload":    payload or {},
    }).execute()

    new_status = _STAGE_PROGRESSION.get((channel, status))
    if new_status:
        lead = (db.table("leads").select("status").eq("id", lead_id).maybe_single().execute()).data
        current = (lead or {}).get("status", "New") or "New"
        if _STAGE_RANK.get(new_status, 0) > _STAGE_RANK.get(current, 0):
            db.table("leads").update({
                "status": new_status,
                "last_touch_at":   now,
                "last_contact_at": now,
            }).eq("id", lead_id).execute()
