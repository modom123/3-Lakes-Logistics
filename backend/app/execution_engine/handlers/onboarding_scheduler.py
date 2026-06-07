"""Scheduled task executor — polls scheduled_tasks and fires due onboarding work.

Functions called by APScheduler jobs in triggers.py:
  execute_due_tasks()               — hourly, fires carrier_check_in + insurance tasks
  send_partial_submission_reminders() — daily 09:00, reminds incomplete applicants
  send_insurance_expiry_alerts()    — daily 06:45, alerts carriers expiring in 30/7 days
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from ...logging_service import get_logger
from ...settings import get_settings

log = get_logger("3ll.onboarding_scheduler")

_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


def _db():
    try:
        from ...supabase_client import get_supabase
        return get_supabase()
    except Exception:
        return None


def _send_sms(phone: str, body: str) -> bool:
    s = get_settings()
    if not (s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number):
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
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("SMS send failed to %s: %s", phone, exc)
        return False


def _send_email(to: str, subject: str, body_html: str) -> bool:
    s = get_settings()
    if not s.postmark_server_token:
        return False
    try:
        try:
            from postmarker.core import PostmarkClient  # type: ignore  # noqa: PLC0415
            PostmarkClient(server_token=s.postmark_server_token).emails.send(
                From=s.postmark_from_email,
                To=to,
                Subject=subject,
                HtmlBody=body_html,
            )
        except ImportError:
            import httpx  # noqa: PLC0415
            r = httpx.post(
                "https://api.postmarkapp.com/email",
                headers={
                    "X-Postmark-Server-Token": s.postmark_server_token,
                    "Content-Type": "application/json",
                },
                json={
                    "From": s.postmark_from_email,
                    "To": to,
                    "Subject": subject,
                    "HtmlBody": body_html,
                    "MessageStream": "outbound",
                },
                timeout=15,
            )
            r.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Email send failed to %s: %s", to, exc)
        return False


# ── Scheduled Task Executor ───────────────────────────────────────────────────

def execute_due_tasks() -> dict[str, Any]:
    """Poll scheduled_tasks for due pending tasks and execute them."""
    sb = _db()
    if not sb:
        return {"executed": 0, "failed": 0, "skipped": 0, "note": "no_db"}

    now_iso = _NOW()
    executed = failed = skipped = 0

    try:
        rows = (
            sb.table("scheduled_tasks")
            .select("*")
            .eq("status", "pending")
            .lte("scheduled_for", now_iso)
            .execute()
            .data or []
        )
    except Exception as exc:
        log.error("execute_due_tasks query failed: %s", exc)
        return {"executed": 0, "failed": 0, "skipped": 0, "error": str(exc)}

    for task in rows:
        task_id = task.get("id")
        task_type = task.get("task_type")
        carrier_id = task.get("carrier_id")

        try:
            if task_type == "carrier_check_in":
                from ...agents import vance  # noqa: PLC0415
                vance.run({"task": "check_in", "carrier_id": str(carrier_id) if carrier_id else None})
                executed += 1

            elif task_type == "insurance_expiry_alert":
                from ..executor import run_step  # noqa: PLC0415
                # Step 153 = insurance 30-day alert; try whichever is appropriate
                run_step(153, carrier_id, None, {"trigger": "scheduled_insurance_alert"})
                executed += 1

            elif task_type == "lf_welcome_call":
                from ...agents import maya_welcome  # noqa: PLC0415
                maya_welcome.send_welcome_call(str(carrier_id) if carrier_id else "")
                executed += 1

            elif task_type == "lf_day1_sms":
                from ...agents import maya_welcome  # noqa: PLC0415
                maya_welcome.send_day1_sms(str(carrier_id) if carrier_id else "")
                executed += 1

            elif task_type == "lf_day2_email":
                from ...agents import maya_welcome  # noqa: PLC0415
                maya_welcome.send_day2_email(str(carrier_id) if carrier_id else "")
                executed += 1

            elif task_type == "partial_reminder_sent":
                skipped += 1
                continue

            else:
                log.info("execute_due_tasks unknown task_type=%s id=%s", task_type, task_id)
                skipped += 1
                continue

            if task_id:
                sb.table("scheduled_tasks").update({
                    "status": "completed",
                    "executed_at": _NOW(),
                }).eq("id", str(task_id)).execute()

        except Exception as exc:
            log.error("execute_due_tasks task_id=%s type=%s error=%s", task_id, task_type, exc)
            failed += 1
            if task_id:
                try:
                    sb.table("scheduled_tasks").update({
                        "status": "failed",
                        "error": str(exc)[:500],
                        "executed_at": _NOW(),
                    }).eq("id", str(task_id)).execute()
                except Exception:
                    pass

    log.info("execute_due_tasks executed=%d failed=%d skipped=%d", executed, failed, skipped)
    return {"executed": executed, "failed": failed, "skipped": skipped}


# ── Partial Submission Reminders ──────────────────────────────────────────────

def send_partial_submission_reminders() -> dict[str, Any]:
    """Daily sweep — 24h SMS reminder and 72h email for incomplete applications."""
    sb = _db()
    if not sb:
        return {"reminders_sent": 0, "errors": 0, "note": "no_db"}

    now = datetime.now(timezone.utc)
    reminders_sent = errors = 0

    try:
        rows = (
            sb.table("active_carriers")
            .select("id,company_name,email,phone,created_at")
            .in_("status", ["incomplete", "pending"])
            .execute()
            .data or []
        )
    except Exception as exc:
        log.error("send_partial_submission_reminders query failed: %s", exc)
        return {"reminders_sent": 0, "errors": 1, "error": str(exc)}

    for carrier in rows:
        carrier_id = carrier.get("id")
        created_raw = carrier.get("created_at")
        if not created_raw:
            continue

        try:
            created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        except Exception:
            continue

        age_hours = (now - created_at).total_seconds() / 3600
        name = carrier.get("company_name") or "there"
        email = carrier.get("email")
        phone = carrier.get("phone")

        # Check if we already sent a reminder for this carrier recently
        already_sent = False
        try:
            existing = (
                sb.table("scheduled_tasks")
                .select("id")
                .eq("carrier_id", str(carrier_id))
                .eq("task_type", "partial_reminder_sent")
                .gte("created_at", (now - timedelta(hours=25)).isoformat())
                .execute()
                .data or []
            )
            already_sent = bool(existing)
        except Exception:
            pass

        if already_sent:
            continue

        sent = False

        if 24 <= age_hours < 48 and phone:
            msg = (
                f"Hi {name}, your 3 Lakes carrier application is almost done! "
                "Complete it here: https://3lakeslogistics.com/carrier-intake"
            )
            sent = _send_sms(phone, msg)

        elif 72 <= age_hours < 168 and email:
            html = (
                f"<p>Hi {name},</p>"
                "<p>You started a 3 Lakes Logistics carrier application but haven't finished yet. "
                "It only takes a few more minutes — and we're ready to put you to work.</p>"
                '<p><a href="https://3lakeslogistics.com/carrier-intake" '
                'style="background:#3b82f6;color:#fff;padding:12px 24px;border-radius:8px;'
                'text-decoration:none;font-weight:700;">Complete My Application →</a></p>'
                "<p>Questions? Reply to this email or call us anytime.</p>"
                "<p>— 3 Lakes Logistics Team</p>"
            )
            sent = _send_email(
                email,
                "Don't miss out — complete your 3 Lakes application",
                html,
            )

        if sent:
            reminders_sent += 1
            try:
                sb.table("scheduled_tasks").insert({
                    "task_type": "partial_reminder_sent",
                    "carrier_id": str(carrier_id),
                    "scheduled_for": _NOW(),
                    "status": "completed",
                    "executed_at": _NOW(),
                    "created_at": _NOW(),
                }).execute()
            except Exception:
                pass
        elif (24 <= age_hours < 168) and (phone or email):
            errors += 1

    log.info("send_partial_submission_reminders sent=%d errors=%d", reminders_sent, errors)
    return {"reminders_sent": reminders_sent, "errors": errors}


# ── Insurance Expiry Alerts ───────────────────────────────────────────────────

def send_insurance_expiry_alerts() -> dict[str, Any]:
    """Daily sweep — email carriers whose insurance expires in 30 or 7 days."""
    sb = _db()
    if not sb:
        return {"alerts_sent": 0, "note": "no_db"}

    now = datetime.now(timezone.utc).date()
    alerts_sent = 0

    # Fetch carriers with insurance expiring in next 31 days
    expiry_cutoff = (datetime.now(timezone.utc) + timedelta(days=31)).date().isoformat()

    try:
        rows = (
            sb.table("insurance_compliance")
            .select("carrier_id,policy_expiry,policy_number")
            .lte("policy_expiry", expiry_cutoff)
            .gte("policy_expiry", now.isoformat())
            .execute()
            .data or []
        )
    except Exception as exc:
        log.error("send_insurance_expiry_alerts query failed: %s", exc)
        return {"alerts_sent": 0, "error": str(exc)}

    for row in rows:
        carrier_id = row.get("carrier_id")
        expiry_str = row.get("policy_expiry")
        if not (carrier_id and expiry_str):
            continue

        try:
            expiry_date = datetime.fromisoformat(expiry_str).date() if "T" in expiry_str else \
                          datetime.strptime(expiry_str[:10], "%Y-%m-%d").date()
        except Exception:
            continue

        days_left = (expiry_date - now).days

        if days_left not in (30, 7, 1, 0):
            continue

        try:
            c = (
                sb.table("active_carriers")
                .select("company_name,email")
                .eq("id", str(carrier_id))
                .maybe_single()
                .execute()
                .data or {}
            )
        except Exception:
            c = {}

        email = c.get("email")
        name = c.get("company_name") or "Carrier"
        if not email:
            continue

        urgency = "URGENT: " if days_left <= 1 else ""
        subject = f"{urgency}Your 3 Lakes insurance expires in {days_left} day{'s' if days_left != 1 else ''}"
        html = (
            f"<p>Hi {name},</p>"
            f"<p>Your insurance policy on file expires on <strong>{expiry_date}</strong> "
            f"({days_left} day{'s' if days_left != 1 else ''} from now).</p>"
            "<p>Please upload your updated certificate of insurance to avoid service interruption.</p>"
            '<p><a href="https://3lakeslogistics.com/carrier-portal" '
            'style="background:#ef4444;color:#fff;padding:12px 24px;border-radius:8px;'
            'text-decoration:none;font-weight:700;">Update Insurance →</a></p>'
            "<p>— 3 Lakes Compliance Team</p>"
        )

        if _send_email(email, subject, html):
            alerts_sent += 1
            log.info("insurance_expiry_alert sent carrier=%s days_left=%d", carrier_id, days_left)

    log.info("send_insurance_expiry_alerts alerts_sent=%d", alerts_sent)
    return {"alerts_sent": alerts_sent}


# ── Stall Reminder Sweep ──────────────────────────────────────────────────────

def send_stall_reminders() -> dict[str, Any]:
    """Daily sweep — one reminder email when a carrier stops progressing mid-onboarding.

    Fires at 24h, 72h, and 7d of no phase advancement. Never sends more than
    one reminder per window per carrier.
    """
    from ...onboarding.phase_tracker import get_carrier_phase, send_stall_reminder

    sb = _db()
    if not sb:
        return {"sent": 0, "note": "no_db"}

    now = datetime.now(timezone.utc)
    sent = errors = 0
    WINDOWS = [
        (24,  72,   "24h"),
        (72,  168,  "72h"),
        (168, 999,  "7d"),
    ]

    try:
        rows = (
            sb.table("active_carriers")
            .select("id,company_name,status,created_at")
            .in_("status", ["incomplete", "pending", "onboarding"])
            .execute()
            .data or []
        )
    except Exception as exc:
        log.error("send_stall_reminders query failed: %s", exc)
        return {"sent": 0, "errors": 1}

    for carrier in rows:
        carrier_id = carrier.get("id")
        if not carrier_id:
            continue
        try:
            # Find how long since last phase advancement
            phase_data = get_carrier_phase(str(carrier_id))
            current_phase = phase_data.get("phase", 0)
            if current_phase >= 10:
                continue  # fully onboarded

            # Get last phase advancement timestamp
            last_advanced = None
            try:
                log_row = (
                    sb.table("onboarding_phase_log")
                    .select("advanced_at")
                    .eq("carrier_id", str(carrier_id))
                    .order("phase", desc=True)
                    .limit(1)
                    .maybe_single()
                    .execute()
                )
                if log_row.data:
                    last_advanced = datetime.fromisoformat(
                        log_row.data["advanced_at"].replace("Z", "+00:00")
                    )
            except Exception:
                pass

            if not last_advanced:
                # Fall back to created_at
                try:
                    last_advanced = datetime.fromisoformat(
                        carrier["created_at"].replace("Z", "+00:00")
                    )
                except Exception:
                    continue

            stalled_hours = (now - last_advanced).total_seconds() / 3600

            for min_h, max_h, window_key in WINDOWS:
                if not (min_h <= stalled_hours < max_h):
                    continue

                # Check dedup — only one reminder per window
                reminder_key = f"stall_reminder:{carrier_id}:{window_key}"
                already_sent = False
                try:
                    existing = (
                        sb.table("scheduled_tasks")
                        .select("id")
                        .eq("carrier_id", str(carrier_id))
                        .eq("task_type", reminder_key)
                        .limit(1)
                        .execute()
                    )
                    already_sent = bool(existing.data)
                except Exception:
                    pass

                if already_sent:
                    break

                ok = send_stall_reminder(str(carrier_id), int(stalled_hours / 24) or 1)
                if ok:
                    sent += 1
                    try:
                        sb.table("scheduled_tasks").insert({
                            "task_type": reminder_key,
                            "carrier_id": str(carrier_id),
                            "status": "completed",
                            "scheduled_for": now.isoformat(),
                            "executed_at": now.isoformat(),
                            "created_at": now.isoformat(),
                        }).execute()
                    except Exception:
                        pass
                else:
                    errors += 1
                break
        except Exception as exc:
            log.warning("stall reminder failed carrier=%s: %s", carrier_id, exc)
            errors += 1

    log.info("send_stall_reminders sent=%d errors=%d", sent, errors)
    return {"sent": sent, "errors": errors}
