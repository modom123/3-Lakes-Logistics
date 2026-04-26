"""Vance — Step 35. Outbound prospecting voice (Vapi + ElevenLabs)."""
from __future__ import annotations

from datetime import datetime, timezone
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
    """Process Vapi webhook: call.ended, transcript, recording."""
    from ..supabase_client import get_supabase

    kind = event.get("type") or event.get("event") or ""
    lead_id = (event.get("metadata") or {}).get("lead_id")
    now = datetime.now(timezone.utc).isoformat()

    log_agent("vance", f"webhook:{kind}", carrier_id=None, payload={"lead_id": lead_id})

    if not lead_id:
        return

    sb = get_supabase()

    if kind == "call.ended":
        call_data = event.get("call") or {}
        duration_s = call_data.get("duration") or 0
        outcome = "voicemail" if duration_s < 10 else "answered"
        lead = (sb.table("leads").select("call_count")
                  .eq("id", lead_id).maybe_single().execute().data or {})
        sb.table("leads").update({
            "stage":        "contacted",
            "last_touch_at": now,
            "call_count":   (lead.get("call_count") or 0) + 1,
            "vapi_call_id": call_data.get("id"),
        }).eq("id", lead_id).execute()
        log_agent("vance", "call_ended",
                  payload={"lead_id": lead_id, "duration_s": duration_s, "outcome": outcome})

    elif kind in ("transcript.partial", "transcript.final"):
        transcript = event.get("transcript", "")
        if transcript:
            sb.table("agent_log").insert({
                "agent":   "vance",
                "action":  "call_transcript",
                "payload": {"lead_id": lead_id, "kind": kind},
                "result":  transcript[:2000],
            }).execute()
            # Store last transcript on lead record for quick access
            sb.table("leads").update({
                "last_call_transcript": transcript[:500],
            }).eq("id", lead_id).execute()

    elif kind == "call.recording.done":
        recording_url = (
            (event.get("recording") or {}).get("url")
            or event.get("recordingUrl", "")
        )
        if recording_url:
            sb.table("leads").update(
                {"last_call_recording_url": recording_url}
            ).eq("id", lead_id).execute()
            sb.table("agent_log").insert({
                "agent":   "vance",
                "action":  "call_recording",
                "payload": {"lead_id": lead_id},
                "result":  recording_url,
            }).execute()


def run(payload: dict[str, Any]) -> dict[str, Any]:
    lead_id = payload.get("lead_id", "")
    phone = payload.get("phone", "")
    return {"agent": "vance", **start_outbound_call(lead_id, phone, payload.get("vars") or {})}
