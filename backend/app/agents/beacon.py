"""Beacon — Step 38. Daily ops digest — generates and emails the morning briefing."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase

_DIGEST_SUBJECT = "3LL Morning Digest — {date}"
_DIGEST_BODY = """\
Good morning,

Here is your 3 Lakes Logistics daily operations digest for {date}.

FLEET STATUS
  Active carriers:      {active_carriers}
  In onboarding:        {onboarding}

TODAY'S LOADS
  Loads on schedule:    {todays_loads}
  Gross (today):        ${todays_gross:,.2f}
  Exceptions:           {exceptions}

TOP ACTIONS
{top_actions}

— 3 Lakes Logistics Autonomous Ops
"""


def generate_digest() -> dict[str, Any]:
    sb = get_supabase()
    today = datetime.now(timezone.utc).date().isoformat()

    carriers = sb.table("active_carriers").select("id,status").execute().data or []
    loads = (
        sb.table("loads")
        .select("id,status,rate_total")
        .gte("pickup_at", today)
        .execute()
        .data or []
    )
    exceptions = [l for l in loads if l.get("status") in {"pod_needed", "in_transit"}]

    # CDL alerts expiring within 7 days
    cdl_urgent = (
        sb.table("driver_cdl")
        .select("id")
        .eq("cdl_status", "red")
        .execute()
        .data or []
    )

    top_actions = []
    if exceptions:
        top_actions.append(f"  • Review {len(exceptions)} exception load(s)")
    if cdl_urgent:
        top_actions.append(f"  • {len(cdl_urgent)} CDL(s) require immediate action")
    top_actions.append("  • Dispatch pending onboardings")
    top_actions.append("  • Review Friday payout preview (Settler)")
    if not top_actions:
        top_actions.append("  • No critical actions — good standing")

    return {
        "date": today,
        "active_carriers": sum(1 for c in carriers if c.get("status") == "active"),
        "onboarding": sum(1 for c in carriers if c.get("status") == "onboarding"),
        "todays_loads": len(loads),
        "todays_gross": float(sum((l.get("rate_total") or 0) for l in loads)),
        "exceptions": len(exceptions),
        "cdl_urgent": len(cdl_urgent),
        "top_actions": top_actions,
    }


def _send_digest_email(digest: dict, ops_email: str) -> dict:
    """Email the digest to the ops address via Nova/Postmark."""
    from .nova import _send  # lazy import to avoid circular at module load

    top_actions_str = "\n".join(digest["top_actions"])
    subject = _DIGEST_SUBJECT.format(date=digest["date"])
    body = _DIGEST_BODY.format(
        date=digest["date"],
        active_carriers=digest["active_carriers"],
        onboarding=digest["onboarding"],
        todays_loads=digest["todays_loads"],
        todays_gross=digest["todays_gross"],
        exceptions=digest["exceptions"],
        top_actions=top_actions_str,
    )
    return _send(ops_email, subject, body)


def run(payload: dict[str, Any]) -> dict[str, Any]:
    digest = generate_digest()

    email_result: dict[str, Any] = {"status": "not_configured"}
    ops_email = payload.get("ops_email") or get_settings().postmark_from_email
    if ops_email:
        email_result = _send_digest_email(digest, ops_email)

    log_agent("beacon", "digest", result=f"{digest['todays_loads']} loads / {digest['exceptions']} exceptions")
    return {"agent": "beacon", "digest": digest, "email": email_result}
