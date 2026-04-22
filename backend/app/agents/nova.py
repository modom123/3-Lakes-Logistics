"""Nova — Driver support inbox + broker check-call emails (step 68)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..integrations.email import send_email
from ..logging_service import log_agent

CHECK_CALL_TEMPLATE = """Hi {broker_name},

Quick update on load {load_number} ({origin} → {dest}):

  Status:   {status}
  Location: {current_location}
  ETA:      {eta}
  Driver:   {driver_name} ({driver_phone})

Reach out anytime.
— 3 Lakes Logistics Dispatch
"""


def compose_check_call(load: dict[str, Any]) -> str:
    return CHECK_CALL_TEMPLATE.format(
        broker_name=load.get("broker_name", "there"),
        load_number=load.get("load_number", "n/a"),
        origin=f"{load.get('origin_city')}, {load.get('origin_state')}",
        dest=f"{load.get('dest_city')}, {load.get('dest_state')}",
        status=load.get("status", "in_transit"),
        current_location=load.get("current_location", "en route"),
        eta=load.get("eta", "on schedule"),
        driver_name=load.get("driver_name", "on-file"),
        driver_phone=load.get("driver_phone", ""),
    )


def open_thread(*, carrier_id: str | None, driver_id: str | None,
                channel: str, subject: str | None, first_message: str,
                author: str) -> str | None:
    try:
        from ..supabase_client import get_supabase
        sb = get_supabase()
        now = datetime.now(timezone.utc).isoformat()
        th = sb.table("support_threads").insert({
            "carrier_id": carrier_id, "driver_id": driver_id,
            "channel": channel, "subject": subject or "(no subject)",
            "status": "open", "assigned_agent": "nova",
            "last_message_at": now,
        }).execute()
        tid = (th.data or [{}])[0].get("id")
        if tid:
            sb.table("support_messages").insert({
                "thread_id": tid, "direction": "in",
                "author": author, "body": first_message,
            }).execute()
        return tid
    except Exception as exc:  # noqa: BLE001
        log_agent("nova", "thread_open_failed", error=str(exc))
        return None


def reply(thread_id: str, body: str) -> dict[str, Any]:
    try:
        from ..supabase_client import get_supabase
        sb = get_supabase()
        sb.table("support_messages").insert({
            "thread_id": thread_id, "direction": "out",
            "author": "nova", "body": body,
        }).execute()
        sb.table("support_threads").update({
            "last_message_at": datetime.now(timezone.utc).isoformat(),
            "status": "waiting",
        }).eq("id", thread_id).execute()
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    kind = payload.get("kind") or "check_call"
    if kind == "open_thread":
        tid = open_thread(
            carrier_id=payload.get("carrier_id"),
            driver_id=payload.get("driver_id"),
            channel=payload.get("channel") or "email",
            subject=payload.get("subject"),
            first_message=payload.get("body") or "",
            author=payload.get("from") or "unknown",
        )
        return {"agent": "nova", "status": "ok" if tid else "error", "thread_id": tid}
    if kind == "reply":
        return {"agent": "nova", **reply(payload.get("thread_id") or "", payload.get("body") or "")}
    body = compose_check_call(payload)
    to = payload.get("broker_email")
    if to:
        send_email(to, f"Load {payload.get('load_number')} update", body, tag="check_call")
    return {"agent": "nova", "status": "ok",
            "subject": f"Load {payload.get('load_number')} update", "body": body}
