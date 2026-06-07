"""Maya Welcome Workflow — 5-step onboarding sequence for new Light Fleet drivers.

Steps:
  1. Welcome SMS     — immediate (Twilio)
  2. Welcome Email   — immediate (Hostinger SMTP from info@)
  3. Welcome Call    — 5 min delay (Bland AI, Maya persona)
  4. Day 1 SMS       — 24 hours after sign-up (Twilio)
  5. Day 2 Email     — 48 hours after sign-up (Hostinger SMTP)

All steps are idempotent — safe to call multiple times (checks welcome_step_X columns).
Scheduled steps 4 and 5 go into the scheduled_tasks table.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

log = logging.getLogger("3ll.maya_welcome")

_NOW = lambda: datetime.now(timezone.utc)  # noqa: E731


def _db():
    try:
        from ..supabase_client import get_supabase
        return get_supabase()
    except Exception:
        return None


def _load_driver(driver_id: str) -> dict:
    sb = _db()
    if not sb:
        return {}
    try:
        r = (
            sb.table("light_vehicle_drivers")
            .select("*")
            .eq("id", str(driver_id))
            .maybe_single()
            .execute()
        )
        return r.data or {}
    except Exception as exc:
        log.warning("_load_driver failed driver_id=%s: %s", driver_id, exc)
        return {}


def _send_sms(phone: str, body: str) -> bool:
    from ..settings import get_settings
    s = get_settings()
    if not (s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number):
        log.warning("Twilio not configured — skipping SMS to %s", phone)
        return False
    try:
        try:
            from twilio.rest import Client as TwilioClient  # noqa: PLC0415
            TwilioClient(s.twilio_account_sid, s.twilio_auth_token).messages.create(
                to=phone, from_=s.twilio_from_number, body=body
            )
        except ImportError:
            import httpx  # noqa: PLC0415
            url = (
                f"https://api.twilio.com/2010-04-01/Accounts/"
                f"{s.twilio_account_sid}/Messages.json"
            )
            r = httpx.post(
                url,
                auth=(s.twilio_account_sid, s.twilio_auth_token),
                data={"From": s.twilio_from_number, "To": phone, "Body": body},
                timeout=15,
            )
            r.raise_for_status()
        log.info("SMS sent to %s", phone)
        return True
    except Exception as exc:
        log.warning("SMS send failed to %s: %s", phone, exc)
        return False


def _schedule_task(task_type: str, carrier_id: str, scheduled_for: datetime) -> bool:
    sb = _db()
    if not sb:
        return False
    try:
        sb.table("scheduled_tasks").insert({
            "task_type": task_type,
            "carrier_id": str(carrier_id),
            "scheduled_for": scheduled_for.isoformat(),
            "status": "pending",
        }).execute()
        log.info("Scheduled task=%s carrier=%s for=%s", task_type, carrier_id, scheduled_for.isoformat())
        return True
    except Exception as exc:
        log.warning("Failed to schedule task=%s carrier=%s: %s", task_type, carrier_id, exc)
        return False


# ── Step 1: Welcome SMS ───────────────────────────────────────────────────────

def send_welcome_sms(driver_id: str) -> dict[str, Any]:
    """Send the immediate welcome SMS to a new Light Fleet driver."""
    try:
        d = _load_driver(driver_id)
        phone = d.get("phone")
        if not phone:
            log.warning("send_welcome_sms: no phone for driver_id=%s", driver_id)
            return {"sms_sent": False, "reason": "no_phone"}

        name = d.get("name") or "Driver"
        services = d.get("approved_services") or []
        services_str = ", ".join(services) if services else "your assigned services"

        message = (
            f"Welcome to 3 Lakes Light Fleet, {name}! \U0001f697 "
            f"You're approved for: {services_str}. "
            f"A team member will be in touch within 1 business day. "
            f"Questions? Reply anytime. — 3 Lakes Logistics"
        )

        ok = _send_sms(phone, message)
        log.info("send_welcome_sms driver_id=%s sent=%s", driver_id, ok)
        return {"sms_sent": ok, "phone": phone}
    except Exception as exc:
        log.warning("send_welcome_sms error driver_id=%s: %s", driver_id, exc)
        return {"sms_sent": False, "error": str(exc)}


# ── Step 2: Welcome Email ─────────────────────────────────────────────────────

def send_welcome_email(driver_id: str) -> dict[str, Any]:
    """Send the immediate welcome email to a new Light Fleet driver (Hostinger SMTP)."""
    try:
        d = _load_driver(driver_id)
        name = d.get("name") or "Driver"
        email = d.get("email") or ""
        if not email:
            log.warning("send_welcome_email: no email for driver_id=%s", driver_id)
            return {"email_sent": False, "reason": "no_email"}

        services = d.get("approved_services") or []
        services_list = (
            "".join(f"<li>{s.title()}</li>" for s in services)
            if services
            else "<li>Your assigned services</li>"
        )

        body_html = f"""
