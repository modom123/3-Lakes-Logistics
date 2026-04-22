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
    log_agent("vance", "link_click", payload={"lead_id": lead_id, "utm_ref": utm_ref}, result="recorded")
    # TODO: increment a clicks counter on leads
