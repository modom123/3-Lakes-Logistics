"""LF BizDev Agent — automated email sequences + Bland AI outbound calls.

Three sales reps, three sectors:
  Marcus Webb   → Healthcare  (hospitals, dialysis, senior living, NEMT)
  Jordan Vale   → Enterprise  (corporate, hotels, law firms)
  Priya Santos  → Platform    (gig apps, rideshare, delivery platforms)

Daily run logic:
  run_email_sequence() — sends next drip-step to eligible prospects (5-touch)
  run_call_sequence()  — fires Bland AI calls to warm prospects (step 1+)
  run()                — runs both, returns combined results
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from ..studio.registry import BOOKING_URL

POSTMARK_API = "https://api.postmarkapp.com/email"
BLAND_API_URL = "https://api.bland.ai/v1"

# Rep display names keyed by DB slug
REP_NAMES = {
    "marcus_webb":   "Marcus Webb",
    "jordan_vale":   "Jordan Vale",
    "priya_santos":  "Priya Santos",
}

# Step-delay thresholds in days (measured from first email / created_at)
STEP_DELAYS = {0: 0, 1: 3, 2: 7, 3: 14, 4: 21}

# ---------------------------------------------------------------------------
# Email copy — (subject, body_text) per sector per step
# ---------------------------------------------------------------------------

def _build_email(sector: str, step: int, company: str, contact: str, rep: str) -> tuple[str, str]:
    """Return (subject, plain-text body) for the given sector/step."""
    rep_name = REP_NAMES.get(rep, rep or "The 3 Lakes Team")
    contact_first = (contact or "there").split()[0]

    sequences: dict[str, list[tuple[str, str]]] = {
        "healthcare": [
            (
                f"Reliable NEMT Partnership for {company}",
                f"""Hi {contact_first},

I'm {rep_name} from 3 Lakes Logistics. I wanted to reach out about our Non-Emergency Medical Transport services — we work with hospitals, dialysis centers, senior living communities, and NEMT coordinators across the region.

Here's what makes us different:
• ADA-compliant vehicles and HIPAA-aware dispatch
• Same-day scheduling for recurring medical trips
• No monthly fees — just 15% per completed trip
• Real-time tracking so you always know where your passengers are

We'd love to set up a quick 15-minute call to see if there's a fit. Would this week work for you?

Book a time here: {BOOKING_URL}

Best,
{rep_name}
3 Lakes Light Fleet
661-466-9932""",
            ),
            (
                f"Following up — NEMT transport for {company}",
                f"""Hi {contact_first},

I sent a note a few days ago about our NEMT services for {company} — just wanted to make sure it didn't get buried.

A few quick highlights:
• No monthly retainer or setup fees
• Same-day scheduling available for recurring medical trips
• Real-time GPS tracking on every ride
• Fully insured, background-checked drivers

If you're managing patient transport right now, we can take that off your plate. Happy to do a 15-minute call at your convenience.

{BOOKING_URL}

Best,
{rep_name}
3 Lakes Light Fleet | 661-466-9932""",
            ),
            (
                f"How [similar org] cut transport costs with 3 Lakes",
                f"""Hi {contact_first},

Quick follow-up from 3 Lakes Logistics.

We're currently running a >97% on-time rate across our NEMT fleet, and a number of our healthcare partners have moved to recurring contract arrangements that save them 20–30% compared to ad-hoc transport vendors.

For {company}, a recurring contract would mean:
• Priority scheduling for your regular patient runs
• Dedicated dispatch contact for last-minute changes
• Monthly reporting so you have full visibility

If you'd like to see how this might work for your organization, I'd love 15 minutes.

{BOOKING_URL}

Best,
{rep_name}
3 Lakes Light Fleet | 661-466-9932""",
            ),
            (
                f"Quick question — {company} transport needs",
                f"""Hi {contact_first},

I've reached out a couple of times about our NEMT services — I promise this one is short.

I'd just love to understand your current transport situation at {company} — even if the timing isn't right, it helps us understand where we can add the most value.

Would you have 10 minutes this week or next?

{BOOKING_URL}

Thanks for your time,
{rep_name}
3 Lakes Light Fleet | 661-466-9932""",
            ),
            (
                f"Last note from 3 Lakes",
                f"""Hi {contact_first},

