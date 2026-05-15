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


def send_onboarding_guide_email(
    lead_id: str,
    prospect_name: str,
    prospect_email: str,
    company_name: str,
    phone_number: str,
) -> dict[str, Any]:
    """Send the full onboarding guide email 1 hour after a Nova call.

    This is the comprehensive version — explains all 5 steps, timelines, what documents
    are needed, pricing with economics example, and Calendly CTA to book Commander call.
    Sent to all prospects regardless of call outcome, as long as they have an email.
    """
    s = get_settings()
    if not s.postmark_server_token:
        return {"status": "error", "error": "postmark not configured"}

    subject = f"Your 3 Lakes Logistics Onboarding Roadmap — {prospect_name}"
    first_name = prospect_name.split()[0] if prospect_name else "there"

    html_body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;line-height:1.6;color:#333;background:#f5f5f5;margin:0;padding:20px}}
.container{{max-width:600px;margin:0 auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)}}
.header{{background:linear-gradient(135deg,#1e40af 0%,#1e3a8a 100%);color:white;padding:32px;text-align:center}}
.header h1{{margin:0;font-size:26px}}
.header p{{margin:10px 0 0;font-size:14px;opacity:.9}}
.body{{padding:32px}}
.step-row{{display:flex;gap:16px;margin:20px 0;align-items:flex-start}}
.step-num{{background:#1e40af;color:white;border-radius:50%;width:32px;height:32px;display:flex;align-items:center;justify-content:center;font-weight:bold;flex-shrink:0;font-size:14px}}
.step-done .step-num{{background:#10b981}}
.step-content h3{{margin:0 0 4px;font-size:16px;color:#1e40af}}
.step-done .step-content h3{{color:#10b981}}
.step-content p{{margin:0;font-size:14px;color:#555}}
table{{width:100%;border-collapse:collapse;margin:16px 0;font-size:14px}}
th{{background:#f3f4f6;padding:10px 12px;text-align:left;border-bottom:2px solid #1e40af;font-size:13px}}
td{{padding:10px 12px;border-bottom:1px solid #e5e7eb;vertical-align:top}}
.pricing{{background:#eff6ff;border:2px solid #1e40af;padding:20px;border-radius:8px;margin:24px 0}}
.pricing-num{{font-size:22px;font-weight:900;color:#10b981}}
.cta-wrap{{text-align:center;margin:28px 0}}
.cta{{display:inline-block;background:#1e40af;color:white;padding:14px 32px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:16px}}
.benefits{{list-style:none;padding:0;margin:12px 0}}
.benefits li{{padding:6px 0 6px 24px;position:relative;font-size:14px}}
.benefits li::before{{content:"✓";position:absolute;left:0;color:#10b981;font-weight:bold}}
.divider{{border:none;border-top:1px solid #e5e7eb;margin:24px 0}}
.footer{{background:#f9fafb;padding:20px 32px;font-size:12px;color:#888;text-align:center;border-top:1px solid #e5e7eb}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Welcome to the Founders Program</h1>
    <p>Your complete onboarding roadmap — here's everything that happens next</p>
  </div>
  <div class="body">
    <p>Hi {first_name},</p>
    <p>Nova here! Thanks for taking my call. As promised, here's your complete roadmap so you know exactly what to expect. The whole process takes about a week, but your active time is just 45 minutes.</p>

    <hr class="divider">
    <h3 style="margin:0 0 16px;color:#1e40af">Your 5-Step Onboarding</h3>

    <div class="step-row step-done">
      <div class="step-num">✓</div>
      <div class="step-content">
        <h3>Step 1: Founders Call — Done!</h3>
        <p>We talked through your operation, lanes, and goals. You're all set here.</p>
      </div>
    </div>

    <div class="step-row step-done">
      <div class="step-num">✓</div>
      <div class="step-content">
        <h3>Step 2: This Email — You're Reading It</h3>
        <p>Your roadmap so there are no surprises.</p>
      </div>
    </div>

    <div class="step-row">
      <div class="step-num">3</div>
      <div class="step-content">
        <h3>Step 3: Commander Call (15 minutes)</h3>
        <p>A brief call with our human Commander to dial in your profile — preferred lanes, equipment, target RPM, home time. This is where we customize everything to <strong>{company_name or "your operation"}</strong>.</p>
      </div>
    </div>

    <div class="step-row">
      <div class="step-num">4</div>
      <div class="step-content">
        <h3>Step 4: Sign Your Onboarding Packet (10 minutes)</h3>
        <p>One email from Adobe Sign. Two documents — fill out and sign both at once.</p>
        <table style="margin:12px 0">
          <tr><th>Document</th><th>What You Do</th><th>Time</th></tr>
          <tr><td><strong>Dispatch Agreement</strong></td><td>Review and e-sign your contract with us</td><td>~3 min</td></tr>
          <tr><td><strong>W9 Form</strong></td><td>Fill in your tax info and e-sign</td><td>~3 min</td></tr>
          <tr><td><strong>Insurance COI</strong></td><td>Upload your certificate (from your insurance company)</td><td>~2 min</td></tr>
        </table>
      </div>
    </div>

    <div class="step-row">
      <div class="step-num">5</div>
      <div class="step-content">
        <h3>Step 5: You're Live — Start Getting Loads</h3>
        <p>We verify everything and flip the switch. Loads start flowing to your app Day 1.</p>
      </div>
    </div>

    <hr class="divider">

    <div class="cta-wrap">
      <p style="margin-bottom:12px"><strong>👉 Your next step: Book your Commander call (takes 30 seconds)</strong></p>
      <a href="{CALENDLY_BOOKING_URL}" class="cta">📅 Book Your Commander Call</a>
      <p style="font-size:13px;color:#888;margin-top:10px">15 minutes. Slots fill up fast.</p>
    </div>

    <hr class="divider">

    <h3 style="color:#1e40af;margin-bottom:16px">What We Need From You</h3>
    <table>
      <tr><th>Item</th><th>Why</th></tr>
      <tr><td><strong>DOT Number</strong></td><td>Required by law. 30+ years old for Founders.</td></tr>
      <tr><td><strong>MC Authority Certificate</strong></td><td>Proof you can operate as a carrier.</td></tr>
      <tr><td><strong>Certificate of Insurance</strong></td><td>We verify minimum $1.2M cargo liability.</td></tr>
      <tr><td><strong>Banking Details</strong></td><td>Direct deposit — get paid daily.</td></tr>
    </table>

    <hr class="divider">

    <div class="pricing">
      <p style="margin:0 0 8px;font-size:13px;text-transform:uppercase;letter-spacing:.5px;color:#1e40af;font-weight:700">Founders Pricing</p>
      <div class="pricing-num">$300/month, forever</div>
      <p style="margin:8px 0 0;font-size:14px">That's your Founders lock — a flat fee that never increases.</p>
      <p style="font-size:14px;margin:8px 0 0"><strong>Example:</strong> A $2,000 load = $2,000 in your pocket. Standard broker takes 20% = only $1,600. You net an extra $400 per load, every time.</p>
    </div>

    <hr class="divider">

    <h3 style="color:#1e40af;margin-bottom:4px">What You Get on Day 1</h3>
    <ul class="benefits">
      <li>100% of load earnings — no commission, ever</li>
      <li>Real-time load dispatch to your phone</li>
      <li>Automated check-calls every 2–4 hours</li>
      <li>Rate confirmations sent electronically</li>
      <li>Weekly RPM reports and lane optimization</li>
      <li>Direct line to your Commander for any issue</li>
    </ul>

    <hr class="divider">

    <h3 style="color:#1e40af;margin-bottom:12px">Quick Questions</h3>
    <p><strong>Can I work with other brokers?</strong><br/>Yes. You own your authority. We just ask 3 Lakes be your primary source.</p>
    <p><strong>How do I get paid?</strong><br/>Direct deposit daily. Load closes → money in your account within 24 hours.</p>
    <p><strong>How many loads per week?</strong><br/>New Founders typically see 2–4 loads in their preferred lanes. Heavy utilization = 4–6+.</p>
    <p><strong>What if I need to take time off?</strong><br/>No problem. Your $300 rate is locked forever, even if you pause for a month.</p>

    <hr class="divider">

    <div class="cta-wrap">
      <a href="{CALENDLY_BOOKING_URL}" class="cta">📅 Book Your Commander Call Now</a>
    </div>

    <p>Questions? Just reply to this email. We're here.<br/>
    <strong>Nova &amp; the 3 Lakes Team</strong><br/>
    <em style="color:#888;font-size:13px">Automated dispatch for owner-operators</em></p>
  </div>
  <div class="footer">
    <p>3 Lakes Logistics — You received this because you spoke with Nova about the Founders program.</p>
    <p><a href="https://3lakeslogistics.com/unsubscribe" style="color:#888">Unsubscribe</a></p>
  </div>
</div>
</body>
</html>"""

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
                "Metadata": {"lead_id": lead_id, "type": "nova_onboarding_guide"},
            },
            timeout=15,
        )
        r.raise_for_status()
        message_id = r.json().get("MessageID")
        log_agent("nova", "onboarding_guide_sent",
                  payload={"lead_id": lead_id, "prospect": prospect_name, "email": prospect_email},
                  result=message_id)
        return {"status": "sent", "message_id": message_id}

    except Exception as e:  # noqa: BLE001
        log_agent("nova", "onboarding_guide_failed",
                  payload={"lead_id": lead_id, "prospect": prospect_name}, error=str(e))
        return {"status": "error", "error": str(e)}


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

            <p>Thanks for taking my call! I'm excited about the opportunity to get {company_name} enrolled in the Founders program.</p>

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

            <p>Nova<br>
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


def send_post_call_email(
    lead_id: str,
    prospect_name: str,
    prospect_email: str,
    company_name: str,
    phone_number: str,
) -> dict[str, Any]:
    """Send a brief process-intro email to every prospect 3 minutes after a call.

    This goes to ALL prospects regardless of interest level — it's a friendly
    follow-through on Nova's closing line: "We'll be following up with an email
    to get you familiar with our process."
    """
    s = get_settings()
    if not s.postmark_server_token:
        return {"status": "error", "error": "postmark not configured"}

    subject = f"Quick intro from Nova at 3 Lakes Logistics — {prospect_name}"

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #1e40af; color: white; padding: 20px; border-radius: 8px 8px 0 0; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 22px; }}
        .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 8px 8px; }}
        .section {{ margin: 20px 0; }}
        .cta-button {{ display: inline-block; background: #1e40af; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: bold; margin: 10px 0; }}
        .process-steps {{ background: white; border-radius: 8px; padding: 20px; margin: 16px 0; }}
        .step {{ display: flex; gap: 12px; margin: 12px 0; align-items: flex-start; }}
        .step-num {{ background: #1e40af; color: white; border-radius: 50%; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 12px; flex-shrink: 0; padding-top: 2px; }}
        .footer {{ color: #666; font-size: 12px; margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>3 Lakes Logistics — How We Work</h1>
            <p>A quick overview so you know exactly what to expect</p>
        </div>

        <div class="content">
            <p>Hi {prospect_name},</p>

            <p>This is Nova from 3 Lakes — just wanted to follow through on what I mentioned on our call.
            Here's a quick look at how our process works so you have all the info you need.</p>

            <div class="process-steps">
                <div class="step">
                    <div class="step-num">1</div>
                    <div><strong>Quick Qualification Call</strong> — That's what we just did! We make sure we're a good fit for each other before anything else.</div>
                </div>
                <div class="step">
                    <div class="step-num">2</div>
                    <div><strong>15-Min Commander Call</strong> — A brief call with our human Commander to review your lanes, equipment, and goals. No pressure, just a real conversation.</div>
                </div>
                <div class="step">
                    <div class="step-num">3</div>
                    <div><strong>Onboarding Packet</strong> — We send you a digital packet: carrier agreement, W9, insurance COI on file. Signed electronically in minutes.</div>
                </div>
                <div class="step">
                    <div class="step-num">4</div>
                    <div><strong>Founders Pricing Locked</strong> — $300/month, lifetime rate. Your loads, your earnings — 100% of what brokers pay goes to you.</div>
                </div>
                <div class="step">
                    <div class="step-num">5</div>
                    <div><strong>Full Automation Live</strong> — Loads dispatched directly to your app. Check-calls handled. Rate confirmations sent. You drive, we handle the rest.</div>
                </div>
            </div>

            <div class="section">
                <p>If you have any questions or want to move forward, just reply to this email or book a quick call:</p>
                <p style="text-align: center;">
                    <a href="{CALENDLY_BOOKING_URL}" class="cta-button">📅 Book Your Commander Call</a>
                </p>
            </div>

            <p>No obligation — just here if you want to learn more.</p>

            <p>Nova<br>
            3 Lakes Logistics<br>
            <em>Automated dispatch for owner-operators</em></p>

            <div class="footer">
                <p>You received this because we spoke today. Reply STOP to opt out of future messages.</p>
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
                    "type": "nova_post_call",
                },
            },
            timeout=15,
        )
        r.raise_for_status()

        data = r.json()
        message_id = data.get("MessageID")

        from ..logging_service import log_agent
        log_agent(
            "nova",
            "post_call_email_sent",
            payload={
                "lead_id": lead_id,
                "prospect": prospect_name,
                "company": company_name,
                "email": prospect_email,
            },
            result=message_id,
        )

        return {"status": "sent", "message_id": message_id}

    except Exception as e:  # noqa: BLE001
        error_msg = str(e)
        from ..logging_service import log_agent
        log_agent("nova", "post_call_email_failed",
                  payload={"lead_id": lead_id, "prospect": prospect_name}, error=error_msg)
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
