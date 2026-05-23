"""CC Gulley — Chief Strategy Officer (IEBC Step 55).

Drives long-range strategic planning, competitive positioning, and
initiative execution across all departments. Works directly under
Mark Odom (CEO) and alongside Victoria Roth (CGO) to align every
department to the company vision and growth model.

Daily run: reviews market intel, audits initiative progress, surfaces
strategic risks, and writes the org-wide strategic plan to memory.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from . import memory as mem


# Strategic initiative categories CC monitors
_INITIATIVE_DOMAINS = [
    "carrier_acquisition",
    "revenue_diversification",
    "technology_partnerships",
    "market_expansion",
    "operational_efficiency",
    "talent_development",
]


def _safe_count(table: str, filters: dict | None = None) -> int:
    try:
        sb = get_supabase()
        q = sb.table(table).select("id", count="exact")
        if filters:
            for k, v in filters.items():
                q = q.eq(k, v)
        return q.execute().count or 0
    except Exception:
        return 0


def strategic_plan() -> dict[str, Any]:
    """
    Synthesizes cross-functional intelligence into a strategic plan.
    Reads market data, growth metrics, and competitive signals to produce
    a 30/60/90-day strategic roadmap for the Commander.
    """
    # Pull executive intelligence from org brain
    market_intel    = mem.recall_value("alexander", "fmcsa_intel") or {}
    growth_snapshot = mem.recall_value("victoria", "last_snapshot") or {}
    lead_intel      = mem.recall_value("naomi", "lead_intel") or {}
    churn_signals   = mem.recall_value("winston", "churn_signals") or {}
    commander_dir   = mem.recall_value("mark_odom", "commander_directive") or {}

    # Live metrics
    total_carriers  = _safe_count("active_carriers")
    active_carriers = _safe_count("active_carriers", {"status": "active"})
    total_leads     = _safe_count("leads")
    qualified_leads = _safe_count("leads", {"status": "Qualified"})

    activation_rate = round(active_carriers / total_carriers * 100, 1) if total_carriers else 0
    lead_quality    = round(qualified_leads / total_leads * 100, 1) if total_leads else 0

    # 30-day strategic priorities
    priorities_30d: list[str] = []
    if activation_rate < 70:
        priorities_30d.append(f"Intensify carrier onboarding pipeline — activation at {activation_rate}%")
    if lead_quality < 30:
        priorities_30d.append(f"Improve lead scoring model — only {lead_quality}% qualified")
    hot_states = market_intel.get("hot_states", {})
    if hot_states:
        top_state = list(hot_states.keys())[0] if hot_states else None
        if top_state:
            priorities_30d.append(f"Launch geo-targeted push into {top_state} — highest market density")
    if not priorities_30d:
        priorities_30d.append("Execute Founders pricing close — drive toward 1,000-truck cap")

    # 60-day initiatives
    initiatives_60d: list[str] = [
        "Expand load board integrations (DAT, TruckStop, 123Loads) for broader dispatch coverage",
        "Launch carrier referral program — incentivize word-of-mouth acquisition",
        "Develop broker relationship tier system — preferred broker list for rate negotiation",
    ]

    # 90-day vision
    vision_90d: list[str] = [
        "Position 3 Lakes Logistics as the #1 AI-powered dispatch OS for owner-operators",
        "Target $300K ARR milestone — 1,000 trucks × $300/mo × Founders close",
        "Build institutional carrier memory — 18 months of lane data per carrier for hyper-personalized dispatch",
    ]

    # Strategic risks
    risks: list[str] = []
    at_risk = churn_signals.get("at_risk_count", 0)
    if at_risk and at_risk > 5:
        risks.append(f"Carrier churn risk — {at_risk} carriers flagged by Winston. Escalate to Arthur Vance.")
    if lead_quality < 20:
        risks.append("Lead pipeline quality degrading — review FMCSA targeting criteria with Alexander.")
    if not risks:
        risks.append("No critical strategic risks identified — maintain execution velocity")

    return {
        "strategist": "CC Gulley",
        "title": "Chief Strategy Officer",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "situation": {
            "total_carriers": total_carriers,
            "active_carriers": active_carriers,
            "activation_rate_pct": activation_rate,
            "total_leads": total_leads,
            "qualified_leads": qualified_leads,
            "lead_quality_pct": lead_quality,
        },
        "priorities_30d": priorities_30d,
        "initiatives_60d": initiatives_60d,
        "vision_90d": vision_90d,
        "strategic_risks": risks,
        "commander_alignment": commander_dir.get("org_priority", "carrier_acquisition"),
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    result = strategic_plan()

    summary = (
        f"activation={result['situation']['activation_rate_pct']}% "
        f"lead_quality={result['situation']['lead_quality_pct']}% "
        f"risks={len(result['strategic_risks'])} "
        f"30d_priorities={len(result['priorities_30d'])}"
    )
    log_agent("cc_gulley", "strategic_plan", payload={}, result=summary)

    # Write strategic plan to org brain
    mem.remember(
        "cc_gulley", "strategic_plan",
        {
            "priorities_30d":    result["priorities_30d"],
            "initiatives_60d":   result["initiatives_60d"],
            "vision_90d":        result["vision_90d"],
            "strategic_risks":   result["strategic_risks"],
            "situation":         result["situation"],
        },
        confidence=0.85,
        source_agent="cc_gulley",
        summary=f"Strategic plan: {len(result['priorities_30d'])} priorities · {len(result['strategic_risks'])} risks",
    )
    mem.log_interaction(
        "cc_gulley", "org", "strategic_plan",
        payload={"alignment": result["commander_alignment"]},
        result={"priorities": len(result["priorities_30d"]), "risks": len(result["strategic_risks"])},
        outcome="success",
        outcome_notes=f"Activation={result['situation']['activation_rate_pct']}% · Leads={result['situation']['total_leads']}",
    )

    return {"agent": "cc_gulley", **result}