I don't want to keep cluttering your inbox, so this will be my last note for now. If the timing isn't right, I'll plan to follow up next quarter.

Here's a quick summary of what we offer:
• Non-Emergency Medical Transport — HIPAA-aware, ADA vehicles
• No monthly fees — 15% per completed trip
• Same-day scheduling, real-time tracking
• Recurring contract options available

If you ever need reliable patient transport, we're here: 661-466-9932
Or book a call anytime: {BOOKING_URL}

Best of luck,
{rep_name}
3 Lakes Light Fleet""",
            ),
        ],
        "enterprise": [
            (
                f"Corporate courier & executive transport — {company}",
                f"""Hi {contact_first},

I'm {rep_name} from 3 Lakes Logistics. We provide same-day courier services and executive transport for businesses in your area — flat 15% fee, no monthly contracts, no setup costs.

What we offer:
• Same-day document and package delivery with real-time tracking
• Executive car service for clients, executives, and VIP guests
• Dedicated dispatch — one point of contact for all your logistics
• Scale up or down as your needs change — no commitments

I'd love to show you how we're supporting companies like yours. Would you have 15 minutes this week?

{BOOKING_URL}

Best,
{rep_name}
3 Lakes Light Fleet | 661-466-9932""",
            ),
            (
                f"Re: Courier services for {company}",
                f"""Hi {contact_first},

Following up on my previous note about our courier and executive transport services for {company}.

A few things that set us apart:
• Consistent on-time delivery — tracked and reported
• No retainer or monthly minimums
• Real-time tracking on every order so you and your clients always know the ETA
• Scalable — one vehicle or twenty, we adjust with you

Happy to jump on a quick call to see if we're a fit.

{BOOKING_URL}

Best,
{rep_name}
3 Lakes Light Fleet | 661-466-9932""",
            ),
            (
                f"How companies like {company} use 3 Lakes",
                f"""Hi {contact_first},

A quick follow-up from 3 Lakes Logistics.

Here's how some of our enterprise clients are using us right now:
• Law firms: time-sensitive document delivery + client/witness transport
• Hotels: airport pickups, VIP guest shuttles, package delivery
• Corporations: executive transport, inter-office courier, event logistics

Our package delivery SLA is same-day in most metro corridors, and our executive transport is available 6am–10pm seven days a week.

If any of this sounds useful for {company}, I'd love 15 minutes.

{BOOKING_URL}

Best,
{rep_name}
3 Lakes Light Fleet | 661-466-9932""",
            ),
            (
                f"15 minutes — {company} logistics",
                f"""Hi {contact_first},

Reaching out one more time about courier and executive transport for {company}.

Would you have 15 minutes this week for a quick call? I'd love to learn about your current logistics setup and show you exactly what we can do.

{BOOKING_URL}

Best,
{rep_name}
3 Lakes Light Fleet | 661-466-9932""",
            ),
            (
                f"Closing the loop — 3 Lakes",
                f"""Hi {contact_first},

Last note from me — I don't want to keep filling up your inbox.

If the timing ever is right for a courier or executive transport partner, here's a quick recap:
• Same-day delivery and executive car service
• Flat 15% fee — no contracts, no monthly minimums
• Real-time tracking, dedicated dispatch
• Ready to scale with your business

Reach us anytime: 661-466-9932 | {BOOKING_URL}

Best of luck,
{rep_name}
3 Lakes Light Fleet""",
            ),
        ],
        "platform": [
            (
                f"Driver supply partnership — 3 Lakes Light Fleet",
                f"""Hi {contact_first},

I'm {rep_name} from 3 Lakes Logistics. We operate a network of pre-vetted, fully insured Light Fleet drivers and we're actively looking for platform partnerships to expand our driver supply agreements.

What we bring to the table:
• Pre-screened, insured drivers — background checks, MVR verified
• Bulk driver supply available on short timelines
• White-label dispatch integration available
• Volume pricing for ongoing partnerships

If you're looking to expand your driver network in our coverage area, I'd love to connect.

{BOOKING_URL}

