"""Bond Office API — bidirectional channel between IEBC Internal
James Bond and the External James Bond on Daytona.

Internal endpoints (bearer auth) — called by EAGLE EYE / Bond Office UI:
  GET  /bond/thread              full conversation thread
  POST /bond/directive           IEBC sends directive to External Bond
  GET  /bond/status              channel health + message counts
  PATCH /bond/message/{id}       mark a message actioned

External endpoints (X-Bond-Key auth) — called by External Bond on Daytona:
  GET  /bond/inbox               poll for pending IEBC directives
  POST /bond/report              post report / feedback / suggestion back

Set BOND_API_KEY in Railway env vars.  External Bond must pass the same
value in the X-Bond-Key request header.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from ..agents import bond_courier
from ..supabase_client import get_supabase
from .deps import require_bearer

_DAYTONA_ID = "dtn_de4285148e3f305bfb077d37073c7992fa9021760e7cfe2938c761425c975ffc"


# ── Auth helpers ─────────────────────────────────────────────────────────────────

def _require_bond_key(x_bond_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("BOND_API_KEY", "")
    if not expected:
        raise HTTPException(503, "BOND_API_KEY not configured on server")
    if x_bond_key != expected:
        raise HTTPException(401, "Invalid Bond API key")


# ── Pydantic models ─────────────────────────────────────────────────────────────────

class DirectiveIn(BaseModel):
    content: str
    priority: str = "normal"
    metadata: dict | None = None


class ReportIn(BaseModel):
    content: str
    message_type: str = "report"  # report | feedback | suggestion | acknowledgment
    daytona_id: str | None = None
    metadata: dict | None = None


class StatusPatch(BaseModel):
    status: str  # pending | delivered | read | actioned


# ── Internal router (EAGLE EYE) ───────────────────────────────────────────────────────

_internal = APIRouter(dependencies=[Depends(require_bearer)])


@_internal.get("/thread")
def get_thread(limit: int = 50, direction: str = "all") -> dict:
    msgs = bond_courier.thread(limit=limit, direction=direction)
    return {"messages": msgs, "count": len(msgs)}


@_internal.post("/directive")
def send_directive(body: DirectiveIn) -> dict:
    return bond_courier.send_directive(body.content, body.priority, body.metadata)


@_internal.get("/status")
def channel_status() -> dict:
    return bond_courier.run({"action": "status"})


@_internal.patch("/message/{msg_id}")
def update_message_status(msg_id: str, body: StatusPatch) -> dict:
    sb = get_supabase()
    result = (
        sb.table("bond_channel")
        .update({"status": body.status})
        .eq("id", msg_id)
        .execute()
    )
    return {"updated": len(result.data or [])}


# ── External router (Daytona Bond) ─────────────────────────────────────────────────────

_external = APIRouter(dependencies=[Depends(_require_bond_key)])


@_external.get("/inbox")
def external_inbox(limit: int = 10) -> dict:
    """External Bond polls this endpoint to pick up pending IEBC directives."""
    sb = get_supabase()
    rows = (
        sb.table("bond_channel")
        .select("*")
        .eq("direction", "internal_to_external")
        .eq("status", "pending")
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
        .data or []
    )
    if rows:
        ids = [r["id"] for r in rows]
        sb.table("bond_channel").update({"status": "delivered"}).in_("id", ids).execute()
    return {"directives": rows, "count": len(rows)}


@_external.post("/report")
def external_report(body: ReportIn) -> dict:
    """External Bond posts a report / feedback / suggestion to IEBC."""
    valid_types = {"report", "feedback", "suggestion", "acknowledgment"}
    if body.message_type not in valid_types:
        raise HTTPException(400, f"message_type must be one of {valid_types}")
    sb = get_supabase()
    row = {
        "direction":    "external_to_internal",
        "from_label":   "Bond External (Daytona)",
        "message_type": body.message_type,
        "content":      body.content,
        "priority":     "normal",
        "status":       "pending",
        "metadata":     {
            **(body.metadata or {}),
            "daytona_id": body.daytona_id or _DAYTONA_ID,
        },
    }
    result = sb.table("bond_channel").insert(row).execute()
    inserted = result.data[0] if result.data else {}
    return {"status": "received", "id": inserted.get("id")}


# ── Combined export ─────────────────────────────────────────────────────────────────

router = APIRouter()
router.include_router(_internal)
router.include_router(_external)
