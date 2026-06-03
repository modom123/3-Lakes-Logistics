"""Email Campaigner — cold outreach to leads with email addresses via Postmark.

Uses the brand-accurate HTML template from studio/email_template.py which
matches the official 3 Lakes design materials (dark blue, real stats, brand copy).
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..logging_service import log_agent
from ..prospecting.activity import log_activity
from ..settings import get_settings
from ..supabase_client import get_supabase
from ..studio.email_template import build_html
from ..studio.registry import CHANNEL_COPY
from . import memory as mem

POSTMARK_API = "https://api.postmarkapp.com/email"


def send_batch(daily_limit: int = 100) -> dict[str, Any]:
    db = get_supabase()
    s = get_settings()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()

    rows = (
        db.table("leads")
        .select("id,contact_name,company_name,state,email")
        .not_.is_("email", "null")
        .in_("status", ["New", "Contacted"])
        .neq("do_not_contact", True)
        .or_(f"last_touch_at.is.null,last_touch_at.lt.{cutoff}")
        .limit(daily_limit)
        .execute()
    ).data or []

    sent = 0
    failed = 0
    now = datetime.now(timezone.utc).isoformat()

    for row in rows:
        email = (row.get("email") or "").strip()
        if not email:
            failed += 1
            continue

        state = row.get("state") or ""
        lead_name = row.get("contact_name") or "there"
        html_body = build_html(state=state, lead_name=lead_name)
        subject = (
            CHANNEL_COPY["email"]["subject_open_loads"].format(state=state)
            if state else CHANNEL_COPY["email"]["subject_pitch"]
        )

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
                    "To": email,
                    "Subject": subject,
                    "HtmlBody": html_body,
                    "MessageStream": "outbound",
                },
                timeout=15,
            )
            r.raise_for_status()
            db.table("leads").update(
                {"last_touch_at": now, "last_contact_at": now, "outreach_channel": "email"}
            ).eq("id", row["id"]).execute()
            log_activity(row["id"], "email", "sent",
                         summary=f"Subject: {subject}",
                         agent="email_campaigner",
                         payload={"to": email, "subject": subject})
            sent += 1
        except Exception as exc:  # noqa: BLE001
            log_agent("email_campaigner", "send_failed", payload={"lead_id": row["id"]}, error=str(exc))
            log_activity(row["id"], "email", "error",
                         summary=str(exc)[:120], agent="email_campaigner",
                         payload={"to": email})
            failed += 1

        time.sleep(0.05)

    summary = {"agent": "email_campaigner", "sent": sent, "failed": failed, "eligible": len(rows)}
    mem.remember(
        "email_campaigner", "last_batch", summary,
        summary=f"sent={sent} failed={failed} eligible={len(rows)}",
    )
    log_agent("email_campaigner", "send_batch", result=f"sent={sent} failed={failed}")
    return summary


def run(payload: dict[str, Any]) -> dict[str, Any]:
    return send_batch(daily_limit=payload.get("daily_limit", 100))
