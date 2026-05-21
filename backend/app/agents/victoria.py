"""Victoria Roth — Chief Strategy Officer (IEBC Step 54).
Pulls real-time business metrics and produces a strategic intelligence
snapshot: growth trajectory, plan mix health, and top 3 recommended
macro actions for the Commander. Daily task to be refined.
"""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from . import memory as mem


def _safe_count(table: str, filters: dict | None = None) -> int:
    try:
        sb = get_supabase()
        q = sb.table(table).select("id", count="exact")
        if filters:
            for k, v in filters.items():
                q = q.eq(k, v)
        res = q.execute()
        return res.count or 0
    except Exception:
        return 0


def strategic_snapshot() -> dict[str, Any]:
    sb = get_supabase()

    total_carriers = _safe_count("active_carriers")
    active_carriers = _safe_count("active_carriers", {"status": "active"})
    total_loads = _safe_count("loads")
    open_loads = _safe_count("loads", {"status": "in_transit"})
    total_leads = _safe_count("leads")
    new_leads = _safe_count("leads", {"status": "New"})

    # Revenue snapshot from loads
    try:
        rev_rows = (
            sb.table("loads")
            .select("rate")
            .in_("status", ["delivered", "closed", "paid"])
            .limit(500)
            .execute()
            .data or []
        )
        total_rev = sum(float(r.get("rate") or 0) for r in rev_rows)
    except Exception:
        total_rev = 0.0

    activation_rate = round(active_carriers / total_carriers * 100, 1) if total_carriers else 0
    lead_conversion = round((total_carriers / total_leads * 100), 1) if total_leads else 0

    # Strategic signal
    signals: list[str] = []
    if activation_rate < 60:
        signals.append(f"Carrier activation below 60% ({activation_rate}%) — run onboarding push")
    if new_leads > 20:
        signals.append(f"{new_leads} untouched leads in pipeline — deploy Vance + Isabella")
    if open_loads > total_carriers * 2:
        signals.append("Load demand outpacing fleet — accelerate carrier acquisition")
    if not signals:
        signals.append("All metrics nominal — focus on geographic lane expansion")

    return {
        "total_carriers": total_carriers,
        "active_carriers": active_carriers,
        "activation_rate_pct": activation_rate,
        "total_loads": total_loads,
        "open_loads": open_loads,
        "total_leads": total_leads,
        "new_leads_untouched": new_leads,
        "lead_to_carrier_conversion_pct": lead_conversion,
        "total_revenue_closed": round(total_rev, 2),
        "strategic_signals": signals,
        "recommended_actions": signals[:3],
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    # Read the full org brain before forming strategy
    org_intel = mem.read_org_intelligence()

    result = strategic_snapshot()

    # Enrich with org brain insights
    lead_intel  = mem.recall_value("org", "lead_intelligence") or {}
    market_intel = mem.recall_value("org", "market_intel") or {}
    at_risk_data = mem.recall_value("winston", "churn_signals") or {}

    result["org_brain"] = {
        "agents_with_memory":  org_intel.get("agents_with_memory", 0),
        "total_memories":      org_intel.get("total_memories", 0),
        "recent_interactions": org_intel.get("recent_interactions", 0),
        "top_state_from_alexander": market_intel.get("top_state"),
        "tier_a_leads_from_naomi":  lead_intel.get("tier_a_count"),
        "at_risk_carriers_from_winston": at_risk_data.get("at_risk_count"),
    }

    summary = f"carriers={result['total_carriers']} activation={result['activation_rate_pct']}% signals={len(result['strategic_signals'])}"
    log_agent("victoria", "strategic_snapshot", payload={}, result=summary)

    # Write strategic directive to org brain — all agents read this
    directive = {
        "priority":          "carrier_acquisition" if result["activation_rate_pct"] < 60 else "load_growth",
        "hot_states":        market_intel.get("hot_states", {}),
        "tier_a_leads":      lead_intel.get("tier_a_count", 0),
        "at_risk_carriers":  at_risk_data.get("at_risk_count", 0),
        "recommended_actions": result["recommended_actions"],
    }
    mem.remember(
        "org", "strategic_directive",
        directive,
        confidence=0.8,
        source_agent="victoria",
        summary=f"Priority: {directive['priority']} · {len(result['recommended_actions'])} actions · activation={result['activation_rate_pct']}%",
    )
    mem.remember(
        "victoria", "last_snapshot",
        {k: v for k, v in result.items() if k != "org_brain"},
        confidence=0.7,
        summary=f"Strategic snapshot: {result['total_carriers']} carriers, {result['total_loads']} loads",
    )
    mem.log_interaction("victoria", "org", "directive",
        payload={"directive_priority": directive["priority"]},
        result={"actions_written": len(result["recommended_actions"])},
        outcome="success",
        outcome_notes=f"Activation={result['activation_rate_pct']}% · Tier A={lead_intel.get('tier_a_count','?')}",
    )
    return {"agent": "victoria", **result}
