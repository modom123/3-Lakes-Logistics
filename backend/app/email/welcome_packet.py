"""Generate a driver welcome packet as a self-contained HTML string.

This module produces a professional, mobile-friendly HTML document that
can be served directly from a FastAPI endpoint or embedded in an email.
No external dependencies — all CSS is inlined.
"""
from __future__ import annotations

from datetime import date


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_welcome_packet_html(
    name: str,
    approved_services: list[str],
    vehicle_type: str = "vehicle",
    driver_id: str = "",
) -> str:
    """Return a complete HTML welcome packet for *name*.

    Args:
        name: Driver's full name.
        approved_services: List of service types the driver is approved for
            (e.g. ``["courier", "executive"]``).
        vehicle_type: Descriptive vehicle type string (cosmetic only).
        driver_id: Internal driver UUID — used for reference only.
    """
    today = date.today().strftime("%B %d, %Y")
    services_html = _render_services(approved_services)
    faq_html = _render_faq()

    # Section bodies are hoisted into locals (rather than nested f-strings inside
    # the main return f-string) so the module compiles on Python 3.11 as well as
    # 3.12+. Nested same-delimiter f-strings are a PEP 701 / 3.12 feature.
    welcome_body = f"""
              <p style="{_p_style()}">
                We are thrilled to have you join the <strong>3 Lakes Light Fleet</strong> — a growing network of
                professional drivers delivering excellence across medical transport, executive transfers, same-day
                courier, and gig logistics. You were carefully selected because we believe you have the reliability,
                professionalism, and hustle it takes to thrive with us.
              </p>
              <p style="{_p_style()}margin-bottom:0;">
                This packet contains everything you need to hit the ground running: your approved service types,
                how our platform works, how you get paid, and who to call when you need us. Read it once carefully —
                then keep it bookmarked. We&rsquo;re excited for what&rsquo;s ahead and we&rsquo;re here every step of the way.
              </p>
              <p style="margin:16px 0 0;color:#6b7280;font-size:13px;font-style:italic;">— The 3 Lakes Team</p>
            """

    paid_body = f"""
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
                {_info_card("💳", "Weekly Payouts", "Earnings are calculated each Sunday night and deposited every Monday morning via direct deposit. No waiting, no manual requests.")}
                {_info_card("🏦", "Direct Deposit", "Set up your bank account in the driver app under Settings → Payout Method. ACH transfers typically clear within 1 business day.")}
                {_info_card("📊", "How Earnings Work", "You earn a percentage of the trip rate displayed at acceptance. Rates vary by service type, distance, and time-of-day surge pricing.")}
                {_info_card("🎯", "Bonus Tiers", "Complete 20+ trips/month to unlock the Pro bonus tier. Consistently high ratings (4.8+) qualify you for premium dispatch priority.")}
              </div>
              <div style="margin-top:20px;padding:16px;background:#fffbeb;border-left:4px solid #f59e0b;border-radius:0 8px 8px 0;">
                <strong style="color:#92400e;font-size:13px;">Important:</strong>
                <span style="color:#78350f;font-size:13px;"> You are an independent contractor. 3 Lakes does not withhold taxes. Set aside approximately 25–30% of gross earnings for self-employment tax obligations.</span>
              </div>
            """

    vehicle_req = (
        f"Your {_esc(vehicle_type)} must be no more than 10 years old, pass a visual "
        "cleanliness check, and be fully insured at all times. Annual inspection required."
    )
    standards_body = f"""
              <p style="{_p_style()}">Maintaining high standards protects your ratings, your earnings, and the 3 Lakes brand. Every driver is expected to uphold the following:</p>
              <table width="100%" cellpadding="0" cellspacing="0">
                {_standard_row("👔", "Professional Appearance", "Clean, pressed clothing (business casual minimum). No strong fragrances. Presentable at all times when on duty.")}
                {_standard_row("🚗", "Vehicle Requirements", vehicle_req)}
                {_standard_row("⏱️", "On-Time Rate", "We expect a 90%+ on-time rate. Repeated late arrivals will trigger a performance review. Always communicate proactively if delayed.")}
                {_standard_row("⭐", "Rating Minimum", "Maintain a 4.6+ star average across all platforms. Ratings below 4.4 for two consecutive months may result in suspension from premium trips.")}
                {_standard_row("📵", "Device Policy", "No phone use while driving unless via hands-free. Violations reported by clients or platform GPS data are grounds for immediate deactivation.")}
                {_standard_row("🔒", "Confidentiality", "Passenger information, medical details (for NEMT), and client addresses are confidential. Never share or discuss trip details with third parties.")}
              </table>
            """

    downloads_body = f"""
              <p style="{_p_style()}">Depending on your approved services, you may receive trips through one or more partner platforms. Download and set up each app that matches your services.</p>
              <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
                {_platform_row("Curri", "courier", "Parcel & pallet delivery for businesses. Download the Curri Driver app on iOS or Android. Use invite code provided in your onboarding email.", "#6366f1")}
                {_platform_row("Roadie", "courier / gig", "Same-day package delivery for major retailers. Download Roadie Driver on iOS or Android and create your account with the email on file.", "#f97316")}
                {_platform_row("Modivcare", "nemt", "Non-emergency medical transport network. You will receive a separate activation email from Modivcare. Complete their driver orientation video before your first trip.", "#10b981")}
                {_platform_row("MTM (Medical Transport Mgmt)", "nemt", "Medical transport brokerage trips. Activation handled by your onboarding coordinator. Download the MTM Link driver app.", "#0ea5e9")}
                {_platform_row("Uber for Business / Lyft Business", "executive", "Executive corporate accounts. Your profile will be linked by the 3 Lakes ops team. Ensure your personal Uber/Lyft account is active and in good standing.", "#1a4fa8")}
                {_platform_row("3 Lakes Driver Portal", "all services", "Your primary dashboard for trip history, pay stubs, document uploads, and compliance status. Visit <a href='https://3lakeslogistics.com/driver' style='color:#1a4fa8'>3lakeslogistics.com/driver</a> or download the app.", "#f59e0b")}
              </table>
            """

    contacts_body = f"""
              <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
                {_contact_row("📦", "Dispatch &amp; Load Coordination", "loads@3lakeslogistics.com", "For trip assignments, schedule changes, and urgent dispatch issues")}
                {_contact_row("🛟", "Driver Support", "info@3lakeslogistics.com", "For onboarding questions, document uploads, payout issues, and general support")}
                {_contact_row("🌐", "Driver Portal &amp; Resources", "3lakeslogistics.com", "Access your trip history, pay stubs, compliance docs, and training materials")}
                {_contact_row("🚨", "Emergency / Safety", "911 first, then loads@3lakeslogistics.com", "In any safety emergency, contact 911 immediately. Notify dispatch as soon as safe to do so.")}
              </table>
            """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>3 Lakes Light Fleet — Driver Welcome Packet</title>
