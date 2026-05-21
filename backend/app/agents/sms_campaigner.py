"""SMS Campaigner — bulk outreach to Tier B leads (score 4-7) via Twilio."""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from . import memory as mem

CALENDLY_URL = "https://calendly.com/3lakes/commander-call"

_TEMPLATES = [
    "Hi {name}, {company} running loads in {state}? 3 Lakes Logistics pays fast & keeps you moving. Book a free call: {link} Reply STOP to opt out.",
    "Hey {name} — owner-operators in {state} are locking in $300/mo with 3 Lakes & keeping 100% of earnings. Interested? {link} Reply STOP to opt out.",
    "{name}, tired of chasing brokers in {state}? 3 Lakes automates your dispatch so you haul more. See how: {link} Reply STOP to opt out.",
]


def _normalize_phone(phone: str) -> str | None:
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return None


def send_batch(daily_limit: int = 75) -> dict[str, Any]:
    db = get_supabase()
    s = get_settings()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    rows = (
        db.table("leads")
        .select("id,contact_name,company_name,state,phone")
        .gte("score", 4)
        .lt("score", 8)
        .not_.is_("phone", "null")
        .neq("do_not_contact", True)
        .not_.in_("status", ["Converted", "Dead"])
        .or_(f"last_touch_at.is.null,last_touch_at.lt.{cutoff}")
        .limit(daily_limit)
        .execute()
    ).data or []

    sent = 0
    failed = 0
    now = datetime.now(timezone.utc).isoformat()
    url = f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json"

    for i, row in enumerate(rows):
        phone = _normalize_phone(row.get("phone") or "")
        if not phone:
            failed += 1
            continue

        template = _TEMPLATES[i % len(_TEMPLATES)]
        body = template.format(
            name=row.get("contact_name") or "there",
            company=row.get("company_name") or "your company",
            state=row.get("state") or "your area",
            link=CALENDLY_URL,
        )
        # Truncate to SMS safe length
        if len(body) > 160:
            body = body[:157] + "..."

        try:
            r = httpx.post(
                url,
                auth=(s.twilio_account_sid, s.twilio_auth_token),
                data={"From": s.twilio_from_number, "To": phone, "Body": body},
                timeout=15,
            )
            r.raise_for_status()
            db.table("leads").update(
                {"last_touch_at": now, "last_contact_at": now, "outreach_channel": "sms"}
            ).eq("id", row["id"]).execute()
            sent += 1
        except Exception as exc:  # noqa: BLE001
            log_agent("sms_campaigner", "send_failed", payload={"lead_id": row["id"]}, error=str(exc))
            failed += 1

        time.sleep(0.1)

    summary = {"agent": "sms_campaigner", "sent": sent, "failed": failed, "eligible": len(rows)}
    mem.remember(
        "sms_campaigner", "last_batch", summary,
        summary=f"sent={sent} failed={failed} eligible={len(rows)}",
    )
    log_agent("sms_campaigner", "send_batch", result=f"sent={sent} failed={failed}")
    return summary


def run(payload: dict[str, Any]) -> dict[str, Any]:
    return send_batch(daily_limit=payload.get("daily_limit", 75))
