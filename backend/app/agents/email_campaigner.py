"""Email Campaigner — cold outreach to leads with email addresses via Postmark."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from . import memory as mem

CALENDLY_URL = "https://calendly.com/3lakes/commander-call"
POSTMARK_API = "https://api.postmarkapp.com/email"

_EMAIL_HTML = """\
<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#222;">
  <p>Hi {name},</p>
  <p>I'm reaching out because we're actively moving loads through <strong>{state}</strong>
  and we're looking for reliable owner-operators to work with.</p>
  <p>At <strong>3 Lakes Logistics</strong>, our Founders program gives you:</p>
  <ul>
    <li><strong>$300/month</strong> — locked in for life</li>
    <li><strong>100% of load earnings</strong> stay in your pocket</li>
    <li>Full dispatch automation — we handle broker communication, paperwork, and compliance</li>
    <li>Dedicated support so you can focus on driving</li>
  </ul>
  <p>We only work with a limited number of carriers per region, and spots in {state} are
  filling up fast.</p>
  <p>If you'd like to see how it works, grab a free 15-minute call with our team:</p>
  <p style="text-align:center;">
    <a href="{calendly}" style="background:#1a56db;color:#fff;padding:12px 24px;
    border-radius:6px;text-decoration:none;font-weight:bold;">
      Schedule a Free Call
    </a>
  </p>
  <p>No pressure — just a quick conversation to see if it's a fit.</p>
  <p>Best,<br>The 3 Lakes Logistics Team</p>
  <hr style="border:none;border-top:1px solid #eee;margin-top:32px;">
  <p style="font-size:11px;color:#888;">
    You received this because your carrier information is publicly listed with the FMCSA.<br>
    <a href="https://3lakeslogistics.com/unsubscribe?id={lead_id}">Unsubscribe</a>
  </p>
</body>
</html>
"""


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

        state = row.get("state") or "your area"
        html_body = _EMAIL_HTML.format(
            name=row.get("contact_name") or "there",
            state=state,
            calendly=CALENDLY_URL,
            lead_id=row["id"],
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
                    "Subject": f"Open loads in {state} — 3 Lakes Logistics",
                    "HtmlBody": html_body,
                    "MessageStream": "outbound",
                },
                timeout=15,
            )
            r.raise_for_status()
            db.table("leads").update(
                {"last_touch_at": now, "last_contact_at": now, "outreach_channel": "email"}
            ).eq("id", row["id"]).execute()
            sent += 1
        except Exception as exc:  # noqa: BLE001
            log_agent("email_campaigner", "send_failed", payload={"lead_id": row["id"]}, error=str(exc))
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
