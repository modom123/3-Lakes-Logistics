"""Winston Carmichael — VP Client Success (IEBC Step 58).
Monitors carrier health and engagement. Flags at-risk carriers based
on load activity, onboarding status, and inactivity windows so the
team can intervene before churn.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from . import memory as mem
from . import carrier_brain as cb

# Days without a completed load before a carrier is flagged at-risk
_INACTIVITY_DAYS = 14
# Carriers with fewer than this many total loads are still in early engagement
_LOW_LOAD_THRESHOLD = 3


def assess_carriers() -> dict[str, Any]:
    sb = get_supabase()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_INACTIVITY_DAYS)).isoformat()

    carriers = (
        sb.table("active_carriers")
        .select("id,name,status,service_plan,fleet_size,created_at,updated_at")
        .limit(500)
        .execute()
        .data or []
    )

    loads = (
        sb.table("loads")
        .select("carrier_id,status,created_at")
        .in_("status", ["delivered", "closed", "paid", "in_transit", "dispatched"])
        .execute()
        .data or []
    )

    # Build load index per carrier
    load_idx: dict[str, list[dict]] = {}
    for ld in loads:
        cid = ld.get("carrier_id")
        if cid:
            load_idx.setdefault(cid, []).append(ld)

    at_risk: list[dict[str, Any]] = []
    healthy: int = 0
    never_loaded: list[str] = []

    for c in carriers:
        cid = c["id"]
        carrier_loads = load_idx.get(cid, [])
        load_count = len(carrier_loads)

        # Find most recent load date
        dates = [ld.get("created_at") for ld in carrier_loads if ld.get("created_at")]
        last_load_at = max(dates) if dates else None

        inactive = last_load_at is None or last_load_at < cutoff

        if load_count == 0:
            never_loaded.append(c.get("name") or cid)
            at_risk.append({
                "carrier_id": cid,
                "name": c.get("name"),
                "status": c.get("status"),
                "plan": c.get("service_plan"),
                "fleet_size": c.get("fleet_size"),
                "total_loads": 0,
                "last_load_at": None,
                "risk_reason": "Never completed a load — needs activation call",
                "priority": "high",
            })
        elif inactive and load_count < _LOW_LOAD_THRESHOLD:
            at_risk.append({
                "carrier_id": cid,
                "name": c.get("name"),
                "status": c.get("status"),
                "plan": c.get("service_plan"),
                "fleet_size": c.get("fleet_size"),
                "total_loads": load_count,
                "last_load_at": last_load_at,
                "risk_reason": f"Only {load_count} load(s) + inactive {_INACTIVITY_DAYS}+ days",
                "priority": "medium",
            })
        elif inactive:
            at_risk.append({
                "carrier_id": cid,
                "name": c.get("name"),
                "status": c.get("status"),
                "plan": c.get("service_plan"),
                "fleet_size": c.get("fleet_size"),
                "total_loads": load_count,
                "last_load_at": last_load_at,
                "risk_reason": f"No load activity in {_INACTIVITY_DAYS}+ days",
                "priority": "low",
            })
        else:
            healthy += 1

    at_risk.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}[x["priority"]])

    return {
        "carriers_assessed": len(carriers),
        "healthy_carriers": healthy,
        "at_risk_count": len(at_risk),
        "never_loaded_count": len(never_loaded),
        "at_risk_carriers": at_risk[:15],
        "retention_rate_pct": round(healthy / len(carriers) * 100, 1) if carriers else 0,
        "recommended_action": (
            "Deploy Vance calls + Isabella campaign to at-risk carriers"
            if len(at_risk) > 3 else "Carrier health nominal"
        ),
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    # Read CC Gulley's strategic plan and live directive — retention programs
    cso_plan = mem.recall_value("cc_gulley", "strategic_plan") or {}
    retention_focus = cso_plan.get("retention_priority", None)
    cso_directive = mem.recall_value("cc_gulley", "directive_to_winston") or {}
    if cso_directive:
        if cso_directive.get("retention_priority"):
            retention_focus = cso_directive["retention_priority"]
    # Read org-wide strategic directive — Victoria may have flagged retention as priority
    directive = mem.recall_value("org", "strategic_directive") or {}

    result = assess_carriers()
    log_agent(
        "winston", "retention_audit",
        payload={},
        result=f"at_risk={result['at_risk_count']} healthy={result['healthy_carriers']} retention={result['retention_rate_pct']}%",
    )

    # Write churn signals to org brain — Victoria and Isabella read this
    churn_data = {
        "at_risk_count":      result["at_risk_count"],
        "never_loaded_count": result["never_loaded_count"],
        "retention_rate_pct": result["retention_rate_pct"],
        "at_risk_names":      [c["name"] for c in result["at_risk_carriers"][:5] if c.get("name")],
        "high_priority":      [c for c in result["at_risk_carriers"] if c.get("priority") == "high"][:5],
    }
    mem.remember(
        "winston", "churn_signals",
        churn_data,
        confidence=0.75,
        summary=f"{result['at_risk_count']} at-risk carriers · {result['never_loaded_count']} never loaded · retention={result['retention_rate_pct']}%",
    )
    mem.remember(
        "org", "retention_health",
        {"retention_rate_pct": result["retention_rate_pct"], "at_risk_count": result["at_risk_count"]},
        confidence=0.75,
        source_agent="winston",
        summary=f"Retention {result['retention_rate_pct']}% · {result['at_risk_count']} at risk",
    )
    # Write each at-risk carrier into Carrier Brain for relationship-level tracking
    for carrier in result["at_risk_carriers"][:20]:
        cid = carrier.get("carrier_id")
        if not cid:
            continue
        cb.remember_carrier(
            cid,
            carrier.get("name"),
            "risk_profile",
            {
                "priority":     carrier["priority"],
                "risk_reason":  carrier["risk_reason"],
                "total_loads":  carrier["total_loads"],
                "last_load_at": carrier["last_load_at"],
                "plan":         carrier.get("plan"),
                "fleet_size":   carrier.get("fleet_size"),
            },
            agent="winston",
            confidence={"high": 0.85, "medium": 0.70, "low": 0.55}.get(carrier["priority"], 0.6),
            summary=f"{carrier['priority'].upper()} risk — {carrier['risk_reason']}",
        )

    if result["at_risk_count"] > 0:
        mem.log_interaction("winston", "isabella", "handoff",
            payload={"at_risk_count": result["at_risk_count"]},
            result={"churn_signals_written": True},
            outcome="success",
            outcome_notes=f"Isabella should run retention campaign for {result['at_risk_count']} at-risk carriers",
        )
    mem.log_interaction("winston", "cc_gulley", "report",
        payload={"retention_focus": retention_focus},
        result={"at_risk": result["at_risk_count"], "retention_rate_pct": result["retention_rate_pct"]},
        outcome="success",
        outcome_notes=f"Retention audit complete · directive applied: {bool(cso_directive)}",
    )
    if cso_directive:
        result["cso_directive"] = cso_directive.get("instruction", "")
        result["cso_directive_focus"] = cso_directive.get("focus", "")
    return {"agent": "winston", **result}
