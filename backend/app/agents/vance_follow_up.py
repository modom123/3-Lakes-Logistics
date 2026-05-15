"""Nova Follow-Up Agent — Step 36.

After Vance qualifies an interested prospect:
1. Send demo video email
2. Schedule 24h SMS reminder if no booking
3. Track conversion funnel
"""
from __future__ import annotations

from typing import Any

from ..prospecting.follow_up import send_follow_up_email, schedule_follow_up_reminder
from ..logging_service import log_agent


def run(payload: dict[str, Any]) -> dict[str, Any]:
    """Trigger follow-up sequence for interested prospects.

    Expected payload (from Vance's webhook handler):
    {
        "lead_id": "lead_123",
        "prospect_name": "John Smith",
        "prospect_email": "john@smithtrucking.com",
        "company_name": "Smith Trucking",
        "phone_number": "+15551234567",
        "call_outcome": "interested",  # or "not_interested", "call_failed"
        "transcript": "...",
        "call_id": "call_abc123"
    }
    """
    lead_id = payload.get("lead_id", "")
    prospect_name = payload.get("prospect_name", "")
    prospect_email = payload.get("prospect_email", "")
    company_name = payload.get("company_name", "")
    phone_number = payload.get("phone_number", "")
    call_outcome = payload.get("call_outcome", "")

    if not call_outcome == "interested":
        return {
            "agent": "nova_follow_up",
            "status": "skipped",
            "reason": f"outcome was {call_outcome}, not interested",
        }

    if not prospect_email or not phone_number:
        return {
            "agent": "nova_follow_up",
            "status": "error",
            "error": "email and phone required for follow-up",
        }

    # Step 1: Send follow-up email with demo video
    email_result = send_follow_up_email(
        lead_id=lead_id,
        prospect_name=prospect_name,
        prospect_email=prospect_email,
        company_name=company_name,
        phone_number=phone_number,
    )

    if email_result.get("status") != "sent":
        return {
            "agent": "nova_follow_up",
            "status": "error",
            "error": f"email failed: {email_result.get('error')}",
        }

    # Step 2: Schedule SMS reminder for 24h later
    reminder_result = schedule_follow_up_reminder(
        lead_id=lead_id,
        prospect_name=prospect_name,
        phone_number=phone_number,
    )

    log_agent(
        "nova_follow_up",
        "follow_up_sequence_started",
        payload={
            "lead_id": lead_id,
            "prospect": prospect_name,
            "company": company_name,
        },
        result="email sent + 24h reminder scheduled",
    )

    return {
        "agent": "nova_follow_up",
        "status": "success",
        "lead_id": lead_id,
        "prospect": prospect_name,
        "email_sent": True,
        "message_id": email_result.get("message_id"),
        "sms_reminder_scheduled_at": reminder_result.get("remind_at"),
    }