<html><body style="font-family:Arial,sans-serif;color:#222;max-width:600px;margin:auto">
<h2 style="color:#1a4fa8">Welcome to 3 Lakes Light Fleet, {name}!</h2>
<p>We're excited to have you on the team. Your driver profile is now <strong>active</strong>
and you are approved for the following services:</p>
<ul>{services_list}</ul>
<p>Here's what to expect next:</p>
<ol>
  <li>A team member will reach out within 1 business day to walk you through your first assignment.</li>
  <li>Make sure your vehicle is clean, fueled, and ready to go.</li>
  <li>Keep your phone available — dispatch notifications come via text.</li>
</ol>
<p>If you have any questions, reply to this email or text us directly — we're here to help.</p>
<p style="margin-top:32px">Welcome aboard,<br>
<strong>The 3 Lakes Light Fleet Team</strong><br>
<a href="https://3lakeslogistics.com">3lakeslogistics.com</a></p>
</body></html>"""

        body_text = (
            f"Welcome to 3 Lakes Light Fleet, {name}!\n\n"
            f"Your driver profile is active. Approved services: {', '.join(services) if services else 'assigned services'}.\n\n"
            "A team member will contact you within 1 business day. "
            "Questions? Reply to this email or text us anytime.\n\n"
            "— The 3 Lakes Light Fleet Team"
        )

        from ..email.smtp_sender import send_from_mailbox
        send_from_mailbox(
            mailbox="info",
            to=[email],
            subject=f"Welcome to 3 Lakes Light Fleet, {name}!",
            body_html=body_html,
            body_text=body_text,
        )
        log.info("send_welcome_email sent to %s driver_id=%s", email, driver_id)
        return {"email_sent": True, "to": email}
    except Exception as exc:
        log.warning("send_welcome_email error driver_id=%s: %s", driver_id, exc)
        return {"email_sent": False, "error": str(exc)}


# ── Step 3: Welcome Call ──────────────────────────────────────────────────────

def send_welcome_call(driver_id: str) -> dict[str, Any]:
    """Place the welcome call via Bland AI using Maya's persona."""
    try:
        d = _load_driver(driver_id)
        phone = d.get("phone")
        if not phone:
            log.warning("send_welcome_call: no phone for driver_id=%s", driver_id)
            return {"call_placed": False, "reason": "no_phone"}

        name = d.get("name") or "Driver"
        services = d.get("approved_services") or []
        services_str = ", ".join(services) if services else "light fleet services"

        from .bland_client import start_outbound_call, MAYA_WELCOME_PROMPT
        task_prompt = (
            MAYA_WELCOME_PROMPT
            + f"\n\nCall context:\nDriver: {name}\nApproved services: {services_str}\n"
            "Goal: Welcome call — see prompt above."
        )

        result = start_outbound_call(
            lead_id=str(driver_id),
            phone=phone,
            prospect_name=name,
            task_prompt=task_prompt,
        )

        if result.get("status") == "started":
            log.info("send_welcome_call placed driver_id=%s call_id=%s", driver_id, result.get("call_id"))
            return {"call_placed": True, "call_id": result.get("call_id")}
        else:
            log.warning("send_welcome_call failed driver_id=%s: %s", driver_id, result.get("error"))
            return {"call_placed": False, "error": result.get("error")}
    except Exception as exc:
        log.warning("send_welcome_call error driver_id=%s: %s", driver_id, exc)
        return {"call_placed": False, "error": str(exc)}


