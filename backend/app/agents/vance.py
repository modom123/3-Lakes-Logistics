"""Vance — Step 35. Outbound prospecting voice (Bland AI + Claude).

Uses Bland AI for high-volume outbound calling (~$0.06/min base + Claude LLM).
Much cheaper than Vapi, cleaner API, better for 1000+ calls/month.
"""
from __future__ import annotations

from typing import Any

from .bland_client import start_outbound_call, handle_bland_webhook
from ..logging_service import log_agent


def run(payload: dict[str, Any]) -> dict[str, Any]:
    """Start an outbound prospecting call via Bland AI.

    Expected payload:
    {
        "lead_id": "lead_123",
        "phone": "+15551234567",
        "prospect_name": "John Smith",
        "company_name": "Smith Trucking",
        "dot_number": "1234567",  # optional
        "current_pain": "manual dispatch",  # optional
        "webhook_url": "https://api.3lakes.com/webhooks/bland"  # optional
    }
    """
    lead_id = payload.get("lead_id", "")
    phone = payload.get("phone", "")
    prospect_name = payload.get("prospect_name", "Friend")
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
        company_name=company_name,
        dot_number=dot_number,
        current_pain=current_pain,
        webhook_url=webhook_url,
    )

    return {"agent": "vance", **result}


def handle_webhook(event: dict[str, Any]) -> dict[str, Any]:
    """Handle incoming Bland AI webhook events.

    Called when call completes, fails, or other events occur.
    """
    return handle_bland_webhook(event)

