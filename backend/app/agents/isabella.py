"""Isabella Cruz — VP Omnichannel Outreach (IEBC Step 57).
Segments the leads pipeline and builds personalized outreach campaign
batches ready for Vance (voice) or Echo (SMS) to execute.

Two campaign types:
  build_campaign()            — new/warm leads from the leads table
  run_carrier_reengagement()  — at-risk carriers from Carrier Brain (Winston feeds these)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from . import memory as mem
from . import carrier_brain as cb

_LEAD_TEMPLATES: dict[str, str] = {
    "New": (
        "Hi {name}, this is 3 Lakes Logistics — we help carriers like {company} "
        "book more loads and get paid faster. Do you have capacity this week?"
    ),
    "Contacted": (
        "Hi {name}, following up from 3 Lakes Logistics. We'd love to get {company} "
        "set up on our load board — takes under 10 minutes. Ready to move forward?"
    ),
    "Warm": (
        "Hi {name}, great connecting earlier! We have loads matching {equipment} "
        "available in your area right now. Want me to send the details?"
    ),
}

# Re-engagement message templates keyed by Winston's risk priority
_REENGAGEMENT_TEMPLATES: dict[str, str] = {
    "high": (
        "Hi {name}, it's 3 Lakes Logistics. We noticed {company} hasn't booked a load "
        "with us yet — we'd love to get you activated. We have loads available right now "
        "and can walk you through the process in minutes. Want to get started?"
    ),
    "medium": (
        "Hi {name}, this is 3 Lakes Logistics checking in on {company}. It's been a "
        "while since your last load — we have great lanes open and want to make sure "
        "you're getting the best rates. Can we set something up?"
    ),
    "low": (
        "Hi {name}, 3 Lakes Logistics here. We have high-demand loads in your area "
        "and wanted to make sure {company} gets first look. Ready to book when you are!"
    ),
}


def build_campaign(segment: str = "New", limit: int = 50) -> dict[str, Any]:
    sb = get_supabase()
    rows = (
        sb.table("leads")
        .select("id,business_name,contact_name,phone,equipment_type,status,score,city,state")
        .eq("status", segment)
        .order("score", desc=True)
        .limit(limit)
        .execute()
        .data or []
    )

    template = _LEAD_TEMPLATES.get(segment, _LEAD_TEMPLATES["New"])
    campaign: list[dict[str, Any]] = []
    for lead in rows:
        name = lead.get("contact_name") or lead.get("business_name") or "there"
        msg = template.format(
            name=name,
            company=lead.get("business_name") or "your company",
            equipment=lead.get("equipment_type") or "your equipment",
        )
        campaign.append({
            "lead_id": lead["id"],
            "phone": lead.get("phone"),
            "name": name,
            "location": f"{lead.get('city') or ''}, {lead.get('state') or ''}".strip(", "),
            "score": lead.get("score"),
            "message": msg,
        })

    # Score distribution
    scores = [c["score"] for c in campaign if c["score"] is not None]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    return {
        "segment": segment,
        "total_leads_in_segment": len(rows),
        "campaign_size": len(campaign),
        "avg_lead_score": avg_score,
        "preview": campaign[:5],
        "handoff": "Ready for Vance (voice) or Echo (SMS) — pass campaign to run agent.",
    }


def run_carrier_reengagement(limit: int = 30) -> dict[str, Any]:
    """Build a re-engagement campaign for at-risk carriers identified by Winston.

    Reads risk_profile records from Carrier Brain, builds personalised messages
    keyed by priority, and writes a 'relationship' memory entry back to Carrier
    Brain for each carrier targeted — so call history stays in one place.
    """
    # Pull at-risk carriers straight from Carrier Brain
    at_risk_records = cb.search_by_type("risk_profile", limit=limit)

    campaign: list[dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for record in at_risk_records:
        cid = record.get("carrier_id")
        if not cid:
            continue
        val = record.get("memory_value") or {}
        priority = val.get("priority", "low")
        carrier_name = record.get("carrier_name") or "there"
        company = record.get("carrier_name") or "your company"

        # Look up phone from active_carriers (best effort)
        try:
            sb = get_supabase()
            row = (
                sb.table("active_carriers")
                .select("contact_name,phone,contact_phone")
                .eq("id", cid)
                .limit(1)
                .execute()
                .data or [{}]
            )[0]
            contact_name = row.get("contact_name") or carrier_name
            phone = row.get("phone") or row.get("contact_phone") or ""
        except Exception:
            contact_name = carrier_name
            phone = ""

        msg = _REENGAGEMENT_TEMPLATES.get(priority, _REENGAGEMENT_TEMPLATES["low"]).format(
            name=contact_name,
            company=company,
        )

        campaign.append({
            "carrier_id":  cid,
            "name":        contact_name,
            "company":     company,
            "phone":       phone,
            "priority":    priority,
            "risk_reason": val.get("risk_reason"),
            "total_loads": val.get("total_loads", 0),
            "message":     msg,
        })

        # Write relationship memory to Carrier Brain — records this campaign touch
        cb.remember_carrier(
            cid,
            company,
            "relationship",
            {
                "last_campaign_at": now_iso,
                "campaign_type":    "re_engagement",
                "priority":         priority,
                "message_preview":  msg[:120],
                "touch_count":      (record.get("interaction_count") or 0) + 1,
            },
            agent="isabella",
            confidence=0.6,
            summary=f"Re-engagement campaign touch · {priority} priority",
        )

    high_count = sum(1 for c in campaign if c["priority"] == "high")
    result = {
        "campaign_type":      "carrier_reengagement",
        "carriers_targeted":  len(campaign),
        "high_priority":      high_count,
        "preview":            campaign[:5],
        "handoff":            "Ready for Vance (voice calls) — prioritise high_priority carriers first.",
    }

    log_agent(
        "isabella", "carrier_reengagement",
        payload={"limit": limit},
        result=f"{len(campaign)} carriers targeted · {high_count} high priority",
    )

    mem.remember(
        "isabella", "last_reengagement_campaign",
        {"carriers_targeted": len(campaign), "high_priority": high_count, "run_at": now_iso},
        confidence=0.65,
        summary=f"Re-engagement: {len(campaign)} carriers · {high_count} high priority",
    )

    if campaign:
        mem.log_interaction("isabella", "vance", "handoff",
            payload={"carriers_targeted": len(campaign), "high_priority": high_count},
            result={"status": "reengagement_campaign_ready"},
            outcome="success",
            outcome_notes=f"Re-engagement campaign for {len(campaign)} at-risk carriers built — Vance to call high-priority first",
        )

    return {"agent": "isabella", **result}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    segment = payload.get("segment", "New")
    limit = int(payload.get("limit", 50))

    # Check what Naomi and Winston have written to memory — prioritize their signals
    tier_b  = mem.recall_value("naomi", "tier_b_targets") or {}
    churn   = mem.recall_value("winston", "churn_signals") or {}
    directive = mem.recall_value("org", "strategic_directive") or {}

    result = build_campaign(segment=segment, limit=limit)

    # Surface what intelligence was available
    result["informed_by"] = {
        "naomi_tier_b_count":  tier_b.get("count", 0),
        "winston_at_risk":     churn.get("at_risk_count", 0),
        "org_priority":        directive.get("priority", "unknown"),
    }

    log_agent(
        "isabella", "build_campaign",
        payload={"segment": segment, "limit": limit},
        result=f"{result['campaign_size']} contacts avg_score={result['avg_lead_score']}",
    )

    # Write campaign summary to org brain
    mem.remember(
        "isabella", "last_campaign",
        {"segment": segment, "size": result["campaign_size"], "avg_score": result["avg_lead_score"]},
        confidence=0.6,
        summary=f"Campaign: {result['campaign_size']} {segment} leads · avg score {result['avg_lead_score']}",
    )
    mem.log_interaction("isabella", "vance", "handoff",
        payload={"campaign_size": result["campaign_size"], "segment": segment},
        result={"status": "campaign_ready"},
        outcome="success",
        outcome_notes="Campaign built — Vance to execute voice follow-up on high-score contacts",
    )
    return {"agent": "isabella", **result}
