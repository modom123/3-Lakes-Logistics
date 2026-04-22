"""Step 41: FMCSA New Entrant daily scraper.

Target: carriers with DOT <180 days old, <10 trucks — our ICP. Runs on a
daily cron and inserts new rows into `leads` with source='fmcsa'.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from . import dedupe, scoring


FMCSA_BASE = "https://mobile.fmcsa.dot.gov/qc/services/carriers"


def fetch_new_entrants(since_days: int = 1) -> list[dict[str, Any]]:
    """Hit SAFER's new-entrant feed. Real implementation scrapes
    https://li-public.fmcsa.dot.gov for the last `since_days` of new DOTs.
    """
    key = get_settings().fmcsa_webkey
    if not key:
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).date().isoformat()
    # TODO: implement the SAFER list-of-new-authorities endpoint; this is a stub
    try:
        r = httpx.get(f"{FMCSA_BASE}/new-entrants", params={"webKey": key, "since": since}, timeout=15)
        if r.status_code != 200:
            return []
        return r.json().get("content") or []
    except Exception:  # noqa: BLE001
        return []


def ingest() -> dict[str, Any]:
    entrants = fetch_new_entrants()
    sb = get_supabase()
    inserted = 0
    for e in entrants:
        dot = str(e.get("dotNumber") or "")
        mc = str(e.get("docketNumber") or "")
        if dedupe.is_duplicate(dot, mc):
            continue
        row = {
            "source": "fmcsa",
            "source_ref": dot,
            "company_name": e.get("legalName"),
            "dot_number": dot,
            "mc_number": mc,
            "phone": e.get("phone"),
            "email": e.get("emailAddress"),
            "address": e.get("physicalAddress"),
            "fleet_size": e.get("totalPowerUnits"),
        }
        row["score"] = scoring.score_lead(row)
        sb.table("leads").insert(row).execute()
        inserted += 1
    log_agent("vance", "fmcsa_ingest", result=f"{inserted}/{len(entrants)}")
    return {"fetched": len(entrants), "inserted": inserted}
