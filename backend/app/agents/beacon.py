"""Beacon — Step 38. High-level daily summary."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase


def generate_digest() -> dict[str, Any]:
    sb = get_supabase()
    today = datetime.now(timezone.utc).date().isoformat()
    carriers = sb.table("active_carriers").select("id,status").execute().data or []
    loads = sb.table("loads").select("id,status,rate_total").gte("pickup_at", today).execute().data or []
    exceptions = [l for l in loads if l.get("status") in {"pod_needed", "in_transit"}]
    return {
        "date": today,
        "active_carriers": sum(1 for c in carriers if c.get("status") == "active"),
        "onboarding": sum(1 for c in carriers if c.get("status") == "onboarding"),
        "todays_loads": len(loads),
        "todays_gross": sum((l.get("rate_total") or 0) for l in loads),
        "exceptions": len(exceptions),
        "top_actions": [
            "review exceptions" if exceptions else "no exceptions",
            "dispatch pending onboardings",
            "review payout preview (Fri)",
        ],
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    digest = generate_digest()
    log_agent("beacon", "digest", result=f"{digest['todays_loads']} loads")
    return {"agent": "beacon", "digest": digest}