Best,
{rep_name}
3 Lakes Light Fleet | 661-466-9932""",
            ),
            (
                f"Re: Driver network expansion",
                f"""Hi {contact_first},

Following up on my note about driver supply for your platform.

A few specifics that might be relevant:
• Our driver network spans multiple metro corridors and is growing
• New driver activation typically within 48–72 hours of partnership agreement
• We handle compliance, insurance, and background checks on our end
• Flexible volume commitments — we'll work with your growth stage

Happy to share more details on a quick call.

{BOOKING_URL}

Best,
{rep_name}
3 Lakes Light Fleet | 661-466-9932""",
            ),
            (
                f"Volume pricing for {company} driver supply",
                f"""Hi {contact_first},

Another note from 3 Lakes — wanted to share a bit more on how our driver supply agreements work.

We offer tiered pricing based on volume:
• Starter tier: flexible, no minimums
• Growth tier: volume discounts once you're dispatching regularly
• Enterprise tier: dedicated driver pool, SLA guarantees, white-label dispatch

For platforms like {company}, we can structure an agreement around your dispatch cadence and coverage needs.

Worth a 15-minute conversation?

{BOOKING_URL}

Best,
{rep_name}
3 Lakes Light Fleet | 661-466-9932""",
            ),
            (
                f"Partnership call — {company}",
                f"""Hi {contact_first},

One more reach-out about a potential driver supply partnership between {company} and 3 Lakes Logistics.

Would you be open to a 15-minute call this week to explore fit? No pitch — just a conversation about your driver supply needs and whether we can help.

{BOOKING_URL}

Best,
{rep_name}
3 Lakes Light Fleet | 661-466-9932""",
            ),
            (
                f"Final follow-up — 3 Lakes driver supply",
                f"""Hi {contact_first},

Last note from me on this — I don't want to overstay my welcome.

If {company} ever needs pre-vetted, insured drivers to supplement your network, 3 Lakes is here:
• Bulk driver supply, volume pricing
• White-label dispatch integration available
• Fast activation, compliance handled on our end

Call or text: 661-466-9932 | {BOOKING_URL}

