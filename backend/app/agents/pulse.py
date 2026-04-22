"""Pulse — Step 40. Weekly fleet wellness check."""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase


def score_driver(driver_id: str) -> dict[str, Any]:
    """Scan recent HOS violations, speeding, idle. Stub returns shape."""
    sb = get_supabase()
    recent = (
        sb.table("driver_hos_status")
        .select("duty_status,violation_flags,ts")
        .eq("driver_id", driver_id)
        .order("ts", desc=True)
        .limit(200)
        .execute()
        .data or []
    )
    violations = sum(1 for r in recent if r.get("violation_flags"))
    wellness = max(0, 100 - violations * 5)
    return {"driver_id": driver_id, "wellness_score": wellness, "recent_violations": violations}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    driver_id = payload.get("driver_id", "")
    res = score_driver(driver_id) if driver_id else {"note": "pass driver_id"}
    log_agent("pulse", "wellness", payload={"driver_id": driver_id}, result=str(res.get("wellness_score")))
    return {"agent": "pulse", **res}