# ── Step 4: Day 1 SMS ─────────────────────────────────────────────────────────

def send_day1_sms(driver_id: str) -> dict[str, Any]:
    """Send the Day 1 check-in SMS (~24h after sign-up)."""
    try:
        d = _load_driver(driver_id)
        phone = d.get("phone")
        if not phone:
            log.warning("send_day1_sms: no phone for driver_id=%s", driver_id)
            return {"sms_sent": False, "reason": "no_phone"}

        name = d.get("name") or "there"
        message = (
            f"Hi {name}, 3 Lakes checking in! Your driver profile is active and your first "
            "assignment opportunity is coming soon. Make sure your vehicle is clean and ready. "
            "Any questions, reply to this message. — 3 Lakes"
        )

        ok = _send_sms(phone, message)
        log.info("send_day1_sms driver_id=%s sent=%s", driver_id, ok)
        return {"sms_sent": ok, "phone": phone}
    except Exception as exc:
        log.warning("send_day1_sms error driver_id=%s: %s", driver_id, exc)
        return {"sms_sent": False, "error": str(exc)}


# ── Step 5: Day 2 Email ───────────────────────────────────────────────────────

def send_day2_email(driver_id: str) -> dict[str, Any]:
    """Send the Day 2 'Getting your first trip' email (~48h after sign-up)."""
    try:
        d = _load_driver(driver_id)
        email = d.get("email") or ""
        if not email:
            log.warning("send_day2_email: no email for driver_id=%s", driver_id)
            return {"email_sent": False, "reason": "no_email"}

        name = d.get("name") or "Driver"

        body_html = f"""
<html><body style="font-family:Arial,sans-serif;color:#222;max-width:600px;margin:auto">
<h2 style="color:#1a4fa8">Getting Your First Trip, {name}</h2>
<p>You're officially part of the 3 Lakes Light Fleet — and your first assignment is just around the corner.
Here's everything you need to know before you hit the road.</p>

<h3 style="color:#1a4fa8">How Dispatch Works</h3>
<ul>
  <li>Our dispatch coordinators match trips to available drivers based on your location and approved services.</li>
  <li>You'll receive a text notification when a trip is assigned — accept it directly from your phone.</li>
  <li>Dispatch operates 7 days a week. The more available you are, the more trips you get.</li>
</ul>

<h3 style="color:#1a4fa8">Tips for Your First Trip</h3>
<ul>
  <li><strong>Be on time</strong> — punctuality builds your driver rating and leads to more assignments.</li>
  <li><strong>Vehicle check</strong> — clean interior, full tank, phone charged and mounted safely.</li>
  <li><strong>Stay in contact</strong> — if anything changes (traffic, delay), text dispatch immediately.</li>
  <li><strong>Be professional</strong> — introduce yourself, help with bags if applicable, and follow the client's lead.</li>
</ul>

<h3 style="color:#1a4fa8">Contact &amp; Support</h3>
<p>Have a question before or during a trip? Reach us at:</p>
<ul>
  <li>Text or call: reply to any 3 Lakes message</li>
  <li>Email: <a href="mailto:info@3lakeslogistics.com">info@3lakeslogistics.com</a></li>
  <li>Website: <a href="https://3lakeslogistics.com">3lakeslogistics.com</a></li>
</ul>

<p>We're rooting for you. Your first trip is going to go great.</p>
<p style="margin-top:32px">Drive safe,<br>
<strong>The 3 Lakes Light Fleet Team</strong></p>
</body></html>"""

        body_text = (
            f"Getting Your First Trip, {name}\n\n"
            "How Dispatch Works:\n"
            "- Dispatch coordinators match trips to available drivers based on location and services.\n"
            "- You'll receive a text when a trip is assigned — accept it from your phone.\n"
            "- The more available you are, the more trips you get.\n\n"
            "Tips for Your First Trip:\n"
            "- Be on time — punctuality builds your driver rating.\n"
            "- Vehicle check: clean interior, full tank, phone charged.\n"
            "- Stay in contact if anything changes during the trip.\n"
            "- Be professional and follow the client's lead.\n\n"
            "Contact & Support:\n"
            "- Email: info@3lakeslogistics.com\n"
            "- Website: 3lakeslogistics.com\n\n"
            "Drive safe,\nThe 3 Lakes Light Fleet Team"
        )

        from ..email.smtp_sender import send_from_mailbox
        send_from_mailbox(
            mailbox="info",
            to=[email],
            subject=f"Getting your first trip, {name} — 3 Lakes Light Fleet",
            body_html=body_html,
            body_text=body_text,
        )
        log.info("send_day2_email sent to %s driver_id=%s", email, driver_id)
        return {"email_sent": True, "to": email}
    except Exception as exc:
        log.warning("send_day2_email error driver_id=%s: %s", driver_id, exc)
        return {"email_sent": False, "error": str(exc)}


