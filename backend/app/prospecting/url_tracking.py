"""Step 51: URL tracking for link clicks on the intake form."""
from __future__ import annotations

import hashlib
from urllib.parse import urlencode


def build_tracked_url(base: str, lead_id: str, campaign: str) -> str:
    h = hashlib.md5(f"{lead_id}:{campaign}".encode()).hexdigest()[:10]
    params = {"utm_source": "3ll", "utm_campaign": campaign, "utm_ref": h, "lead": lead_id}
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}{urlencode(params)}"


def record_click(lead_id: str, utm_ref: str) -> None:
    from ..logging_service import log_agent
    from ..supabase_client import get_supabase

    log_agent("vance", "link_click", payload={"lead_id": lead_id, "utm_ref": utm_ref}, result="recorded")

    try:
        sb = get_supabase()
        # Read current clicks count then increment
        row = sb.table("leads").select("id,clicks").eq("id", lead_id).maybe_single().execute().data
        if row is not None:
            current = int(row.get("clicks") or 0)
            sb.table("leads").update({"clicks": current + 1}).eq("id", lead_id).execute()
    except Exception:  # noqa: BLE001
        pass  # click tracking is best-effort; never block the redirect
