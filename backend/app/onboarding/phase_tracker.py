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
    """Send phase email if not already sent; log the transition."""
    log = _log()
    try:
        sb = _db()

        # Check idempotency — has this phase email been sent?
        already_sent = False
        if sb:
            try:
                existing = (
                    sb.table("onboarding_phase_log")
                    .select("id")
                    .eq("carrier_id", str(carrier_id))
                    .eq("phase", new_phase)
                    .maybe_single()
                    .execute()
                )
                already_sent = bool(existing.data)
            except Exception:
                # Table may not exist — fall through and try agent_memory
                pass

        if not already_sent:
            # Try agent_memory as fallback idempotency check
            try:
                from ..agents.memory import remember, recall
                mem_key = f"phase_email_sent:{carrier_id}:{new_phase}"
                existing_mem = recall(mem_key)
                if existing_mem:
                    already_sent = True
            except Exception:
                pass

        if already_sent:
            log.debug("Phase %d email already sent for carrier %s — skipping", new_phase, carrier_id)
            return

        # Get carrier info
        carrier_info: dict = {}
        if sb:
            try:
                r = (
                    sb.table("active_carriers")
                    .select("company_name,email")
                    .eq("id", str(carrier_id))
                    .maybe_single()
                    .execute()
                )
                carrier_info = r.data or {}
            except Exception:
                pass

        carrier_name = carrier_info.get("company_name", "Carrier")
        carrier_email = carrier_info.get("email")

        # Build and send email
        if carrier_email:
            try:
                from .email_templates import get_phase_email
                from ..settings import get_settings
                s = get_settings()

                email_data = get_phase_email(new_phase, carrier_name)

                if s.postmark_server_token:
                    try:
                        from postmarker.core import PostmarkClient  # type: ignore
                        PostmarkClient(server_token=s.postmark_server_token).emails.send(
                            From=s.postmark_from_email,
                            To=carrier_email,
                            Subject=email_data["subject"],
                            HtmlBody=email_data["html"],
                            TextBody=email_data["text"],
                        )
                        log.info("Phase %d email sent to %s (%s)", new_phase, carrier_email, carrier_id)
                    except Exception as e:
                        log.warning("Postmark send failed for phase %d / %s: %s", new_phase, carrier_id, e)
                else:
                    log.info("Phase %d email would send to %s (postmark not configured)", new_phase, carrier_email)
            except Exception as e:
                log.warning("Email build failed for phase %d / %s: %s", new_phase, carrier_id, e)

        # Record in onboarding_phase_log
        if sb:
            try:
                from datetime import datetime, timezone
                sb.table("onboarding_phase_log").insert({
                    "carrier_id": str(carrier_id),
                    "phase": new_phase,
                    "phase_name": PHASE_INFO.get(new_phase, {}).get("name", ""),
                    "email_sent": bool(carrier_email),
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
            except Exception as e:
                log.debug("onboarding_phase_log insert failed (table may not exist): %s", e)

        # Record in agent memory
        try:
            from ..agents.memory import remember
            remember(
                f"phase_email_sent:{carrier_id}:{new_phase}",
                {"carrier_id": carrier_id, "phase": new_phase, "sent": True},
            )
        except Exception:
            pass

    except Exception as e:
        log.error("advance_phase_notification failed for carrier %s phase %d: %s", carrier_id, new_phase, e)
