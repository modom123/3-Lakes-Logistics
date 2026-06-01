"""Vance Follow-Up Agent — fires immediately after an interested call completes.

Sequence:
  1. Email (Calendly + intake link) — if email available
  2. SMS  (Calendly + intake link) — immediate, regardless of email
  3. Schedule 24h SMS reminder    — via leads.stage + APScheduler hourly job
"""
from __future__ import annotations

from typing import Any

from ..prospecting.follow_up import (
    send_follow_up_email,
    send_follow_up_sms,
    schedule_follow_up_reminder,
)
from ..logging_service import log_agent


def run(payload: dict[str, Any]) -> dict[str, Any]:
    """Trigger follow-up sequence for an interested prospect.

    Expected payload (passed from bland_client.handle_bland_webhook):
    {
        "lead_id": "uuid",
        "prospect_name": "John Smith",
        "prospect_email": "john@smithtrucking.com",  # may be empty
        "company_name": "Smith Trucking",
        "phone_number": "+15551234567",
        "call_outcome": "interested",
        "call_id": "bland_call_id"
    }
    """
    # ── carrier check_in branch (called from onboarding_scheduler) ───────────
    if payload.get("task") == "check_in":
        carrier_id = payload.get("carrier_id")
        log_agent(
            "vance_follow_up", "carrier_check_in",
            payload={"carrier_id": carrier_id},
            result="check_in_acknowledged",
        )
        return {"agent": "vance_follow_up", "status": "ok", "task": "check_in", "carrier_id": carrier_id}

    lead_id       = payload.get("lead_id", "")
    prospect_name = payload.get("prospect_name", "")
    prospect_email = payload.get("prospect_email", "")
    company_name  = payload.get("company_name", "")
    phone_number  = payload.get("phone_number", "")
    call_outcome  = payload.get("call_outcome", "")

    if call_outcome != "interested":
        return {
            "agent": "vance_follow_up",
            "status": "skipped",
            "reason": f"outcome was '{call_outcome}', not interested",
        }

    if not phone_number and not prospect_email:
        return {
            "agent": "vance_follow_up",
            "status": "error",
            "error": "need at least phone or email to follow up",
        }

    # Step 1: Email (Calendly + intake links)
    email_result = send_follow_up_email(
        lead_id=lead_id,
        prospect_name=prospect_name,
        prospect_email=prospect_email,
        company_name=company_name,
    )

    # Step 2: Immediate SMS with links
    sms_result = send_follow_up_sms(
        lead_id=lead_id,
        prospect_name=prospect_name,
        phone_number=phone_number,
        reminder=False,
    )

    # Step 3: Schedule 24h reminder SMS in the DB
    reminder_result = schedule_follow_up_reminder(
        lead_id=lead_id,
        prospect_name=prospect_name,
        phone_number=phone_number,
    )

    log_agent(
        "vance_follow_up",
        "sequence_fired",
        payload={"lead_id": lead_id, "prospect": prospect_name, "company": company_name},
        result=(
            f"email={email_result.get('status')} "
            f"sms={sms_result.get('status')} "
            f"reminder={reminder_result.get('status')}"
        ),
    )

    return {
        "agent": "vance_follow_up",
        "status": "success",
        "lead_id": lead_id,
        "email": email_result,
        "sms": sms_result,
        "reminder_24h": reminder_result,
    }
