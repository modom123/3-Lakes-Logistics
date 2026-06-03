"""Lead activity logger — single helper imported by all agents.

Writes to lead_activities table (permanent, per-lead touchpoint history).
Also auto-advances lead stage and fires intake-link outreach when a lead
becomes Interested.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any


_STAGE_PROGRESSION = {
    # channel+status → new status (only advances, never regresses)
    ("call",  "sent"):         "Contacted",
    ("call",  "answered"):     "Contacted",
    ("call",  "no_answer"):    "Contacted",
    ("call",  "voicemail"):    "Contacted",
    ("call",  "interested"):   "Interested",
    ("sms",   "sent"):         "Contacted",
    ("sms",   "delivered"):    "Contacted",
    ("email", "sent"):         "Contacted",
    ("email", "delivered"):    "Contacted",
}

_STAGE_RANK = {
    "new": 0, "New": 0,
    "Contacted": 1, "contacted": 1,
    "Interested": 2, "interested": 2,
    "Qualified": 3, "qualified": 3,
    "Converted": 4, "converted": 4,
    "Won": 4, "won": 4,
}


def _send_intake_link(lead: dict[str, Any]) -> None:
    """Fire SMS + email with the signup link to an interested lead (background thread)."""
    import re
    import httpx
    from ..settings import get_settings
    from ..studio.registry import SIGNUP_URL, BOOKING_URL
    from ..supabase_client import get_supabase

    s = get_settings()
    db = get_supabase()
    name = lead.get("business_name") or lead.get("company_name") or "there"
    lead_id = lead["id"]
    now = datetime.now(timezone.utc).isoformat()

    sms_msg = (
        f"Hi {name}! Ready to get started with 3 Lakes? "
        f"Sign up here (takes 5 min): {SIGNUP_URL} "
        f"Or book a quick call: {BOOKING_URL} — Reply STOP to opt out."
    )
    if len(sms_msg) > 160:
        sms_msg = sms_msg[:157] + "..."

    # SMS
    phone = (lead.get("phone") or "").strip()
    if phone and s.twilio_account_sid:
        digits = re.sub(r"\D", "", phone)
        if len(digits) == 10:
            digits = "1" + digits
        e164 = "+" + digits
        try:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json"
            r = httpx.post(url,
                auth=(s.twilio_account_sid, s.twilio_auth_token),
                data={"From": s.twilio_from_number, "To": e164, "Body": sms_msg},
                timeout=15)
            db.table("lead_activities").insert({
                "lead_id": lead_id, "created_at": now, "channel": "sms",
                "direction": "outbound",
                "status": "sent" if r.status_code < 300 else "error",
                "summary": f"Intake link sent: {SIGNUP_URL}",
                "agent": "auto_intake",
                "payload": {"to": e164, "type": "intake_link"},
            }).execute()
        except Exception:  # noqa: BLE001
            pass

    # Email
    email = (lead.get("email") or "").strip()
    if email and s.postmark_server_token:
        try:
            from ..studio.email_template import build_html
            html = build_html(state=lead.get("state") or "", lead_name=name)
            cta_block = (
                f'<div style="padding:20px;text-align:center">'
                f'<p style="color:#0b2545;font-size:15px">You expressed interest in joining 3 Lakes — '
                f'complete your application in 5 minutes:</p>'
                f'<a href="{SIGNUP_URL}" style="display:inline-block;background:#0b2545;color:#fff;'
                f'padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px">'
                f'Complete My Application →</a>'
                f'<p style="margin-top:12px;font-size:12px;color:#666">'
                f'Or book a call: <a href="{BOOKING_URL}">{BOOKING_URL}</a></p></div>'
            )
            html = html.replace("</body>", cta_block + "</body>")
            r2 = httpx.post("https://api.postmarkapp.com/email",
                headers={"Accept":"application/json","Content-Type":"application/json",
                         "X-Postmark-Server-Token": s.postmark_server_token},
                json={"From": s.postmark_from_email, "To": email,
                      "Subject": f"Complete your 3 Lakes application — {name}",
                      "HtmlBody": html, "MessageStream": "outbound"},
                timeout=15)
            db.table("lead_activities").insert({
                "lead_id": lead_id, "created_at": now, "channel": "email",
                "direction": "outbound",
                "status": "sent" if r2.status_code < 300 else "error",
                "summary": f"Intake link email sent to {email}",
                "agent": "auto_intake",
                "payload": {"to": email, "type": "intake_link"},
            }).execute()
        except Exception:  # noqa: BLE001
            pass


def log_activity(
    lead_id: str,
    channel: str,
    status: str,
    summary: str | None = None,
    agent: str | None = None,
    payload: dict[str, Any] | None = None,
    direction: str = "outbound",
) -> None:
    """Insert a lead_activity row, advance stage, and trigger intake link if Interested."""
    from ..supabase_client import get_supabase
    db = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    db.table("lead_activities").insert({
        "lead_id":    lead_id,
        "created_at": now,
        "channel":    channel,
        "direction":  direction,
        "status":     status,
        "summary":    summary,
        "agent":      agent,
        "payload":    payload or {},
    }).execute()

    new_status = _STAGE_PROGRESSION.get((channel, status))
    if new_status:
        lead_row = (db.table("leads").select("*").eq("id", lead_id).maybe_single().execute()).data
        current = (lead_row or {}).get("status", "New") or "New"
        if _STAGE_RANK.get(new_status, 0) > _STAGE_RANK.get(current, 0):
            db.table("leads").update({
                "status": new_status,
                "last_touch_at":   now,
                "last_contact_at": now,
            }).eq("id", lead_id).execute()

            # Interested → fire intake link in background (non-blocking)
            if new_status == "Interested" and lead_row:
                threading.Thread(
                    target=_send_intake_link,
                    args=(lead_row,),
                    daemon=True,
                ).start()
