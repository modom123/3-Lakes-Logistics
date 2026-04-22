"""Step 53: Airtable → Supabase sync for legacy leads."""
from __future__ import annotations

from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from . import dedupe, scoring


def sync_airtable_leads(table: str = "Leads") -> dict[str, Any]:
    s = get_settings()
    if not s.airtable_api_key or not s.airtable_base_id:
        return {"status": "stub", "reason": "airtable_not_configured"}
    url = f"https://api.airtable.com/v0/{s.airtable_base_id}/{table}"
    r = httpx.get(url, headers={"Authorization": f"Bearer {s.airtable_api_key}"}, timeout=30)
    r.raise_for_status()
    records = r.json().get("records") or []
    sb = get_supabase()
    inserted = 0
    for rec in records:
        f = rec.get("fields", {})
        dot = f.get("DOT")
        mc = f.get("MC")
        if dedupe.is_duplicate(dot, mc):
            continue
        row = {
            "source": "airtable", "source_ref": rec.get("id"),
            "company_name": f.get("Company"),
            "dot_number": dot, "mc_number": mc,
            "contact_name": f.get("Contact"), "phone": f.get("Phone"),
            "email": f.get("Email"), "fleet_size": f.get("Fleet"),
        }
        row["score"] = scoring.score_lead(row)
        sb.table("leads").insert(row).execute()
        inserted += 1
    log_agent("vance", "airtable_sync", result=f"{inserted}/{len(records)}")
    return {"fetched": len(records), "inserted": inserted}
