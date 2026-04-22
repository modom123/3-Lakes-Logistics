"""Vance — Step 35. Outbound prospecting voice (Vapi + ElevenLabs)."""
from __future__ import annotations

from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings


def start_outbound_call(lead_id: str, phone: str, script_vars: dict[str, Any]) -> dict[str, Any]:
    """Trigger a Vapi assistant to dial a prospect."""
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
    except Exception as e:  # noqa: BLE001
        log_agent("vance", "call_failed", payload={"lead_id": lead_id}, error=str(e))
        return {"status": "error", "error": str(e)}


def handle_vapi_event(event: dict[str, Any]) -> None:
    """Stripe-style webhook for Vapi. Events: call.ended, call.transcript."""
    kind = event.get("type") or event.get("event")
    lead_id = (event.get("metadata") or {}).get("lead_id")
    log_agent("vance", f"webhook:{kind}", carrier_id=None, payload={"lead_id": lead_id})


def run(payload: dict[str, Any]) -> dict[str, Any]:
    lead_id = payload.get("lead_id", "")
    phone = payload.get("phone", "")
    return {"agent": "vance", **start_outbound_call(lead_id, phone, payload.get("vars") or {})}