Best of luck,
{rep_name}
3 Lakes Light Fleet""",
            ),
        ],
    }

    steps = sequences.get(sector, sequences["enterprise"])
    idx = min(step, len(steps) - 1)
    return steps[idx]


# ---------------------------------------------------------------------------
# Email sending (Postmark)
# ---------------------------------------------------------------------------

def _send_postmark_email(to: str, subject: str, body: str) -> dict[str, Any]:
    s = get_settings()
    if not s.postmark_server_token:
        return {"status": "error", "error": "POSTMARK_SERVER_TOKEN not configured"}
    try:
        r = httpx.post(
            POSTMARK_API,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Postmark-Server-Token": s.postmark_server_token,
            },
            json={
                "From": s.postmark_from_email,
                "To": to,
                "Subject": subject,
                "TextBody": body,
                "MessageStream": "outbound",
            },
            timeout=15,
        )
        r.raise_for_status()
        return {"status": "sent"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Email sequence runner
# ---------------------------------------------------------------------------

def run_email_sequence(daily_limit: int = 30) -> dict[str, Any]:
    """Send next drip-step email to eligible prospects."""
    db = get_supabase()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    rows = (
        db.table("lf_bd_prospects")
        .select("id,company,contact,email,sector,rep,status,sequence_step,email_count,last_email_at,do_not_contact,created_at")
        .not_.in_("status", ["active", "lost"])
        .neq("do_not_contact", True)
        .limit(200)
        .execute()
    ).data or []

    sent = 0
    skipped = 0

    for prospect in rows:
        if sent >= daily_limit:
            break

        email = (prospect.get("email") or "").strip()
        if not email:
            skipped += 1
            continue

        step = prospect.get("sequence_step") or 0
        email_count = prospect.get("email_count") or 0
        last_email_at = prospect.get("last_email_at")
        created_at = prospect.get("created_at") or now_iso

        # Determine if this prospect is due for next step
        if step == 0 and email_count == 0:
            # Never emailed — eligible immediately
            next_step = 0
        elif step >= 4:
            skipped += 1
            continue
        else:
            # Check how many days since first email (from created_at as baseline)
            baseline_str = prospect.get("last_email_at") or created_at
            try:
                baseline = datetime.fromisoformat(baseline_str.replace("Z", "+00:00"))
            except Exception:
                baseline = now
            days_since = (now - baseline).days
            required_delay = STEP_DELAYS.get(step + 1, 999)
            if days_since < required_delay:
                skipped += 1
                continue
            next_step = step + 1

        if next_step > 4:
            skipped += 1
            continue

        company = prospect.get("company") or "your organization"
        contact = prospect.get("contact") or ""
        sector = prospect.get("sector") or "enterprise"
        rep = prospect.get("rep") or "marcus_webb"
        prospect_id = str(prospect["id"])

        subject, body = _build_email(sector, next_step, company, contact, rep)

        result = _send_postmark_email(email, subject, body)

        # Log to outreach log
        try:
            db.table("lf_bd_outreach_log").insert({
                "prospect_id": prospect_id,
                "channel": "email",
                "step": next_step,
                "subject": subject,
                "body": body[:2000],
                "status": result.get("status", "sent"),
            }).execute()
        except Exception as log_exc:  # noqa: BLE001
            log_agent("lf_bizdev", "log_insert_failed", payload={"prospect_id": prospect_id}, error=str(log_exc))

        if result.get("status") == "sent":
            current_status = prospect.get("status") or "prospect"
            new_status = "prospecting" if current_status == "prospect" else current_status
            db.table("lf_bd_prospects").update({
                "sequence_step": next_step,
                "email_count": email_count + 1,
                "last_email_at": now_iso,
                "last_contact_at": now_iso,
                "status": new_status,
                "updated_at": now_iso,
            }).eq("id", prospect_id).execute()
            sent += 1
            log_agent("lf_bizdev", "email_sent", payload={"prospect_id": prospect_id, "step": next_step, "company": company})
        else:
            log_agent("lf_bizdev", "email_failed", payload={"prospect_id": prospect_id}, error=result.get("error"))
            skipped += 1

        time.sleep(0.05)

    return {"sent": sent, "skipped": skipped, "eligible": len(rows)}


# ---------------------------------------------------------------------------
# Bland AI call helper
# ---------------------------------------------------------------------------

def _fire_bland_call(prospect: dict) -> dict[str, Any]:
    s = get_settings()
    if not s.bland_ai_api_key:
        return {"status": "error", "error": "BLAND_AI_API_KEY not configured"}

    phone = (prospect.get("phone") or "").strip()
    if not phone:
        return {"status": "error", "error": "no phone"}

    contact_first = (prospect.get("contact") or "there").split()[0]
    company = prospect.get("company") or "your organization"
    rep = prospect.get("rep") or "marcus_webb"
    rep_name = REP_NAMES.get(rep, "the 3 Lakes team")
    sector = prospect.get("sector") or "enterprise"

    sector_service = {
        "healthcare": "NEMT and medical transport",
        "enterprise": "corporate courier and executive transport",
        "platform": "driver supply partnership",
    }.get(sector, "logistics services")

    sector_type = {
        "healthcare": "healthcare organizations",
        "enterprise": "businesses",
        "platform": "platforms",
    }.get(sector, "organizations")

    task_prompt = (
        f"You are {rep_name} from 3 Lakes Logistics calling {contact_first} at {company}. "
        f"Keep this short and human — under 60 seconds if possible.\n\n"
        f"Introduction script:\n"
        f"\"Hey {contact_first}, this is {rep_name} from 3 Lakes Logistics. "
        f"I sent you an email recently about our {sector_service}. "
        f"I wanted to follow up and see if you had two minutes to chat. "
        f"We work with a lot of {sector_type} in your area and I think there might be a good fit.\"\n\n"
        f"If they want to book a call, direct them to: {BOOKING_URL}\n"
        f"If they ask for a callback number: 661-466-9932\n\n"
        f"Voicemail script (if no answer):\n"
        f"\"Hey {contact_first}, {rep_name} from 3 Lakes Logistics. "
        f"Sent you a note about {sector_service}. "
        f"Give us a call at 661-466-9932 when you have a moment. Thanks!\"\n\n"
        f"Rules: Be friendly, not pushy. Accept 'not interested' gracefully. Keep it under 2 minutes."
    )

    try:
        payload: dict[str, Any] = {
            "phone_number": phone,
            "task": task_prompt,
            "model": "enhanced",
            "language": "en",
            "max_duration": 5,
            "metadata": {
                "prospect_id": str(prospect.get("id", "")),
                "company": company,
                "rep": rep,
            },
        }
        if s.bland_ai_voice:
            payload["voice"] = s.bland_ai_voice

        r = httpx.post(
            f"{BLAND_API_URL}/calls",
            headers={"Authorization": f"Bearer {s.bland_ai_api_key}"},
            json=payload,
            timeout=20,
        )
        if not r.is_success:
            return {"status": "error", "error": f"Bland {r.status_code}: {r.text}"}
        data = r.json()
        return {"status": "started", "call_id": data.get("call_id")}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Call sequence runner
# ---------------------------------------------------------------------------

def run_call_sequence(daily_limit: int = 20) -> dict[str, Any]:
    """Fire Bland AI calls for warm prospects who have received at least one email."""
    db = get_supabase()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # Only call M-F 9am–5pm (UTC approximation — PST is UTC-7/8, these times cover business hours)
    weekday = now.weekday()  # 0=Mon … 6=Sun
    hour_utc = now.hour
    if weekday >= 5 or not (16 <= hour_utc <= 23):  # 9am–4pm PST ≈ 16:00–23:00 UTC
        return {"calls_queued": 0, "skipped": 0, "reason": "outside_calling_hours"}

    three_days_ago = (now - timedelta(days=3)).isoformat()

    rows = (
        db.table("lf_bd_prospects")
        .select("id,company,contact,phone,sector,rep,status,email_count,call_count,last_call_at,do_not_contact")
        .in_("status", ["prospecting", "contacted"])
        .neq("do_not_contact", True)
        .not_.is_("phone", "null")
        .gte("email_count", 1)
        .limit(200)
        .execute()
    ).data or []

    queued = 0
    skipped = 0

    for prospect in rows:
        if queued >= daily_limit:
            break

        call_count = prospect.get("call_count") or 0
        if call_count >= 3:
            skipped += 1
            continue

        last_call_at = prospect.get("last_call_at")
        if last_call_at and last_call_at > three_days_ago:
            skipped += 1
            continue

        prospect_id = str(prospect["id"])
        result = _fire_bland_call(prospect)

        # Log to outreach log
        try:
            db.table("lf_bd_outreach_log").insert({
                "prospect_id": prospect_id,
                "channel": "call",
                "step": prospect.get("sequence_step") or 0,
                "subject": f"Outbound call — {prospect.get('company', '')}",
                "status": "sent" if result.get("status") == "started" else "failed",
                "call_id": result.get("call_id"),
            }).execute()
        except Exception as log_exc:  # noqa: BLE001
            log_agent("lf_bizdev", "call_log_failed", payload={"prospect_id": prospect_id}, error=str(log_exc))

        if result.get("status") == "started":
            db.table("lf_bd_prospects").update({
                "call_count": call_count + 1,
                "last_call_at": now_iso,
                "updated_at": now_iso,
            }).eq("id", prospect_id).execute()
            queued += 1
            log_agent("lf_bizdev", "call_queued", payload={"prospect_id": prospect_id, "company": prospect.get("company"), "call_id": result.get("call_id")})
        else:
            log_agent("lf_bizdev", "call_failed", payload={"prospect_id": prospect_id}, error=result.get("error"))
            skipped += 1

        time.sleep(0.1)

    return {"calls_queued": queued, "skipped": skipped, "eligible": len(rows)}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run full email + call sequence. Called by scheduler and API routes."""
    if payload is None:
        payload = {}
    results: dict[str, Any] = {"agent": "lf_bizdev"}
    results["emails"] = run_email_sequence(daily_limit=payload.get("email_limit", 30))
    results["calls"] = run_call_sequence(daily_limit=payload.get("call_limit", 20))
    log_agent(
        "lf_bizdev",
        "run_complete",
        result=(
            f"emails_sent={results['emails'].get('sent')} "
            f"calls_queued={results['calls'].get('calls_queued')}"
        ),
    )
    return results
