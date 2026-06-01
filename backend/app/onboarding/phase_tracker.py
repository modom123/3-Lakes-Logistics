"""Maps 30-step execution engine to 10 client-facing onboarding phases."""
from __future__ import annotations

log_ref = None


def _log():
    global log_ref
    if log_ref is None:
        try:
            from ..logging_service import get_logger
            log_ref = get_logger("3ll.onboarding.phase_tracker")
        except Exception:
            import logging
            log_ref = logging.getLogger("3ll.onboarding.phase_tracker")
    return log_ref


# Backend step → client phase (1-10)
PHASE_MAP: dict[int, int] = {
    1: 1, 2: 1,
    3: 2, 4: 2, 5: 2,
    6: 3, 7: 3,
    8: 4, 9: 4,
    10: 5, 11: 5, 12: 5, 13: 5,
    14: 6, 15: 6,
    16: 7, 17: 7, 18: 7, 19: 7,
    20: 7,   # step 20 (vance call) also phase 7 — no gap
    21: 8, 22: 8,
    23: 9, 24: 9, 25: 9, 26: 9,
    27: 10, 28: 10, 29: 10, 30: 10,
}

PHASE_INFO: dict[int, dict] = {
    1: {
        "name": "Application Received",
        "description": "Your carrier application has been received and is being reviewed.",
        "what_carrier_needs_to_do": "Sit tight — we're reviewing your submission.",
        "what_3lakes_does": "Performs initial intake and duplicate check.",
        "estimated_days": 1,
    },
    2: {
        "name": "DOT & Safety Verification",
        "description": "We're verifying your DOT number and safety record via FMCSA.",
        "what_carrier_needs_to_do": "No action needed — we'll contact you with results.",
        "what_3lakes_does": "Runs FMCSA SAFER lookup, CSA score, and safety light check.",
        "estimated_days": 1,
    },
    3: {
        "name": "Insurance Review",
        "description": "We're reviewing your insurance documentation.",
        "what_carrier_needs_to_do": "Upload a current Certificate of Insurance if requested.",
        "what_3lakes_does": "Verifies policy number, expiry date, and schedules renewal alerts.",
        "estimated_days": 2,
    },
    4: {
        "name": "ELD & Equipment Setup",
        "description": "We're connecting your Electronic Logging Device to our system.",
        "what_carrier_needs_to_do": "Provide your ELD provider name and API credentials.",
        "what_3lakes_does": "Detects ELD provider and syncs credentials for live tracking.",
        "estimated_days": 1,
    },
    5: {
        "name": "Banking & Payment Setup",
        "description": "We're setting up your payment account so you get paid fast.",
        "what_carrier_needs_to_do": "Complete the Stripe payment setup link we'll send you.",
        "what_3lakes_does": "Collects banking info, verifies account, creates Stripe customer and subscription.",
        "estimated_days": 2,
    },
    6: {
        "name": "Agreement & E-Signature",
        "description": "Your carrier agreement is ready for your electronic signature.",
        "what_carrier_needs_to_do": "Sign the carrier agreement via the link in your email.",
        "what_3lakes_does": "Sends agreement, tracks e-signature completion.",
        "estimated_days": 1,
    },
    7: {
        "name": "Account Activation",
        "description": "Your account is being activated in our system.",
        "what_carrier_needs_to_do": "Watch for our welcome email with login instructions.",
        "what_3lakes_does": "Ingests signed contract into CLM, sets carrier active, decrements inventory, sends welcome email.",
        "estimated_days": 1,
    },
    8: {
        "name": "Documents & Vault",
        "description": "Your document folder is being created in our secure vault.",
        "what_carrier_needs_to_do": "Upload any remaining documents via the document portal.",
        "what_3lakes_does": "Creates your document folder and uploads your signed agreement.",
        "estimated_days": 1,
    },
    9: {
        "name": "System Access & Training",
        "description": "Your carrier dashboard is being activated.",
        "what_carrier_needs_to_do": "Log in to your dashboard and complete the orientation.",
        "what_3lakes_does": "Schedules check-in, activates dashboard, checks loyalty tier, converts lead record.",
        "estimated_days": 1,
    },
    10: {
        "name": "Ready to Haul",
        "description": "Congratulations — you're fully onboarded and ready to haul!",
        "what_carrier_needs_to_do": "Browse available loads and book your first haul.",
        "what_3lakes_does": "Syncs to Airtable, notifies dispatch team, creates fleet asset record, marks onboarding complete.",
        "estimated_days": 0,
    },
}


def _db():
    try:
        from ..supabase_client import get_supabase
        return get_supabase()
    except Exception:
        return None


