"""Post-call follow-up orchestration for interested Vance prospects.

Sequence after a qualified call:
  1. Immediate: branded email with Calendly + intake links
  2. Immediate: SMS with booking + intake links (if email missing, SMS is the primary)
  3. 24h later: SMS reminder if they haven't booked yet
     — driven by APScheduler hourly job checking leads.stage='Interested'
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from ..studio.registry import BOOKING_URL, SIGNUP_URL, WEBSITE_URL, BRAND_STATS


# ── Email template ─────────────────────────────────────────────────────────────

def _build_follow_up_html(prospect_name: str, company_name: str) -> str:
    first = prospect_name.split()[0] if prospect_name else "there"
    company_str = f" at {company_name}" if company_name else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Your 3 Lakes Onboarding Call</title></head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px;">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

  <!-- Header -->
  <tr><td style="background:#0B2545;border-radius:10px 10px 0 0;padding:32px;text-align:center;">
    <div style="font-size:28px;font-weight:900;color:#fff;letter-spacing:1px;">3 LAKES LOGISTICS</div>
    <div style="color:#4FB3F2;font-size:13px;margin-top:6px;letter-spacing:2px;text-transform:uppercase;">Automated American Trucking</div>
  </td></tr>

  <!-- Body -->
  <tr><td style="background:#fff;padding:36px 40px;">
    <p style="font-size:17px;color:#0B2545;margin:0 0 18px;">Hey {first},</p>
    <p style="font-size:15px;color:#374151;line-height:1.7;margin:0 0 18px;">
      Great talking with you{company_str}. As promised, here are your next steps to lock in
      <strong>Founders pricing</strong> before we hit our 1,000-truck cap.
    </p>

    <!-- Stats bar -->
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#061629;border-radius:8px;margin:20px 0;">
      <tr>
        <td align="center" style="padding:16px 8px;border-right:1px solid #1e3a5f;">
          <div style="font-size:22px;font-weight:800;color:#34D399;">{BRAND_STATS["rpm_above_market"]}</div>
          <div style="font-size:11px;color:#9CA3AF;margin-top:3px;">per mile above market</div>
        </td>
        <td align="center" style="padding:16px 8px;border-right:1px solid #1e3a5f;">
          <div style="font-size:22px;font-weight:800;color:#34D399;">{BRAND_STATS["monthly_recovery"]}</div>
          <div style="font-size:11px;color:#9CA3AF;margin-top:3px;">recovered per month</div>
        </td>
        <td align="center" style="padding:16px 8px;">
          <div style="font-size:22px;font-weight:800;color:#34D399;">{BRAND_STATS["flat_fee"]}</div>
          <div style="font-size:11px;color:#9CA3AF;margin-top:3px;">flat, lifetime locked</div>
        </td>
      </tr>
    </table>

    <p style="font-size:15px;color:#374151;line-height:1.7;margin:20px 0 4px;">
      <strong>Ready to lock in your spot?</strong> Takes 3 minutes — you're in as a Founder:
    </p>
    <table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:8px 0 20px;">
      <a href="{SIGNUP_URL}" style="display:inline-block;background:#34D399;color:#0B2545;font-weight:800;font-size:16px;padding:16px 40px;border-radius:7px;text-decoration:none;letter-spacing:0.3px;">
        Sign Up Now — Lock Founders Pricing &rarr;
      </a>
    </td></tr></table>

    <p style="font-size:14px;color:#6B7280;text-align:center;margin:-12px 0 20px;">
      — or —
    </p>

    <p style="font-size:14px;color:#374151;line-height:1.7;margin:0 0 8px;">
      Have questions first? Book a free 15-min call with our onboarding team:
    </p>
    <table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:8px 0 20px;">
      <a href="{BOOKING_URL}" style="display:inline-block;background:#0B2545;color:#fff;font-weight:700;font-size:14px;padding:12px 32px;border-radius:7px;text-decoration:none;">
        Book a 15-Min Onboarding Call &rarr;
      </a>
    </td></tr></table>

    <p style="font-size:13px;color:#6B7280;margin:24px 0 0;">
      Questions? Reply to this email or visit <a href="{WEBSITE_URL}" style="color:#4FB3F2;">{WEBSITE_URL}</a>.
    </p>
  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#f8fafc;border-radius:0 0 10px 10px;padding:20px 40px;text-align:center;border-top:1px solid #e5e7eb;">
    <p style="font-size:11px;color:#9CA3AF;margin:0;">
      3 Lakes Logistics &middot; info@3lakeslogistics.com<br>
      <a href="{WEBSITE_URL}/unsubscribe" style="color:#9CA3AF;">Unsubscribe</a>
    </p>
  </td></tr>

</table></td></tr></table>
</body></html>"""


# ── Delivery helpers ───────────────────────────────────────────────────────────

