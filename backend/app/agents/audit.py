"""Audit — Step 32. Credit-check gate for fuel advances + factoring."""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase


_MAX_ADVANCE_PCT = 0.40   # advance must be ≤ 40% of load rate
_MIN_FLOOR_USD   = 500.0  # floor regardless of rate (for small loads)
_MAX_OUTSTANDING = 1      # driver may not have more than 1 open advance


def _outstanding_advances(driver_id: str) -> int:
    """Count fuel advances approved but not yet deducted from a settlement."""
    sb = get_supabase()
    res = (
        sb.table("agent_log")
        .select("id")
        .eq("agent", "audit")
        .eq("action", "advance_decision")
        .eq("payload->>driver_id", driver_id)
        .eq("result", "approved")
        .execute()
    )
    approved_count = len(res.data or [])

    # Subtract advances already settled (appear in settler logs)
    settled_res = (
        sb.table("agent_log")
        .select("id,payload")
        .eq("agent", "settler")
        .eq("action", "run")
        .execute()
    )
    settled_count = sum(
        1 for r in (settled_res.data or [])
        if (r.get("payload") or {}).get("driver_id") == driver_id
        and float((r.get("payload") or {}).get("fuel_advances", 0)) > 0
    )
    return max(0, approved_count - settled_count)


def _active_load_exists(driver_id: str) -> bool:
    """Driver must have an active dispatched/in-transit load to get an advance."""
    sb = get_supabase()
    res = (
        sb.table("loads")
        .select("id")
        .eq("driver_code", driver_id)
        .in_("status", ["dispatched", "in_transit"])
        .limit(1)
        .execute()
    )
    return bool(res.data)


def decide_advance(driver_id: str, amount: float, load_rate: float) -> dict[str, Any]:
    """Approve or deny a fuel advance request.

    Rules:
      1. Driver must have an active load (dispatched or in_transit)
      2. Amount ≤ max(40% of load rate, $500 floor)
      3. No more than 1 outstanding (unsettled) advance per driver
    """
    cap = max(load_rate * _MAX_ADVANCE_PCT, _MIN_FLOOR_USD)

    if not _active_load_exists(driver_id):
        return {
            "driver_id": driver_id,
            "amount": amount,
            "approved": False,
            "reason": "no_active_load — must have a dispatched or in-transit load",
        }

    if amount > cap:
        return {
            "driver_id": driver_id,
            "amount": amount,
            "approved": False,
            "reason": f"exceeds 40% cap (max ${cap:.2f} on ${load_rate:.2f} load)",
        }

    outstanding = _outstanding_advances(driver_id)
    if outstanding >= _MAX_OUTSTANDING:
        return {
            "driver_id": driver_id,
            "amount": amount,
            "approved": False,
            "reason": f"{outstanding} outstanding advance(s) — must settle before requesting another",
        }

    return {
        "driver_id": driver_id,
        "amount": amount,
        "approved": True,
        "reason": f"within 40% cap (${cap:.2f}) and {outstanding} outstanding advances",
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    res = decide_advance(
        payload.get("driver_id", ""),
        float(payload.get("amount") or 0),
        float(payload.get("load_rate") or 0),
    )
    log_agent(
        "audit", "advance_decision",
        payload={**payload, "driver_id": payload.get("driver_id")},
        result="approved" if res["approved"] else "denied",
    )
    return {"agent": "audit", **res}
