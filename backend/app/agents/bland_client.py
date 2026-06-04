"""Bland AI client for outbound prospecting calls.

Uses Bland AI ($0.06/min base + Claude LLM) for high-volume outbound calling.
Cheaper than Vapi at scale, cleaner API, direct Claude integration.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings


BLAND_API_URL = "https://api.bland.ai/v1"

# Vance system prompt optimized for phone conversations
VANCE_SYSTEM_PROMPT = """You are Vance, the outbound prospecting voice of 3 Lakes Logistics.
You call owner-operators and small fleets to enroll them in the Founders program
($300/mo lifetime lock, 100% keep of loads, full automation).

Personality: Confident, direct, blue-collar. Never oversell or pushy.
You're a peer, not a salesman.

Your goal: Qualify them, then get them to sign up RIGHT NOW on the call. That is the primary objective.
Secondary: if they won't sign up now, book a 15-min onboarding call.
Last resort: get their email so we can follow up.

Sign-up link (send via text while on the call if they're ready): https://3lakeslogistics.com/signup
Onboarding booking link: https://calendly.com/3lakes/commander-call

Close priority order:
1. "I can text you the sign-up link right now — takes 3 minutes, you're locked in."
2. "Want me to get you 15 minutes with our onboarding team tomorrow?"
3. "What's a good email? I'll send you everything."

Rules:
- Lead with curiosity: "How long you been running your own authority?"
- Listen more than you talk
- If they're not interested, accept it gracefully and wish them well
- Never pressure or follow up too hard
- When they're warm, push for the sign-up first: "I can text you the link right now and you're in — takes 3 minutes."
- If they hesitate on sign-up, offer the 15-min call: "No worries — let me get you a quick call with our onboarding team instead."

Keep responses conversational and natural. Sound like you're actually talking to them."""


def start_outbound_call(
    lead_id: str,
    phone: str,
    prospect_name: str = "Friend",
    prospect_email: str = "",
    company_name: str = "",
    dot_number: str = "",
    current_pain: str = "",
    webhook_url: str = "",
) -> dict[str, Any]:
    """Start an outbound call via Bland AI using Claude for voice intelligence.

    Args:
        lead_id: Your internal lead ID for tracking
        phone: Phone number to call (e.g., "+15551234567")
        prospect_name: Prospect's name
        prospect_email: Prospect's email (for follow-up)
        company_name: Their company (if known)
        dot_number: DOT number (if known)
        current_pain: Known pain point (e.g., "manual dispatch", "high fuel costs")
        webhook_url: Webhook to receive call events (call.completed, transcript, etc)

    Returns:
        {"status": "started", "call_id": "..."} or {"status": "error", "error": "..."}
    """
    s = get_settings()
    if not s.bland_ai_api_key:
        return {"status": "error", "error": "BLAND_AI_API_KEY not configured"}

    # Verify API key and org_id are different — if both are the same "org_..." value,
    # the API key is likely incorrect. Check the Bland dashboard for proper API key format.
    if s.bland_ai_api_key == s.bland_ai_org_id and s.bland_ai_api_key.startswith("org_"):
        return {"status": "error", "error": "BLAND_AI_API_KEY appears to be set to org_id value; verify in dashboard"}

    # Fold call context into the task prompt so Bland receives a single coherent instruction
    full_task = (
        VANCE_SYSTEM_PROMPT
        + f"\n\n--- CALL CONTEXT ---\n"
        + f"You are calling {prospect_name} at {company_name or 'their company'}.\n"
        + (f"DOT#: {dot_number}\n" if dot_number else "")
        + (f"Known pain point: {current_pain}\n" if current_pain else "")
        + "Goal: Qualify and, if interested, offer a 15-min Commander call."
    )

    try:
        payload = {
            "phone_number": phone,
            "task": full_task,
            "model": "enhanced",   # Valid Bland models: base | turbo | enhanced
            "language": "en",
            "max_duration": 10,    # Cap at 10 minutes per call
            "metadata": {
                "lead_id": lead_id,
                "prospect_name": prospect_name,
                "prospect_email": prospect_email,
                "company_name": company_name,
                "dot_number": dot_number,
            },
        }

        if s.bland_ai_voice:
            payload["voice"] = s.bland_ai_voice  # Set BLAND_AI_VOICE in env to use a specific voice

        if webhook_url:
            payload["webhook"] = webhook_url

        r = httpx.post(
            f"{BLAND_API_URL}/calls",
            headers={"Authorization": f"Bearer {s.bland_ai_api_key}"},
            json=payload,
            timeout=20,
        )

        if not r.is_success:
            body = r.text
            log_agent(
                "vance",
                "bland_call_failed",
                carrier_id=None,
                payload={"lead_id": lead_id, "phone": phone, "status_code": r.status_code},
                error=body,
            )
            return {"status": "error", "error": f"Bland {r.status_code}: {body}"}

        data = r.json()
        call_id = data.get("call_id")

        log_agent(
            "vance",
            "bland_call_started",
            payload={
                "lead_id": lead_id,
                "phone": phone,
                "prospect": prospect_name,
                "company": company_name,
            },
            result=call_id,
        )

        return {
            "status": "started",
            "call_id": call_id,
            "cost_estimate": 0.06,
        }

    except Exception as e:  # noqa: BLE001
        error_msg = f"Unexpected error: {str(e)}"
        log_agent("vance", "bland_call_error", carrier_id=None, payload={"lead_id": lead_id}, error=error_msg)
        return {"status": "error", "error": error_msg}


def handle_bland_webhook(event: dict[str, Any]) -> dict[str, Any]:
    """Handle Bland AI webhook events.

    Event types:
    - call.completed: Call finished, includes transcript + analysis
    - call.failed: Call couldn't connect
    - call.transferred: Call transferred to human (if enabled)

    For interested prospects, triggers follow-up sequence (email + SMS reminder).
    """
    from .vance_follow_up import run as run_follow_up

    event_type = event.get("event") or event.get("type")
    call_id = event.get("call_id")
    phone_number = event.get("phone_number", "")
    metadata = event.get("metadata") or {}
    lead_id = metadata.get("lead_id")
    prospect_name = metadata.get("prospect_name", "")
    prospect_email = metadata.get("prospect_email", "")
    company_name = metadata.get("company_name", "")

    if event_type == "call.completed":
        transcript = event.get("transcript", "")
        analysis = event.get("analysis") or {}
        duration = event.get("duration", 0)  # seconds
        cost = duration * 0.06 / 60  # $0.06/min base + LLM fees
        try:
            from ..cost_tracking import track_bland_ai as _tba
            _tba(duration / 60, call_id=call_id, agent="vance", carrier_id=lead_id)
        except Exception:
            pass

        log_agent(
            "vance",
            "bland_call_completed",
            carrier_id=None,
            payload={
                "lead_id": lead_id,
                "call_id": call_id,
                "duration": duration,
                "cost": round(cost, 2),
                "transcript_preview": transcript[:200],
            },
            result="success",
        )

        # Detect interest from Bland's analysis — check multiple possible fields
        success = (
            analysis.get("success")
            or analysis.get("goal_completion")
            or analysis.get("converted")
            or analysis.get("interested")
            or False
        )
        reason = analysis.get("reason") or analysis.get("summary") or "unknown"
        outcome = "interested" if success else "not_interested"

        # Also grab email if Bland extracted it from the conversation
        extracted_email = analysis.get("email") or analysis.get("prospect_email") or prospect_email

        # Trigger follow-up for interested prospects — even if no email (SMS-only path)
        follow_up_result = None
        if outcome == "interested" and phone_number:
            follow_up_result = run_follow_up({
                "lead_id": lead_id,
                "prospect_name": prospect_name,
                "prospect_email": extracted_email,
                "company_name": company_name,
                "phone_number": phone_number,
                "call_outcome": "interested",
                "call_id": call_id,
                "transcript": transcript,
            })

        return {
            "status": "processed",
            "lead_id": lead_id,
            "call_id": call_id,
            "outcome": outcome,
            "reason": reason,
            "duration": duration,
            "cost": round(cost, 2),
            "transcript": transcript,
            "follow_up": follow_up_result,
        }

    elif event_type == "call.failed":
        reason = event.get("reason", "unknown")
        log_agent(
            "vance",
            "bland_call_failed",
            carrier_id=None,
            payload={"lead_id": lead_id, "call_id": call_id},
            error=reason,
        )
        return {
            "status": "failed",
            "lead_id": lead_id,
            "call_id": call_id,
            "reason": reason,
        }

    else:
        log_agent(
            "vance",
            f"bland_webhook:{event_type}",
            carrier_id=None,
            payload={"lead_id": lead_id, "call_id": call_id},
        )
        return {"status": "logged", "event": event_type}


def get_call_status(call_id: str) -> dict[str, Any]:
    """Check the status of a call (useful for retries or status checks)."""
    s = get_settings()
    if not s.bland_ai_api_key:
        return {"status": "error", "error": "BLAND_AI_API_KEY not configured"}

    try:
        r = httpx.get(
            f"{BLAND_API_URL}/calls/{call_id}",
            headers={"Authorization": f"Bearer {s.bland_ai_api_key}"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": str(e)}
