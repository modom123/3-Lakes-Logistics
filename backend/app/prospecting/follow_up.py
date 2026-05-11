"""Post-Vance call follow-up orchestration.

After Vance qualifies an interested prospect, automatically:
1. Send welcome email with demo video
2. Schedule SMS reminder in 24h if no booking
3. Track conversion metrics
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings


DEMO_VIDEO_URL = "https://3lakeslogistics.com/demo.mp4"
CALENDLY_BOOKING_URL = "https://calendly.com/3lakes/commander-call"


def send_follow_up_email(
    lead_id: str,
    prospect_name: str,
    prospect_email: str,
    company_name: str,
    phone_number: str,
) -> dict[str, Any]:
    """Send follow-up email with demo video + booking link after interested prospect.

    Args:
        lead_id: Internal lead ID
        prospect_name: Prospect's name
        prospect_email: Email address
        company_name: Their company
        phone_number: Their phone number (for reference)

    Returns:
        {"status": "sent", "message_id": "..."} or {"status": "error", "error": "..."}
    """
    s = get_settings()
    if not s.postmark_server_token:
        return {"status": "error", "error": "postmark not configured"}

    subject = f"Your 3 Lakes Founders Program Demo — {prospect_name}"

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #1e40af; color: white; padding: 20px; border-radius: 8px 8px 0 0; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 8px 8px; }}
        .section {{ margin: 20px 0; }}
        .cta-button {{ display: inline-block; background: #1e40af; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: bold; margin: 10px 0; }}
        .video-container {{ margin: 20px 0; text-align: center; }}
        .benefits {{ background: white; padding: 15px; border-left: 4px solid #1e40af; margin: 15px 0; }}
        .benefit-item {{ margin: 8px 0; }}
        .footer {{ color: #666; font-size: 12px; margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Welcome to 3 Lakes Logistics! 🚚</h1>
            <p>Your path to automated dispatch & full load earnings</p>
        </div>

        <div class="content">
            <p>Hi {prospect_name},</p>

            <p>Thanks for taking my call! I'm pumped about the opportunity to get {company_name} enrolled in the Founders program.</p>

            <div class="video-container">
                <p><strong>Watch this 3-minute overview:</strong></p>
                <a href="{DEMO_VIDEO_URL}" class="cta-button">📹 Watch Demo Video</a>
            </div>

            <div class="section">
                <h3>Here's what you get:</h3>
                <div class="benefits">
                    <div class="benefit-item">✓ <strong>$300/month</strong> lifetime lock (Founders only)</div>
                    <div class="benefit-item">✓ <strong>100% of load earnings</strong> — no commission</div>
                    <div class="benefit-item">✓ <strong>Full automation</strong> — loads dispatched to your app</div>
                    <div class="benefit-item">✓ <strong>Dedicated support</strong> — human Commander always available</div>
                </div>
            </div>

            <div class="section">
                <p>Next step: Let's hop on a quick 15-minute call with our Commander to dive into YOUR specific situation and answer any questions.</p>

                <p style="text-align: center;">
                    <a href="{CALENDLY_BOOKING_URL}" class="cta-button">📅 Book Your Demo Call</a>
                </p>
            </div>

            <div class="section">
                <p><strong>If that link doesn't work:</strong> Reply to this email or call me back at {phone_number}.</p>
            </div>

            <p>Looking forward to helping {company_name} scale!</p>

            <p>Vance<br>
            3 Lakes Logistics<br>
            <em>Turning owner-operators into founders</em></p>

            <div class="footer">
                <p>This email was sent because you expressed interest in the Founders program during our call.</p>
                <p><a href="https://3lakeslogistics.com/unsubscribe">Unsubscribe</a></p>
            </div>
        </div>
    </div>
</body>
</html>
"""

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
                "HtmlBody": html_body,
                "Metadata": {
                    "lead_id": lead_id,
                    "type": "vance_follow_up",
                },
            },
            timeout=15,
        )
        r.raise_for_status()

        data = r.json()
        message_id = data.get("MessageID")

        log_agent(
            "vance",
            "follow_up_email_sent",
            payload={
                "lead_id": lead_id,
                "prospect": prospect_name,
                "company": company_name,
                "email": prospect_email,
            },
            result=message_id,
        )

        return {
            "status": "sent",
            "message_id": message_id,
            "follow_up_reminder_scheduled_at": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
        }

    except Exception as e:  # noqa: BLE001
        error_msg = str(e)
        log_agent(
            "vance",
            "follow_up_email_failed",
            payload={"lead_id": lead_id, "prospect": prospect_name},
            error=error_msg,
        )
        return {"status": "error", "error": error_msg}


def send_sms_reminder(
    lead_id: str,
    prospect_name: str,
    phone_number: str,
) -> dict[str, Any]:
    """Send SMS reminder to book demo call if they haven't booked in 24h.

    Args:
        lead_id: Internal lead ID
        prospect_name: Prospect's name
        phone_number: Phone number to text

    Returns:
        {"status": "sent", "message_sid": "..."} or {"status": "error", "error": "..."}
    """
    s = get_settings()
    if not s.twilio_account_sid or not s.twilio_auth_token:
        return {"status": "error", "error": "twilio not configured"}

    message_text = f"""Hi {prospect_name}! Quick reminder: Book your 15-min call with our Commander to lock in your Founders pricing ($300/mo lifetime). {CALENDLY_BOOKING_URL}"""

    try:
        # Twilio SMS API
        auth = (s.twilio_account_sid, s.twilio_auth_token)
        r = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json",
            auth=auth,
            data={
                "From": s.twilio_from_number,
                "To": phone_number,
                "Body": message_text,
            },
            timeout=15,
        )
        r.raise_for_status()

        data = r.json()
        message_sid = data.get("sid")

        log_agent(
            "vance",
            "sms_reminder_sent",
            payload={"lead_id": lead_id, "phone": phone_number},
            result=message_sid,
        )

        return {"status": "sent", "message_sid": message_sid}

    except Exception as e:  # noqa: BLE001
        error_msg = str(e)
        log_agent(
            "vance",
            "sms_reminder_failed",
            payload={"lead_id": lead_id, "phone": phone_number},
            error=error_msg,
        )
        return {"status": "error", "error": error_msg}


def schedule_follow_up_reminder(lead_id: str, prospect_name: str, phone_number: str) -> dict[str, Any]:
    """Schedule SMS reminder for 24h later if prospect doesn't book.

    This would typically be called by the execution engine to set up a delayed task.
    For now, returns a placeholder for the execution engine to handle scheduling.

    Args:
        lead_id: Internal lead ID
        prospect_name: Prospect's name
        phone_number: Phone number for reminder

    Returns:
        {"status": "scheduled", "remind_at": "..."}
    """
    remind_at = (datetime.utcnow() + timedelta(hours=24)).isoformat()

    log_agent(
        "vance",
        "sms_reminder_scheduled",
        payload={"lead_id": lead_id, "prospect": prospect_name},
        result=f"reminder scheduled for {remind_at}",
    )

    return {
        "status": "scheduled",
        "remind_at": remind_at,
        "note": "Execution engine should check if booking was made before sending SMS",
    }
