"""Lead Scoring — 0 to 10.

Scoring model v2 — Safety ratings, contact completeness, and authority quality
are now primary factors. A carrier with no phone, no email, and a bad safety
rating will score 0-2 and stay out of the Vance call queue.

Factor weights
─────────────
Safety Rating             (0–3 pts, or −2 penalty)
  Satisfactory            → +3  best-in-class, DOT cleared
  Not Rated               → +1  new authority, no incidents yet — acceptable
  Conditional             → +0  flag; still contactable but watch closely
  Unsatisfactory          → −2  do not auto-call; manual review only

Operating Status          (0–1 pts, or −2 penalty)
  Authorized              → +1
  Not Authorized          → −2  (out-of-authority, likely inactive)
  Out of Service          → −3  (hard disqualifier)

Contact Completeness      (0–4 pts)
  Phone present           → +2  essential for Vance outbound
  Email present           → +1  needed for campaign sequences
  Named contact           → +1  legal_name / contact_name present

Fleet Size                (0–2 pts)
  1–5 trucks              → +2  ideal owner-op / small fleet
  6–15 trucks             → +1  small fleet, still targetable
  16+ trucks or unknown   → +0  too large to lease-on easily

Authority Quality         (0–1 pts)
  MC number present       → +1  interstate authority — can haul for brokers

Activity Signal           (0–1 pts)
  MCS-150 filed ≤ 365 days→ +1  filed recently = active operator
  DOT authority < 180 days→ +1  new entrant, actively looking for loads
  (max +1 combined)

Equipment Match           (0–1 pts)
  Founders categories     → +1  dry van, reefer, flatbed, step deck, etc.

Floor: 0    Cap: 10
Vance auto-call threshold: score >= 8
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

FOUNDERS_EQUIPMENT = {
    "dry_van", "reefer", "flatbed", "step_deck",
    "box26", "tanker_hazmat", "hotshot", "auto",
    "tractor-trailer", "tractor_trailer",
}

_SAFETY_SCORES = {
    "satisfactory":   3,
    "not rated":      1,
    "":               1,   # blank = new carrier, treat as Not Rated
    "conditional":    0,
    "unsatisfactory": -2,
}

_BAD_OP_STATUS = {"NOT AUTHORIZED", "INACTIVE", "OUT OF SERVICE"}


def score_lead(lead: dict[str, Any]) -> int:
    score = 0

    # ── Safety Rating ─────────────────────────────────────────────────────────
    raw_rating = (lead.get("safety_rating") or "").strip().lower()
    score += _SAFETY_SCORES.get(raw_rating, 0)

    # ── Operating Status ──────────────────────────────────────────────────────
    op_status = (lead.get("operating_status") or "").strip().upper()
    oos = lead.get("oos_date") or lead.get("out_of_service_date")
    if oos:
        score -= 3   # Out of service — hard disqualifier
    elif op_status == "NOT AUTHORIZED":
        score -= 2
    elif op_status in ("AUTHORIZED", ""):
        score += 1   # Confirmed authorized or unknown (new entry)

    # ── Contact Completeness ─────────────────────────────────────────────────
    phone = (lead.get("phone") or lead.get("telephone") or "").strip()
    email = (lead.get("email") or "").strip()
    contact = (
        lead.get("contact_name") or lead.get("legal_name") or
        lead.get("company_name") or lead.get("business_name") or ""
    ).strip()

    if phone:
        score += 2   # Phone is essential for Vance — double weight
    if email:
        score += 1
    if contact:
        score += 1   # Named contact / legal entity present

    # ── Fleet Size ────────────────────────────────────────────────────────────
    fleet = lead.get("fleet_size") or lead.get("total_power_units") or 0
    try:
        fleet = int(fleet)
    except (ValueError, TypeError):
        fleet = 0
    if 1 <= fleet <= 5:
        score += 2
    elif 6 <= fleet <= 15:
        score += 1

    # ── MC Authority ──────────────────────────────────────────────────────────
    mc = (lead.get("mc_number") or lead.get("mc_mx_ff_number") or "").strip()
    if mc and mc not in ("", "0"):
        score += 1

    # ── Activity Signal ───────────────────────────────────────────────────────
    activity_bonus = 0

    # MCS-150 filed within the last year
    mcs_date = (lead.get("mcs150_date") or lead.get("mcs150_form_date") or "")[:10]
    if mcs_date:
        try:
            mcs_dt = datetime.fromisoformat(mcs_date).replace(tzinfo=timezone.utc)
            days_since = (datetime.now(timezone.utc) - mcs_dt).days
            if days_since <= 365:
                activity_bonus = 1
        except ValueError:
            pass

    # New authority (< 180 days old) — hunting for loads
    dot_age = lead.get("dot_age_days")
    add_date = (lead.get("add_date") or "")[:10]
    if dot_age is None and add_date:
        try:
            add_dt = datetime.fromisoformat(add_date).replace(tzinfo=timezone.utc)
            dot_age = (datetime.now(timezone.utc) - add_dt).days
        except ValueError:
            pass
    if dot_age is not None and int(dot_age) < 180:
        activity_bonus = 1

    score += activity_bonus

    # ── Equipment Match ───────────────────────────────────────────────────────
    equip = lead.get("equipment_types") or lead.get("equipment_type") or []
    if isinstance(equip, str):
        equip = [equip]
    if any(str(e).lower().replace(" ", "_").replace("-", "_") in FOUNDERS_EQUIPMENT for e in equip):
        score += 1

    return max(0, min(score, 10))


def score_summary(lead: dict[str, Any]) -> dict[str, Any]:
    """Return a detailed breakdown of why a lead scored the way it did."""
    raw_rating = (lead.get("safety_rating") or "").strip().lower()
    op_status  = (lead.get("operating_status") or "").strip().upper()
    oos        = lead.get("oos_date") or lead.get("out_of_service_date")
    phone      = (lead.get("phone") or lead.get("telephone") or "").strip()
    email      = (lead.get("email") or "").strip()
    fleet      = lead.get("fleet_size") or lead.get("total_power_units") or 0
    mc         = (lead.get("mc_number") or "").strip()

    safety_pts = _SAFETY_SCORES.get(raw_rating, 0)
    flags = []
    if raw_rating == "unsatisfactory":
        flags.append("UNSATISFACTORY safety rating — manual review required")
    if raw_rating == "conditional":
        flags.append("Conditional safety rating — approach with caution")
    if oos:
        flags.append("Carrier is Out of Service — disqualified from auto-call")
    if op_status == "NOT AUTHORIZED":
        flags.append("Not Authorized to operate — verify before outreach")
    if not phone:
        flags.append("No phone number — Vance cannot call")
    if not email:
        flags.append("No email — cannot add to email campaigns")

    return {
        "total_score": score_lead(lead),
        "breakdown": {
            "safety_rating":      raw_rating or "not rated",
            "safety_pts":         safety_pts,
            "operating_status":   op_status or "unknown",
            "has_phone":          bool(phone),
            "phone_pts":          2 if phone else 0,
            "has_email":          bool(email),
            "email_pts":          1 if email else 0,
            "fleet_size":         fleet,
            "mc_number":          mc,
            "out_of_service":     bool(oos),
        },
        "flags": flags,
        "auto_call_eligible": score_lead(lead) >= 8 and bool(phone) and not oos,
    }
