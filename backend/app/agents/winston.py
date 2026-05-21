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
    result = assess_carriers()
    log_agent(
        "winston", "retention_audit",
        payload={},
        result=f"at_risk={result['at_risk_count']} healthy={result['healthy_carriers']} retention={result['retention_rate_pct']}%",
    )
    return {"agent": "winston", **result}
