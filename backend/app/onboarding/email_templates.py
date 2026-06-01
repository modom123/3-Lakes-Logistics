"""Onboarding email templates — stall reminder only.

Emails are NOT sent on every step. A single reminder fires when a carrier
has stopped progressing (after 24h, 72h, or 7 days of inactivity).
"""
from __future__ import annotations


def _progress_bar(phase: int) -> str:
    cells = ""
    for i in range(1, 11):
        bg = "#34D399" if i <= phase else "#e2e8f0"
        cells += (
            f'<td style="width:10%;padding:0 1px;">'
            f'<div style="height:8px;background:{bg};border-radius:2px;"></div>'
            f'</td>'
        )
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
        f'style="margin:0 0 6px;">'
        f'<tr>{cells}</tr>'
        f'</table>'
        f'<p style="margin:0;color:#6b7280;font-size:11px;">Step {phase} of 10 complete</p>'
    )


def build_stall_reminder_email(
    carrier_name: str,
    current_phase: int,
    phase_name: str,
    next_action: str,
    stalled_days: int,
) -> dict:
    """Build a stall reminder email for a carrier who stopped mid-onboarding."""

    if stalled_days <= 1:
        subject = f"Don't forget — you're almost set up with 3 Lakes Logistics"
        urgency = "You started your onboarding yesterday and are almost there."
    elif stalled_days <= 3:
        subject = f"Your 3 Lakes account is waiting — finish in minutes"
        urgency = f"You started {stalled_days} days ago and are {current_phase} of 10 steps complete."
    else:
        subject = f"Still interested in hauling with 3 Lakes? Your application is saved."
        urgency = f"Your application has been saved for {stalled_days} days. Pick up right where you left off."

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f8;padding:24px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

  <tr>
    <td style="background:#0B2545;padding:20px 32px;border-radius:8px 8px 0 0;">
      <span style="display:inline-block;width:32px;height:32px;background:#4FB3F2;border-radius:6px;
                   text-align:center;line-height:32px;font-weight:700;color:#0B2545;font-size:14px;">3L</span>
      <span style="color:#F5F8FB;font-size:15px;font-weight:600;vertical-align:middle;margin-left:10px;">3 Lakes Logistics</span>
    </td>
  </tr>

  <tr>
    <td style="background:#ffffff;padding:32px;">
      <p style="margin:0 0 8px;color:#6b7280;font-size:13px;">Hi {carrier_name},</p>
      <h1 style="margin:0 0 16px;color:#0B2545;font-size:24px;font-weight:700;line-height:1.2;">
        Your application is saved — finish it now
      </h1>
      <p style="margin:0 0 24px;color:#374151;font-size:14px;line-height:1.6;">
        {urgency}
      </p>

      <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin-bottom:24px;">
        <p style="margin:0 0 12px;color:#0B2545;font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;">
          Your Progress
        </p>
        {_progress_bar(current_phase)}
        <p style="margin:12px 0 4px;color:#374151;font-size:14px;font-weight:600;">
          Current step: {phase_name}
        </p>
        <p style="margin:0;color:#6b7280;font-size:13px;">
          Next: {next_action}
        </p>
      </div>

      <table cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
        <tr>
          <td style="background:#34D399;border-radius:6px;padding:12px 28px;">
            <a href="https://3lakeslogistics.com/carrier-intake"
               style="color:#0B2545;font-size:15px;font-weight:700;text-decoration:none;">
              Continue My Application →
            </a>
          </td>
        </tr>
      </table>

      <p style="margin:0;color:#6b7280;font-size:13px;line-height:1.6;">
        Questions? Reply to this email or contact us at
        <a href="mailto:info@3lakeslogistics.com" style="color:#0B2545;">info@3lakeslogistics.com</a>.
        We're here to help you get on the road.
      </p>
    </td>
  </tr>

  <tr>
    <td style="background:#0B2545;padding:16px 32px;border-radius:0 0 8px 8px;text-align:center;">
      <p style="margin:0;color:#94a3b8;font-size:11px;">
        3 Lakes Logistics · Chicago, IL ·
        <a href="mailto:info@3lakeslogistics.com" style="color:#94a3b8;">info@3lakeslogistics.com</a>
      </p>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    text = (
        f"Hi {carrier_name},\n\n"
        f"{urgency}\n\n"
        f"You're on Step {current_phase} of 10: {phase_name}\n"
        f"Next: {next_action}\n\n"
        f"Continue your application: https://3lakeslogistics.com/carrier-intake\n\n"
        f"Questions? Email info@3lakeslogistics.com\n\n"
        f"— 3 Lakes Logistics"
    )

    return {"subject": subject, "html": html, "text": text}


def get_phase_email(phase: int, carrier_name: str) -> dict:
    """Compatibility shim — returns a stall reminder for the given phase."""
    from .phase_tracker import PHASE_INFO
    info = PHASE_INFO.get(phase, {})
    return build_stall_reminder_email(
        carrier_name=carrier_name,
        current_phase=phase,
        phase_name=info.get("name", f"Step {phase}"),
        next_action=info.get("what_carrier_needs_to_do", "continue your application"),
        stalled_days=2,
    )
