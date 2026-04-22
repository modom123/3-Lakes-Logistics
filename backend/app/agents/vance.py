"""Vance — AI Ops head + outbound voice (step 61).

`run` supports two kinds:
  - kind="call": dial a lead via Vapi (legacy behavior).
  - kind="orchestrate_cycle": walk the priority queue, enqueue scheduled
    work for every agent that has deadlines coming due.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings


def start_outbound_call(lead_id: str, phone: str, script_vars: dict[str, Any]) -> dict[str, Any]:
    s = get_settings()
    if not s.vapi_api_key or not s.vapi_assistant_id_vance:
        return {"status": "stub", "reason": "vapi_not_configured"}
    try:
        r = httpx.post(
            "https://api.vapi.ai/call",
            headers={"Authorization": f"Bearer {s.vapi_api_key}"},
            json={
                "assistantId": s.vapi_assistant_id_vance,
                "phoneNumberId": s.vapi_phone_number_id,
                "customer": {"number": phone},
                "metadata": {"lead_id": lead_id, **script_vars},
            },
            timeout=20,
        )
        r.raise_for_status()
        call = r.json()
        log_agent("vance", "call_started", payload={"lead_id": lead_id}, result=call.get("id"))
        return {"status": "started", "call_id": call.get("id")}
    except Exception as exc:  # noqa: BLE001
        log_agent("vance", "call_failed", payload={"lead_id": lead_id}, error=str(exc))
        return {"status": "error", "error": str(exc)}


def handle_vapi_event(event: dict[str, Any]) -> None:
    kind = event.get("type") or event.get("event")
    lead_id = (event.get("metadata") or {}).get("lead_id")
    log_agent("vance", f"webhook:{kind}", payload={"lead_id": lead_id})


def orchestrate_cycle() -> dict[str, Any]:
    """Look ahead 15 min and enqueue any due scheduled work."""
    from . import router as agent_router
    horizon = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    try:
        from ..supabase_client import get_supabase
        pending = (
            get_supabase().table("agent_tasks")
            .select("id, agent, kind")
            .eq("status", "pending")
            .lte("run_at", horizon).limit(200).execute()
        ).data or []
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    log_agent("vance", "orchestrate_cycle", result=f"pending={len(pending)}")
    if not pending:
        # Top-up "always on" health jobs
        agent_router.enqueue("pulse", "kpi_snapshot", {})
    return {"status": "ok", "pending": len(pending)}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    kind = payload.get("kind") or "call"
    if kind == "orchestrate_cycle":
        return {"agent": "vance", **orchestrate_cycle()}
    lead_id = payload.get("lead_id", "")
    phone = payload.get("phone", "")
    return {"agent": "vance", **start_outbound_call(lead_id, phone, payload.get("vars") or {})}
