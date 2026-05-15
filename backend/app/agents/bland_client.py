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

Your goal: Qualify on: DOT# age, fleet size, current dispatch situation, pain points.
If they're interested, offer a 15-min call with our Commander (human).

Rules:
- Lead with curiosity: "How long you been running your own authority?"
- Listen more than you talk
- If they're not interested, accept it gracefully and wish them well
- Never pressure or follow up too hard
- If they seem open, say: "Perfect. Let me get you scheduled with our Commander for a quick 15-min call tomorrow?"

Script variables available:
- prospect_name: Their name
- company_name: Their company
- dot_number: DOT# (if known)
- current_pain: Their stated pain point (if known)

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

    # Build the conversation context
    context = f"""Calling {prospect_name} at {company_name or 'unknown company'}.
DOT#: {dot_number or 'unknown'}
Known pain point: {current_pain or 'none provided'}
Goal: Qualify and offer demo call with Commander."""

    try:
        payload = {
            "phone_number": phone,
            "task": VANCE_SYSTEM_PROMPT,
            "context": context,
            "model": "claude-opus",  # Use Claude for better reasoning
            "language": "en",
            "voice": "male",  # Neutral, professional voice
            "reduce_latency": True,  # Optimize for conversational speed
            "metadata": {
                "lead_id": lead_id,
                "prospect_name": prospect_name,
                "prospect_email": prospect_email,
                "company_name": company_name,
                "dot_number": dot_number,
            },
        }

        if s.bland_ai_org_id:
            payload["organization_id"] = s.bland_ai_org_id

        if webhook_url:
            payload["webhook_url"] = webhook_url

        r = httpx.post(
            f"{BLAND_API_URL}/calls",
            headers={"Authorization": f"Bearer {s.bland_ai_api_key}"},
            json=payload,
            timeout=20,
        )
        r.raise_for_status()

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
            "cost_estimate": 0.06,  # Base $0.06/min + Claude LLM costs
        }

    except httpx.HTTPError as e:
        error_msg = str(e)
        log_agent(
            "vance",
            "bland_call_failed",
            carrier_id=None,
            payload={"lead_id": lead_id, "phone": phone},
            error=error_msg,
        )
        return {"status": "error", "error": error_msg}
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

        # Parse Bland's analysis for decision signals
        success = analysis.get("success", False)
        reason = analysis.get("reason", "unknown")
        outcome = "interested" if success else "not_interested"

        # Trigger follow-up sequence if interested
        follow_up_result = None
        if outcome == "interested" and prospect_email and phone_number:
            follow_up_result = run_follow_up({
                "lead_id": lead_id,
                "prospect_name": prospect_name,
                "prospect_email": prospect_email,
                "company_name": company_name,
                "phone_number": phone_number,
                "call_outcome": "interested",
                "call_id": call_id,
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
