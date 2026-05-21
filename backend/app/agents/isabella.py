"""Isabella Cruz — VP Omnichannel Outreach (IEBC Step 57).
Segments the leads pipeline and builds personalized outreach campaign
batches ready for Vance (voice) or Echo (SMS) to execute.
"""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from . import memory as mem

_TEMPLATES: dict[str, str] = {
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

    template = _TEMPLATES.get(segment, _TEMPLATES["New"])
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
