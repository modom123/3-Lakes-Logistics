"""Victoria Roth — Chief Strategy Officer (IEBC Step 54).
Pulls real-time business metrics and produces a strategic intelligence
snapshot: growth trajectory, plan mix health, and top 3 recommended
macro actions for the Commander. Daily task to be refined.
"""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase


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
    result = strategic_snapshot()
    summary = f"carriers={result['total_carriers']} activation={result['activation_rate_pct']}% signals={len(result['strategic_signals'])}"
    log_agent("victoria", "strategic_snapshot", payload={}, result=summary)
    return {"agent": "victoria", **result}