def send_follow_up_email(
    lead_id: str,
    prospect_name: str,
    prospect_email: str,
    company_name: str,
    **_kwargs: Any,
) -> dict[str, Any]:
    s = get_settings()
    if not s.postmark_server_token or not prospect_email:
        return {"status": "skipped", "reason": "postmark not configured or no email"}

    first = prospect_name.split()[0] if prospect_name else "there"
    subject = f"Your 3 Lakes onboarding link, {first} — lock in Founders pricing"

    try:
        r = httpx.post(
            "https://api.postmarkapp.com/email",
            headers={
                "X-Postmark-Server-Token": s.postmark_server_token,
                "Content-Type": "application/json",
            },
            json={
                "From": s.postmark_from_email,
                "To": prospect_email,
                "Subject": subject,
                "HtmlBody": _build_follow_up_html(prospect_name, company_name),
                "MessageStream": "outbound",
                "Metadata": {"lead_id": lead_id, "type": "vance_follow_up"},
            },
            timeout=15,
        )
        r.raise_for_status()
        msg_id = r.json().get("MessageID")
        log_agent("vance_follow_up", "email_sent",
                  payload={"lead_id": lead_id, "to": prospect_email}, result=msg_id)
        return {"status": "sent", "message_id": msg_id}
    except Exception as exc:  # noqa: BLE001
        log_agent("vance_follow_up", "email_failed", payload={"lead_id": lead_id}, error=str(exc))
        return {"status": "error", "error": str(exc)}


def send_follow_up_sms(
    lead_id: str,
    prospect_name: str,
    phone_number: str,
    reminder: bool = False,
) -> dict[str, Any]:
    """Send immediate post-call SMS (reminder=False) or 24h reminder (reminder=True)."""
    s = get_settings()
    if not s.twilio_account_sid or not s.twilio_auth_token or not s.twilio_from_number:
        return {"status": "skipped", "reason": "twilio not configured"}
    if not phone_number:
        return {"status": "skipped", "reason": "no phone number"}

    first = prospect_name.split()[0] if prospect_name else "there"
    if reminder:
        body = (
            f"Hey {first}, don't let Founders pricing slip — "
            f"sign up in 3 min: {SIGNUP_URL} "
            f"Or book a call: {BOOKING_URL} "
            f"Reply STOP to opt out."
        )
    else:
        body = (
            f"Hey {first}! Great chatting. Sign up now and lock Founders pricing ($300/mo for life): {SIGNUP_URL} "
            f"Or book a 15-min call: {BOOKING_URL} "
            f"Reply STOP to opt out."
        )

    try:
        r = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json",
            auth=(s.twilio_account_sid, s.twilio_auth_token),
            data={"From": s.twilio_from_number, "To": phone_number, "Body": body},
            timeout=15,
        )
        r.raise_for_status()
        sid = r.json().get("sid")
        action = "reminder_sent" if reminder else "sms_sent"
        log_agent("vance_follow_up", action,
                  payload={"lead_id": lead_id, "phone": phone_number}, result=sid)
        return {"status": "sent", "sid": sid}
    except Exception as exc:  # noqa: BLE001
        log_agent("vance_follow_up", "sms_failed", payload={"lead_id": lead_id}, error=str(exc))
        return {"status": "error", "error": str(exc)}


def schedule_follow_up_reminder(
    lead_id: str,
    prospect_name: str,
    phone_number: str,
) -> dict[str, Any]:
    """Mark lead stage=Interested + next_touch_at=24h so the hourly job fires the reminder."""
    remind_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    try:
        db = get_supabase()
        db.table("leads").update({
            "stage": "Interested",
            "next_touch_at": remind_at,
        }).eq("id", lead_id).execute()
        log_agent("vance_follow_up", "reminder_scheduled",
                  payload={"lead_id": lead_id}, result=f"due={remind_at}")
        return {"status": "scheduled", "remind_at": remind_at}
    except Exception as exc:  # noqa: BLE001
        log_agent("vance_follow_up", "reminder_schedule_failed",
                  payload={"lead_id": lead_id}, error=str(exc))
        return {"status": "error", "error": str(exc)}


def send_due_reminders() -> dict[str, Any]:
    """Called hourly by APScheduler. Sends 24h SMS to Interested leads whose time has come."""
    db = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    rows = (
        db.table("leads")
        .select("id,contact_name,phone")
        .eq("stage", "Interested")
        .not_.is_("phone", "null")
        .not_.is_("next_touch_at", "null")
        .lte("next_touch_at", now)
        .neq("do_not_contact", True)
        .limit(50)
        .execute()
    ).data or []

    sent = 0
    for row in rows:
        send_follow_up_sms(
            lead_id=str(row["id"]),
            prospect_name=row.get("contact_name") or "there",
            phone_number=row.get("phone") or "",
            reminder=True,
        )
        # Advance stage so reminder doesn't fire again
        db.table("leads").update({
            "stage": "Follow-Up Sent",
            "next_touch_at": None,
        }).eq("id", row["id"]).execute()
        sent += 1

    log_agent("vance_follow_up", "reminders_batch",
              result=f"sent={sent} eligible={len(rows)}")
    return {"sent": sent, "eligible": len(rows)}
