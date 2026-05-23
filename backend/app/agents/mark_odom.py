"""Mark Odom — CEO & Commander (IEBC Step 1).

Entrepreneurial executive and AI infrastructure founder. 30+ years across
financial services, sales, recruiting, and business development. Architect of
the IEBC Enterprise Hub — 50+ AI personas running autonomous business operations.

Daily run: reads all executive outputs from org brain, issues strategic
directives, monitors the 3 master scores, and surfaces Commander-level
decisions for the triage tier-3 queue.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from . import memory as mem


# Commander-level intelligence domains Mark reviews each morning
_INTEL_KEYS = [
    ("victoria",   "last_snapshot"),       # CGO growth metrics
    ("cc_gulley",  "strategic_plan"),       # CSO strategic initiatives
    ("alexander",  "fmcsa_intel"),          # Market intelligence
    ("naomi",      "lead_intel"),           # Lead pipeline health
    ("winston",    "churn_signals"),        # Carrier retention
    ("org",        "strategic_directive"),  # Org-wide directive
    ("sofia",      "ar_summary"),           # Financial health
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


def commander_brief() -> dict[str, Any]:
    """Reads all executive intel from org brain and produces a Commander-level brief."""
    sb = get_supabase()

    # Pull live metrics
    total_carriers = _safe_count("active_carriers")
    active_carriers = _safe_count("active_carriers", {"status": "active"})
    total_leads     = _safe_count("leads")
    open_tier3 = 0
    try:
        open_tier3 = (
            sb.table("triage_escalations")
            .select("id", count="exact")
            .eq("tier", 3)
            .in_("status", ["open", "in_review"])
            .execute()
            .count or 0
        )
    except Exception:
        pass

    # Pull all executive memories
    intel: dict[str, Any] = {}
    for agent_key, memory_key in _INTEL_KEYS:
        val = mem.recall_value(agent_key, memory_key)
        if val:
            intel[f"{agent_key}_{memory_key}"] = val

    # Strategic state of the company
    activation_rate = round(active_carriers / total_carriers * 100, 1) if total_carriers else 0
    growth_directive = mem.recall_value("org", "strategic_directive") or {}
    priority = growth_directive.get("priority", "carrier_acquisition")
    actions  = growth_directive.get("recommended_actions", [])

    # Commander decisions
    decisions: list[str] = []
    if open_tier3:
        decisions.append(f"IMMEDIATE: {open_tier3} Tier-3 escalation(s) require Commander review")
    if activation_rate < 60:
        decisions.append(f"GROWTH: Carrier activation at {activation_rate}% — accelerate Vance outreach")
    if total_leads > 50:
        decisions.append(f"PIPELINE: {total_leads} leads in system — ensure Isabella campaign is live")
    if not decisions:
        decisions.append("All systems nominal — hold course, monitor master scores")

    return {
        "commander": "Mark Odom",
        "title": "CEO — Commander",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fleet_metrics": {
            "total_carriers": total_carriers,
            "active_carriers": active_carriers,
            "activation_rate_pct": activation_rate,
            "total_leads": total_leads,
            "open_tier3_escalations": open_tier3,
        },
        "org_priority": priority,
        "recommended_actions": actions,
        "commander_decisions": decisions,
        "executive_intel": intel,
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    result = commander_brief()

    summary = (
        f"carriers={result['fleet_metrics']['total_carriers']} "
        f"activation={result['fleet_metrics']['activation_rate_pct']}% "
        f"tier3_open={result['fleet_metrics']['open_tier3_escalations']} "
        f"decisions={len(result['commander_decisions'])}"
    )
    log_agent("mark_odom", "commander_brief", payload={}, result=summary)

    # Write Commander directive to org brain
    mem.remember(
        "mark_odom", "commander_directive",
        {
            "decisions": result["commander_decisions"],
            "org_priority": result["org_priority"],
            "fleet_metrics": result["fleet_metrics"],
        },
        confidence=0.95,
        source_agent="mark_odom",
        summary=f"Commander brief: {result['org_priority']} · {len(result['commander_decisions'])} decisions",
    )
    mem.log_interaction(
        "mark_odom", "org", "commander_brief",
        payload={"priority": result["org_priority"]},
        result={"decisions": len(result["commander_decisions"])},
        outcome="success",
        outcome_notes=f"Activation={result['fleet_metrics']['activation_rate_pct']}% · Tier3={result['fleet_metrics']['open_tier3_escalations']}",
    )

    return {"agent": "mark_odom", **result}
