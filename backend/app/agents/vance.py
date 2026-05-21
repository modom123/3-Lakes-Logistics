"""Vance — Step 35. Outbound prospecting voice (Bland AI + Claude).

Uses Bland AI for high-volume outbound calling (~$0.06/min base + Claude LLM).
Much cheaper than Vapi, cleaner API, better for 1000+ calls/month.
"""
from __future__ import annotations

from typing import Any

from .bland_client import start_outbound_call, handle_bland_webhook
from ..logging_service import log_agent
from . import memory as mem


def run(payload: dict[str, Any]) -> dict[str, Any]:
    """Start an outbound prospecting call via Bland AI.

    Expected payload:
    {
        "lead_id": "lead_123",
        "phone": "+15551234567",
        "prospect_name": "John Smith",
        "prospect_email": "john@smithtrucking.com",  # needed for follow-up
        "company_name": "Smith Trucking",
        "dot_number": "1234567",  # optional
        "current_pain": "manual dispatch",  # optional
        "webhook_url": "https://api.3lakes.com/webhooks/bland"  # optional
    }
    """
    lead_id = payload.get("lead_id", "")
    phone = payload.get("phone", "")
    prospect_name = payload.get("prospect_name", "Friend")
    prospect_email = payload.get("prospect_email", "")
    company_name = payload.get("company_name", "")
    dot_number = payload.get("dot_number", "")
    current_pain = payload.get("current_pain", "")
    webhook_url = payload.get("webhook_url", "")

    if not phone:
        return {"agent": "vance", "status": "error", "error": "phone number required"}

    result = start_outbound_call(
        lead_id=lead_id,
        phone=phone,
        prospect_name=prospect_name,
        prospect_email=prospect_email,
        company_name=company_name,
        dot_number=dot_number,
        current_pain=current_pain,
        webhook_url=webhook_url,
    )

    return {"agent": "vance", **result}


def handle_webhook(event: dict[str, Any]) -> dict[str, Any]:
    """Handle incoming Bland AI webhook events.
    Writes call outcomes to org brain so Naomi can refine scoring.
    """
    result = handle_bland_webhook(event)

    # Learn from outcome — feed back into Naomi's model
    status   = event.get("status") or event.get("call_status") or ""
    lead_id  = event.get("lead_id") or event.get("metadata", {}).get("lead_id") or ""
    connected = status.lower() in ("completed", "answered", "connected")
    converted = event.get("converted", False) or event.get("booked", False)

    # Read existing call outcomes and update rolling tallies
    existing = mem.recall_value("vance", "call_outcomes") or {}
    total_calls     = int(existing.get("total_calls", 0)) + 1
    connected_count = int(existing.get("connected_count", 0)) + (1 if connected else 0)
    converted_count = int(existing.get("converted_count", 0)) + (1 if converted else 0)
    # Track Tier A calls specifically (Naomi writes lead tier into lead metadata)
    tier_a_calls    = int(existing.get("tier_a_calls", 0))
    tier_a_connected = int(existing.get("tier_a_connected", 0))
    lead_tier = event.get("metadata", {}).get("naomi_tier") or ""
    if lead_tier == "A":
        tier_a_calls += 1
        if connected:
            tier_a_connected += 1

    outcomes = {
        "total_calls":       total_calls,
        "connected_count":   connected_count,
        "converted_count":   converted_count,
        "connect_rate":      round(connected_count / total_calls, 3),
        "convert_rate":      round(converted_count / total_calls, 3),
        "tier_a_calls":      tier_a_calls,
        "tier_a_connected":  tier_a_connected,
        "tier_a_connect_rate": round(tier_a_connected / tier_a_calls, 3) if tier_a_calls else 0,
    }
    mem.remember(
        "vance", "call_outcomes",
        outcomes,
        confidence=min(0.9, 0.3 + total_calls * 0.01),  # grows with sample size
        summary=f"{total_calls} calls · connect={outcomes['connect_rate']:.0%} · convert={outcomes['convert_rate']:.0%} · Tier A accuracy={outcomes['tier_a_connect_rate']:.0%}",
    )
    mem.log_interaction("vance", "naomi", "feedback",
        payload={"lead_id": lead_id, "status": status},
        result={"connected": connected, "converted": converted},
        outcome="success",
        outcome_notes=f"Tier A connect rate now {outcomes['tier_a_connect_rate']:.0%} over {tier_a_calls} calls",
    )
    return result

