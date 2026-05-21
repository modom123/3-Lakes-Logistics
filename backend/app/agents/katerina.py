"""Katerina Rostova — Head of Process Automation (IEBC Step 53 / agent).
Audits active loads for SLA violations and stalled workflows.
Maps each bottleneck to the corrective automation step and returns
a prioritized remediation list for the Commander.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase

# Maximum hours a load may sit in each status before it's flagged
_SLA_HOURS: dict[str, int] = {
    "booked":     2,
    "dispatched": 4,
    "in_transit": 48,
    "delivered":  6,
}

# Corrective step mapped to each stalled status
_REMEDIATION: dict[str, str] = {
    "booked":     "Step 12 — Confirm driver assignment; re-issue BOL via Scout",
    "dispatched": "Step 17 — Contact driver for pickup ETA via Echo (SMS)",
    "in_transit": "Step 28 — Request GPS check-in via Orbit geofence alert",
    "delivered":  "Step 33 — Upload POD via Scout; trigger invoice via Penny",
}


def audit_sla() -> dict[str, Any]:
    sb = get_supabase()
    loads = (
        sb.table("loads")
        .select("id,load_number,status,updated_at,carrier_id")
        .in_("status", list(_SLA_HOURS.keys()))
        .execute()
        .data or []
    )

    now = datetime.now(timezone.utc)
    violations: list[dict[str, Any]] = []

    for ld in loads:
        raw = ld.get("updated_at") or ""
        if not raw:
            continue
        try:
            updated = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        elapsed_h = (now - updated).total_seconds() / 3600
        sla = _SLA_HOURS[ld["status"]]
        if elapsed_h > sla:
            violations.append({
                "load_number": ld.get("load_number"),
                "status": ld["status"],
                "elapsed_hours": round(elapsed_h, 1),
                "sla_hours": sla,
                "overage_hours": round(elapsed_h - sla, 1),
                "remediation": _REMEDIATION[ld["status"]],
            })

    violations.sort(key=lambda x: x["overage_hours"], reverse=True)
    critical = [v for v in violations if v["overage_hours"] > v["sla_hours"]]

    return {
        "loads_scanned": len(loads),
        "sla_violations": len(violations),
        "critical_violations": len(critical),
        "top_violations": violations[:10],
        "escalate_to_commander": len(critical) > 0,
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    result = audit_sla()
    log_agent(
        "katerina", "sla_audit",
        payload={},
        result=f"violations={result['sla_violations']} critical={result['critical_violations']}",
    )
    return {"agent": "katerina", **result}