def get_carrier_phase(carrier_id: str) -> dict:
    """Return current client-facing phase for a carrier."""
    log = _log()
    sb = _db()
    highest_step = 0
    if sb:
        try:
            rows = (
                sb.table("execution_engine_log")
                .select("step_number")
                .eq("carrier_id", str(carrier_id))
                .eq("status", "complete")
                .execute()
                .data or []
            )
            for r in rows:
                s = int(r.get("step_number", 0))
                if s > highest_step:
                    highest_step = s
        except Exception as e:
            log.warning("get_carrier_phase db error: %s", e)

    phase = PHASE_MAP.get(highest_step, 1)
    # If step 0 (no steps complete), stay at phase 1
    if highest_step == 0:
        phase = 1

    info = PHASE_INFO.get(phase, PHASE_INFO[1])

    # pct_complete: completed steps / 30
    pct_complete = round((highest_step / 30) * 100, 1)

    # next_action
    next_steps = [k for k, v in PHASE_MAP.items() if v == phase and k > highest_step]
    if highest_step >= 30:
        next_action = "Onboarding complete — start hauling!"
    elif next_steps:
        next_action = info["what_carrier_needs_to_do"]
    else:
        next_action = PHASE_INFO.get(phase + 1, {}).get("what_carrier_needs_to_do", "Awaiting next phase")

    return {
        "phase": phase,
        "phase_name": info["name"],
        "step": highest_step,
        "pct_complete": pct_complete,
        "next_action": next_action,
    }


def get_all_carriers_phases() -> list[dict]:
    """Return phase status for all active carriers (Eagle Eye staff view)."""
    log = _log()
    sb = _db()
    if not sb:
        return []
    try:
        carriers = (
            sb.table("active_carriers")
            .select("id,company_name,status,created_at")
            .execute()
            .data or []
        )
    except Exception as e:
        log.warning("get_all_carriers_phases: %s", e)
        return []

    results = []
    for c in carriers:
        cid = c.get("id")
        if not cid:
            continue
        phase_data = get_carrier_phase(str(cid))
        # days in phase — estimate from created_at (simplified)
        import datetime
        created_at = c.get("created_at", "")
        days_in_system = 0
        if created_at:
            try:
                dt = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                days_in_system = (datetime.datetime.now(datetime.timezone.utc) - dt).days
            except Exception:
                pass

        results.append({
            "carrier_id": str(cid),
            "company_name": c.get("company_name", "Unknown"),
            "status": c.get("status", ""),
            "days_in_system": days_in_system,
            **phase_data,
        })
    return results


def advance_phase_notification(carrier_id: str, new_phase: int) -> None:
    """Log a phase transition. No email sent here — reminders fire only when carrier stalls."""
    log = _log()
    try:
        sb = _db()
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        if sb:
            try:
                sb.table("onboarding_phase_log").upsert({
                    "carrier_id": str(carrier_id),
                    "phase": new_phase,
                    "phase_name": PHASE_INFO.get(new_phase, {}).get("name", ""),
                    "advanced_at": now,
                }, on_conflict="carrier_id,phase").execute()
            except Exception:
                pass

        log.info("Carrier %s advanced to phase %d (%s)",
                 carrier_id, new_phase, PHASE_INFO.get(new_phase, {}).get("name", ""))
    except Exception as e:
        log.error("advance_phase_notification failed carrier=%s phase=%d: %s", carrier_id, new_phase, e)


def send_stall_reminder(carrier_id: str, stalled_days: int) -> bool:
    """Send a single reminder email when a carrier has stopped progressing.

    Called by the scheduled task executor (onboarding_scheduler.py) when a
    carrier hasn't advanced a phase in stalled_days. Returns True if sent.
    """
    log = _log()
    try:
        sb = _db()
        carrier_info: dict = {}
        if sb:
            try:
                r = (
                    sb.table("active_carriers")
                    .select("company_name,email,status")
                    .eq("id", str(carrier_id))
                    .maybe_single()
                    .execute()
                )
                carrier_info = r.data or {}
            except Exception:
                pass

        carrier_email = carrier_info.get("email")
        carrier_name = carrier_info.get("company_name", "there")
        if not carrier_email:
            return False

        phase_data = get_carrier_phase(carrier_id)
        current_phase = phase_data.get("phase", 1)
        phase_name = phase_data.get("phase_name", "")
        next_action = phase_data.get("next_action", "complete your application")

        from .email_templates import build_stall_reminder_email
        from ..settings import get_settings
        s = get_settings()
        if not s.postmark_server_token:
            log.info("Stall reminder would send to %s (postmark not configured)", carrier_email)
            return False

        email_data = build_stall_reminder_email(
            carrier_name=carrier_name,
            current_phase=current_phase,
            phase_name=phase_name,
            next_action=next_action,
            stalled_days=stalled_days,
        )
        try:
            from postmarker.core import PostmarkClient  # type: ignore
            PostmarkClient(server_token=s.postmark_server_token).emails.send(
                From=s.postmark_from_email,
                To=carrier_email,
                Subject=email_data["subject"],
                HtmlBody=email_data["html"],
                TextBody=email_data["text"],
            )
            log.info("Stall reminder sent to %s (phase %d, stalled %d days)", carrier_email, current_phase, stalled_days)
            return True
        except Exception as e:
            log.warning("Postmark stall reminder failed for %s: %s", carrier_id, e)
            return False
    except Exception as e:
        log.error("send_stall_reminder failed carrier=%s: %s", carrier_id, e)
        return False
