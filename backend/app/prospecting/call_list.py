# ─────────────────────────────────────────────────────────────
# File:     backend/app/prospecting/call_list.py
# Created:  2026-09-29 22:31 UTC
# Purpose:  Daily human call list + call-outcome bookkeeping.
# ─────────────────────────────────────────────────────────────
"""Daily call list for the sales desk.

The AI dialers (Vance / Bland) run on their own schedule. This is the list a
person works by hand: best-scored, newest-authority carriers with a phone,
never flagged do-not-contact, and (optionally) only those inside 9am-5pm
local calling hours right now.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Any

from .. import pricing
from .outbound_schedule import can_dial

# Statuses that mean "still worth a call". Eagle Eye writes Title-case;
# older scrapers wrote lowercase stages.
CALLABLE_STATUSES = frozenset({"new", "contacted", "interested", "nurture"})

OPENER = (
    "Hi, this is {caller} with 3 Lakes Logistics. I saw {company} got its "
    "authority recently. Are you finding enough loads, or would a dispatcher help?"
)
PITCH = (
    "We book your loads, handle broker paperwork, check calls and detention. "
    f"Pay-as-you-go is {int(pricing.HEAVY_PAYG_FEE_PCT * 100)}% per load with no contract, "
    f"or Founders is a flat ${pricing.FOUNDERS_MONTHLY_USD}/month per truck and you keep 100%."
)

# outcome -> (status, days until next touch or None, do_not_contact)
OUTCOMES: dict[str, tuple[str, int | None, bool]] = {
    "no_answer":      ("Contacted", 1, False),
    "voicemail":      ("Contacted", 2, False),
    "callback":       ("Interested", 1, False),
    "interested":     ("Interested", 1, False),
    "sent_signup":    ("Interested", 2, False),
    "signed":         ("Won", None, False),
    "not_interested": ("Lost", 90, False),
    "wrong_number":   ("Lost", None, True),
    "do_not_call":    ("Lost", None, True),
}


def _status(row: dict[str, Any]) -> str:
    return str(row.get("status") or row.get("stage") or "new").strip().lower()


def build_call_list(
    rows: list[dict[str, Any]],
    limit: int = 50,
    dial_now: bool = False,
    now_utc: datetime | None = None,
) -> list[dict[str, Any]]:
    """Filter and rank lead rows into today's call list."""
    now = now_utc or datetime.now(timezone.utc)
    out: list[dict[str, Any]] = []
    for r in rows:
        if r.get("do_not_contact") or not (r.get("phone") or r.get("phone_number")):
            continue
        if _status(r) not in CALLABLE_STATUSES:
            continue
        nxt = r.get("next_touch_at")
        if nxt:
            try:
                if datetime.fromisoformat(str(nxt).replace("Z", "+00:00")) > now:
                    continue
            except ValueError:
                pass
        if dial_now and not can_dial(r.get("state") or "", now):
            continue
        out.append(r)
    # Highest score first; among equals, the newest authority (smallest age) first.
    out.sort(key=lambda r: (-(r.get("score") or 0), r.get("dot_age_days") if r.get("dot_age_days") is not None else 10_000))
    return [_shape(r) for r in out[:limit]]


def _shape(r: dict[str, Any]) -> dict[str, Any]:
    company = r.get("business_name") or r.get("company_name") or r.get("legal_name") or "your company"
    return {
        "id":           r.get("id"),
        "company":      company,
        "contact":      r.get("contact_name") or "",
        "phone":        r.get("phone") or r.get("phone_number"),
        "state":        r.get("state") or "",
        "city":         r.get("city") or "",
        "dot_number":   r.get("dot_number") or "",
        "mc_number":    r.get("mc_number") or "",
        "fleet_size":   r.get("fleet_size"),
        "dot_age_days": r.get("dot_age_days"),
        "score":        r.get("score"),
        "status":       r.get("status") or r.get("stage") or "New",
        "opener":       OPENER.format(caller="{your name}", company=company),
    }


def to_csv(items: list[dict[str, Any]]) -> str:
    cols = ["company", "contact", "phone", "city", "state", "dot_number", "mc_number",
            "fleet_size", "dot_age_days", "score", "status", "id"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols + ["outcome", "notes"], extrasaction="ignore")
    w.writeheader()
    for it in items:
        w.writerow(it)
    return buf.getvalue()


def outcome_patch(outcome: str, notes: str | None = None, now_utc: datetime | None = None) -> dict[str, Any]:
    """Row update for a logged call. Raises KeyError on an unknown outcome."""
    status, days, dnc = OUTCOMES[outcome]
    now = now_utc or datetime.now(timezone.utc)
    patch: dict[str, Any] = {
        "status": status,
        "stage": status,
        "last_contact_at": now.isoformat(),
        "last_touch_at": now.isoformat(),
        "outreach_channel": "call",
        "next_touch_at": (now + timedelta(days=days)).isoformat() if days is not None else None,
    }
    if dnc:
        patch["do_not_contact"] = True
    if notes:
        patch["notes"] = notes[:2000]
    return patch