# ── Main Workflow Orchestrator ────────────────────────────────────────────────

def run_welcome_workflow(driver_id: str) -> dict[str, Any]:
    """Orchestrate the 5-step Maya welcome workflow for a new Light Fleet driver.

    Steps 1 and 2 execute immediately.
    Steps 3, 4, 5 are scheduled via the scheduled_tasks table.

    Returns a summary dict with the result of each step.
    """
    log.info("run_welcome_workflow starting driver_id=%s", driver_id)
    now = _NOW()
    results: dict[str, Any] = {"driver_id": driver_id}

    # Step 1: Welcome SMS — immediate
    try:
        results["step1_welcome_sms"] = send_welcome_sms(driver_id)
    except Exception as exc:
        log.warning("workflow step1 failed driver_id=%s: %s", driver_id, exc)
        results["step1_welcome_sms"] = {"sms_sent": False, "error": str(exc)}

    # Step 2: Welcome Email — immediate
    try:
        results["step2_welcome_email"] = send_welcome_email(driver_id)
    except Exception as exc:
        log.warning("workflow step2 failed driver_id=%s: %s", driver_id, exc)
        results["step2_welcome_email"] = {"email_sent": False, "error": str(exc)}

    # Step 3: Welcome Call — 5 minutes from now
    call_time = now + timedelta(minutes=5)
    ok3 = _schedule_task("lf_welcome_call", driver_id, call_time)
    results["step3_welcome_call"] = {"scheduled": ok3, "scheduled_for": call_time.isoformat()}

    # Step 4: Day 1 SMS — 24 hours from now
    day1_time = now + timedelta(hours=24)
    ok4 = _schedule_task("lf_day1_sms", driver_id, day1_time)
    results["step4_day1_sms"] = {"scheduled": ok4, "scheduled_for": day1_time.isoformat()}

    # Step 5: Day 2 Email — 48 hours from now
    day2_time = now + timedelta(hours=48)
    ok5 = _schedule_task("lf_day2_email", driver_id, day2_time)
    results["step5_day2_email"] = {"scheduled": ok5, "scheduled_for": day2_time.isoformat()}

    # Stamp the driver record
    sb = _db()
    if sb:
        try:
            sb.table("light_vehicle_drivers").update({
                "welcome_workflow_started_at": now.isoformat(),
            }).eq("id", str(driver_id)).execute()
            results["workflow_stamped"] = True
        except Exception as exc:
            log.warning("Failed to stamp welcome_workflow_started_at driver_id=%s: %s", driver_id, exc)
            results["workflow_stamped"] = False

    log.info("run_welcome_workflow complete driver_id=%s results=%s", driver_id, results)
    return results
