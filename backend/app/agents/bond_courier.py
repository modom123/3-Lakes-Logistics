"""Bond Courier — bidirectional message bridge between IEBC Internal
James Bond and the External James Bond hosted on Daytona.

Courier actions (pass as payload['action']):
  send_directive  IEBC → External Bond  (task / question / data)
  poll            pull unread External → Internal messages
  thread          full conversation thread (both directions)
  status          connection health + message counts
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from . import memory as mem

_NAME = "bond_courier"
_DAYTONA_SANDBOX_ID = "2a50d3c2-f813-49c0-8dec-f9248581c5c6"


def send_directive(
    content: str,
    priority: str = "normal",
    metadata: dict | None = None,
) -> dict[str, Any]:
    sb = get_supabase()
    row = {
        "direction":    "internal_to_external",
        "from_label":   "IEBC Internal",
        "message_type": "directive",
        "content":      content,
        "priority":     priority,
        "status":       "pending",
        "metadata":     metadata or {"sandbox_id": _DAYTONA_SANDBOX_ID},
    }
    result = sb.table("bond_channel").insert(row).execute()
    inserted = result.data[0] if result.data else {}
    mem.remember(
        _NAME, "last_directive_sent",
        {"content": content[:120], "priority": priority, "id": inserted.get("id")},
        confidence=0.8,
        summary=f"Directive sent to External Bond: {content[:60]}",
    )
    log_agent(_NAME, "send_directive",
              payload={"priority": priority},
              result=f"id={inserted.get('id')} content={content[:60]}")
    return {"status": "sent", "message": inserted}


def poll_external(limit: int = 20) -> list[dict[str, Any]]:
    sb = get_supabase()
    rows = (
        sb.table("bond_channel")
        .select("*")
        .eq("direction", "external_to_internal")
        .eq("status", "pending")
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
        .data or []
    )
    if rows:
        ids = [r["id"] for r in rows]
        sb.table("bond_channel").update({"status": "read"}).in_("id", ids).execute()
        mem.remember(
            _NAME, "last_external_poll",
            {"count": len(rows), "latest": rows[-1].get("content", "")[:80]},
            confidence=0.7,
            summary=f"Polled {len(rows)} messages from External Bond",
        )
    return rows


def thread(limit: int = 50, direction: str = "all") -> list[dict[str, Any]]:
    sb = get_supabase()
    q = (
        sb.table("bond_channel")
        .select("id,direction,from_label,message_type,content,priority,status,created_at,metadata")
        .order("created_at", desc=False)
        .limit(limit)
    )
    if direction != "all":
        q = q.eq("direction", direction)
    return q.execute().data or []


def run(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action", "status")).lower()

    if action == "send_directive":
        content  = str(payload.get("content", "")).strip()
        priority = str(payload.get("priority", "normal"))
        if not content:
            return {"agent": _NAME, "error": "content is required"}
        result = send_directive(content, priority, payload.get("metadata"))
        return {"agent": _NAME, **result}

    if action == "poll":
        msgs = poll_external(int(payload.get("limit", 20)))
        return {"agent": _NAME, "action": "poll", "messages": msgs, "count": len(msgs)}

    if action == "thread":
        msgs = thread(int(payload.get("limit", 50)), str(payload.get("direction", "all")))
        return {"agent": _NAME, "action": "thread", "messages": msgs, "count": len(msgs)}

    if action == "status":
        sb = get_supabase()
        rows = sb.table("bond_channel").select("direction,status").execute().data or []
        pending_out = sum(1 for r in rows if r["direction"] == "internal_to_external" and r["status"] == "pending")
        unread_in   = sum(1 for r in rows if r["direction"] == "external_to_internal" and r["status"] == "pending")
        return {
            "agent":            _NAME,
            "action":           "status",
            "daytona_sandbox":  _DAYTONA_SANDBOX_ID,
            "total_messages":   len(rows),
            "pending_outbound": pending_out,
            "unread_inbound":   unread_in,
            "channel_active":   True,
        }

    return {"agent": _NAME, "error": f"unknown action: {action}"}
