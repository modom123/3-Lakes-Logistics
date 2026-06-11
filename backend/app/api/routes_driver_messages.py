"""Driver-facing messaging endpoints for the Light Fleet PWA.

Endpoints (all require driver session token):
  GET  /api/messages/thread?after=<iso>  — fetch messages for the authenticated driver
  POST /api/messages/send                — driver sends a message to dispatch
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from .routes_driver_auth import require_driver_token

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _driver_phone(driver_id: str) -> str | None:
    """Resolve driver phone — checks both CDL drivers and light fleet drivers."""
    sb = get_supabase()
    try:
        r = sb.table("drivers").select("phone_e164").eq("id", driver_id).maybe_single().execute()
        if r.data and r.data.get("phone_e164"):
            return r.data["phone_e164"]
    except Exception:
        pass
    try:
        r = (
            sb.table("light_vehicle_drivers")
            .select("phone")
            .eq("id", driver_id)
            .maybe_single()
            .execute()
        )
        return (r.data or {}).get("phone")
    except Exception:
        return None


@router.get("/thread")
def driver_message_thread(
    after: str | None = None,
    limit: int = 60,
    session: dict = Depends(require_driver_token),
) -> dict:
    """Return messages for the authenticated driver's thread."""
    driver_id = session["driver_id"]
    phone = _driver_phone(driver_id)
    if not phone:
        return {"messages": [], "driver_id": driver_id}

    try:
        q = (
            get_supabase()
            .table("driver_messages")
            .select("*")
            .eq("driver_phone", phone)
            .order("created_at", desc=False)
            .limit(limit)
        )
        if after:
            q = q.gt("created_at", after)
        rows = q.execute().data or []
    except Exception:
        rows = []

    return {"messages": rows, "driver_id": driver_id, "phone": phone}


class SendMessageReq(BaseModel):
    phone: str
    body: str


@router.post("/send")
def driver_send_message(
    req: SendMessageReq,
    session: dict = Depends(require_driver_token),
) -> dict:
    """Driver sends a message to dispatch. Stored as inbound; dispatchers see it in the comms panel."""
    driver_id = session["driver_id"]
    phone = req.phone or _driver_phone(driver_id) or req.phone

    try:
        get_supabase().table("driver_messages").insert({
            "direction":    "inbound",
            "driver_phone": phone,
            "body":         req.body.strip(),
            "driver_id":    driver_id,
            "msg_type":     "text",
            "read":         False,
            "created_at":   _now(),
        }).execute()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    log_agent("driver_messages", "send", payload={"driver_id": driver_id}, result="stored")
    return {"ok": True}
