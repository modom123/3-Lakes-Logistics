"""Step 60: dry-run end-to-end across the top 10 leads.

Exercises every module without actually dialing / texting anyone.
Prints a report so the Commander can verify all APIs are wired before
launch.
"""
from __future__ import annotations

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from . import dedupe, scoring, outbound_schedule, traffic_controller, ab_testing, sms_compliance


def run(limit: int = 10) -> dict:
    sb = get_supabase()
    leads = sb.table("leads").select("*").order("score", desc=True).limit(limit).execute().data or []
    report: list[dict] = []
    for lead in leads:
        ch = traffic_controller.pick_channel(lead)
        state = (lead.get("address") or "").strip()[-2:].upper()
        dialable = outbound_schedule.can_dial(state)
        variant = ab_testing.pick_variant("founders_v1", str(lead.get("id")))
        dup = dedupe.is_duplicate(lead.get("dot_number"), lead.get("mc_number"))
        rescore = scoring.score_lead(lead)
        report.append({
            "lead_id": lead.get("id"),
            "company": lead.get("company_name"),
            "channel": ch, "dialable_now": dialable,
            "variant": variant["variant"], "score": rescore, "duplicate": dup,
            "compliance_footer": sms_compliance.compliance_footer(),
        })
    log_agent("vance", "dry_run", result=f"{len(report)} leads checked")
    return {"ok": True, "count": len(report), "leads": report}