</head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1f2937;">

  <!-- ── Outer wrapper ── -->
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:32px 16px;">
    <tr><td align="center">
      <table width="100%" cellpadding="0" cellspacing="0" style="max-width:680px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.08);">

        <!-- ══ HEADER ══ -->
        <tr>
          <td style="background:linear-gradient(135deg,#1a4fa8 0%,#1e3a8a 100%);padding:40px 40px 32px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td>
                  <!-- Logo area -->
                  <div style="display:inline-block;background:rgba(255,255,255,.12);border-radius:12px;padding:10px 18px;margin-bottom:20px;">
                    <span style="color:#ffffff;font-size:20px;font-weight:900;letter-spacing:-0.5px;">3 LAKES</span>
                    <span style="color:#f59e0b;font-size:20px;font-weight:900;letter-spacing:-0.5px;"> LIGHT FLEET</span>
                  </div>
                  <div style="color:#bfdbfe;font-size:11px;font-weight:700;letter-spacing:3px;text-transform:uppercase;margin-bottom:8px;">Driver Welcome Packet</div>
                  <div style="color:#ffffff;font-size:28px;font-weight:800;line-height:1.2;margin-bottom:8px;">Welcome aboard, {_esc(name)}!</div>
                  <div style="color:#93c5fd;font-size:13px;">Issued: {today}{f" &nbsp;·&nbsp; Driver ID: {_esc(driver_id)}" if driver_id else ""}</div>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- ══ BODY ══ -->
        <tr>
          <td style="padding:0 40px 40px;">

            <!-- ── Welcome message ── -->
            {_section("Welcome to the Team", welcome_body)}

            <!-- ── Approved Services ── -->
            {_section("Your Approved Services", services_html)}

            <!-- ── How It Works ── -->
            {_section("How It Works", _render_how_it_works())}

            <!-- ── Getting Paid ── -->
            {_section("Getting Paid", paid_body)}

            <!-- ── Service Standards ── -->
            {_section("Service Standards", standards_body)}

            <!-- ── Platform Downloads ── -->
            {_section("Platform Downloads & Setup", downloads_body)}

            <!-- ── Key Contacts ── -->
            {_section("Key Contacts", contacts_body)}

            <!-- ── FAQ ── -->
            {_section("Frequently Asked Questions", faq_html)}

          </td>
        </tr>

        <!-- ── Footer ── -->
        <tr>
          <td style="background:#1a4fa8;padding:24px 40px;text-align:center;">
            <div style="color:#bfdbfe;font-size:12px;margin-bottom:4px;font-weight:700;letter-spacing:1px;">3 LAKES LIGHT FLEET</div>
            <div style="color:#93c5fd;font-size:11px;">
              <a href="mailto:info@3lakeslogistics.com" style="color:#93c5fd;text-decoration:none;">info@3lakeslogistics.com</a>
              &nbsp;&middot;&nbsp;
              <a href="https://3lakeslogistics.com" style="color:#93c5fd;text-decoration:none;">3lakeslogistics.com</a>
            </div>
            <div style="color:#6b7280;font-size:10px;margin-top:12px;">
              This document is confidential and intended solely for the named driver. &copy; {date.today().year} 3 Lakes Logistics LLC. All rights reserved.
            </div>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _esc(s: str) -> str:
    """Minimal HTML-escape for text insertion."""
    return (s
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _p_style() -> str:
    return "margin:0 0 14px;font-size:14px;line-height:1.7;color:#374151;"


def _section(title: str, content: str) -> str:
    return f"""
    <div style="margin-top:32px;">
      <div style="display:flex;align-items:center;margin-bottom:16px;">
        <div style="flex:1;height:1px;background:#e5e7eb;"></div>
        <div style="padding:0 16px;font-size:11px;font-weight:800;letter-spacing:2px;text-transform:uppercase;color:#1a4fa8;white-space:nowrap;">{title}</div>
        <div style="flex:1;height:1px;background:#e5e7eb;"></div>
      </div>
      {content}
    </div>"""


def _info_card(icon: str, title: str, text: str) -> str:
    return f"""<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:10px;padding:16px;">
      <div style="font-size:22px;margin-bottom:6px;">{icon}</div>
      <div style="font-size:13px;font-weight:700;color:#0369a1;margin-bottom:4px;">{title}</div>
      <div style="font-size:12px;color:#374151;line-height:1.5;">{text}</div>
    </div>"""


def _standard_row(icon: str, label: str, text: str) -> str:
    return f"""<tr>
      <td style="padding:10px 0;border-bottom:1px solid #f3f4f6;vertical-align:top;width:32px;font-size:18px;">{icon}</td>
      <td style="padding:10px 12px;border-bottom:1px solid #f3f4f6;vertical-align:top;width:160px;font-size:13px;font-weight:700;color:#111827;">{label}</td>
      <td style="padding:10px 0;border-bottom:1px solid #f3f4f6;vertical-align:top;font-size:13px;color:#374151;line-height:1.5;">{text}</td>
    </tr>"""


def _platform_row(platform: str, service: str, instructions: str, color: str) -> str:
    return f"""<tr>
      <td style="padding:12px 0;border-bottom:1px solid #f3f4f6;vertical-align:top;width:8px;">
        <div style="width:4px;height:40px;background:{color};border-radius:2px;"></div>
      </td>
      <td style="padding:12px 14px;border-bottom:1px solid #f3f4f6;vertical-align:top;">
        <div style="font-size:13px;font-weight:700;color:#111827;margin-bottom:2px;">{platform}</div>
        <div style="font-size:10px;font-weight:700;color:{color};letter-spacing:1px;text-transform:uppercase;margin-bottom:4px;">{service}</div>
        <div style="font-size:12px;color:#6b7280;line-height:1.5;">{instructions}</div>
      </td>
    </tr>"""


def _contact_row(icon: str, role: str, contact: str, note: str) -> str:
    return f"""<tr style="border-bottom:1px solid #f3f4f6;">
      <td style="padding:12px 0;vertical-align:top;width:32px;font-size:20px;">{icon}</td>
      <td style="padding:12px 12px;vertical-align:top;">
        <div style="font-size:13px;font-weight:700;color:#111827;">{role}</div>
        <div style="font-size:13px;color:#1a4fa8;font-weight:600;margin:2px 0;">{contact}</div>
        <div style="font-size:11px;color:#9ca3af;">{note}</div>
      </td>
    </tr>"""


def _render_services(services: list[str]) -> str:
    if not services:
        return "<p style='color:#9ca3af;font-size:13px;'>No services assigned yet — your onboarding coordinator will update this shortly.</p>"

    _SERVICE_META: dict[str, tuple[str, str, str]] = {
        "nemt":      ("🏥", "#10b981", "Non-Emergency Medical Transport — Medicaid rides & specimen delivery."),
        "executive": ("🎩", "#6366f1", "Executive Transfer — VIP, airport, and corporate trips."),
        "courier":   ("📦", "#f59e0b", "Same-Day Courier — Urban last-mile parcel and document delivery."),
        "gig":       ("⚡", "#0ea5e9", "Gig / On-Demand — Flexible dispatch across multiple platforms."),
        "medical":   ("🩺", "#14b8a6", "Medical Courier — Lab specimens, pharmacy, and clinical logistics."),
    }

    rows = []
    for svc in services:
        key = svc.lower()
        icon, color, desc = _SERVICE_META.get(key, ("🚗", "#1a4fa8", f"{svc.title()} service."))
        rows.append(f"""
        <div style="display:flex;align-items:flex-start;gap:14px;padding:14px;background:{color}0d;border:1px solid {color}33;border-radius:10px;margin-bottom:10px;">
          <div style="font-size:26px;flex-shrink:0;">{icon}</div>
          <div>
            <div style="font-size:14px;font-weight:800;color:{color};text-transform:capitalize;margin-bottom:2px;">{_esc(svc.title())}</div>
            <div style="font-size:13px;color:#374151;line-height:1.5;">{desc}</div>
          </div>
        </div>""")

    return "\n".join(rows)


def _render_how_it_works() -> str:
    steps = [
        ("1", "Get the Call", "Dispatch sends you a trip notification via the app or SMS. You have 60 seconds to accept before it routes to the next available driver."),
        ("2", "Accept the Trip", "Tap Accept in the app. You'll receive the pickup address, client name, and any special instructions. Navigate using your preferred map app."),
        ("3", "Complete It", "Arrive on time, execute the trip professionally, and mark it complete in the app. Upload any required documentation (signatures, photos) before closing the trip."),
        ("4", "Get Paid", "Completed trips are logged instantly. Earnings accumulate in your driver ledger and are paid out every Monday via direct deposit."),
    ]
    items = []
    for num, title, text in steps:
        items.append(f"""
        <div style="display:flex;align-items:flex-start;gap:16px;margin-bottom:20px;">
          <div style="width:36px;height:36px;border-radius:50%;background:#1a4fa8;color:#fff;font-size:15px;font-weight:900;display:flex;align-items:center;justify-content:center;flex-shrink:0;line-height:36px;text-align:center;">{num}</div>
          <div>
            <div style="font-size:14px;font-weight:700;color:#111827;margin-bottom:4px;">{title}</div>
            <div style="font-size:13px;color:#374151;line-height:1.6;">{text}</div>
          </div>
        </div>""")
    return "\n".join(items)


def _render_faq() -> str:
    faqs = [
        (
            "When do I start receiving trips?",
            "Trips begin as soon as your onboarding is complete — MVR cleared, documents verified, and at least one platform activated. Most drivers receive their first trip within 24–48 hours of activation.",
        ),
        (
            "What if I need to cancel a trip after accepting?",
            "Contact dispatch immediately at loads@3lakeslogistics.com. Cancellations within 10 minutes of pickup have no penalty for genuine emergencies. Repeated late cancellations affect your acceptance rate and dispatch priority.",
        ),
        (
            "How do I add or update my bank account for direct deposit?",
            "Log in to the 3 Lakes Driver Portal at 3lakeslogistics.com/driver, go to Settings → Payout Method, and follow the Stripe Connect flow. Changes take effect on the next weekly payout cycle.",
        ),
        (
            "What insurance do I need?",
            "You must maintain personal auto insurance at minimum state-required limits at all times. For NEMT or executive trips, commercial endorsement is strongly recommended and may be required by the client contract. Upload your current insurance card to your driver profile.",
        ),
        (
            "What happens if my vehicle fails a platform inspection?",
            "You will be temporarily suspended from that platform's trip queue until the issue is resolved. Contact driver support and upload proof of repair or inspection to be reinstated. This does not affect trips on other platforms.",
        ),
        (
            "Who do I contact if I have a safety concern on a trip?",
            "Your safety is the top priority. Call 911 first for any emergency. Then notify dispatch at loads@3lakeslogistics.com. Never continue a trip if you feel unsafe — your account will not be penalized for legitimate safety cancellations.",
        ),
    ]
    items = []
    for q, a in faqs:
        items.append(f"""
        <div style="border:1px solid #e5e7eb;border-radius:10px;padding:16px;margin-bottom:10px;">
          <div style="font-size:13px;font-weight:700;color:#1a4fa8;margin-bottom:6px;">Q: {_esc(q)}</div>
          <div style="font-size:13px;color:#374151;line-height:1.6;">A: {_esc(a)}</div>
        </div>""")
    return "\n".join(items)
