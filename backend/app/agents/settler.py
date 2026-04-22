"""Settler — Step 31. Weekly driver payout calculator."""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase


def calc_driver_payout(driver_id: str, week_start: str, week_end: str) -> dict[str, Any]:
    """Gross (sum of delivered load rates) − fuel advances − factoring fees − deductions.

    Returns a breakdown dict for the carrier/driver statement.
    """
    sb = get_supabase()
    loads = (
        sb.table("loads")
        .select("id,rate_total")
        .eq("driver_code", driver_id)
        .eq("status", "delivered")
        .gte("delivery_at", week_start)
        .lte("delivery_at", week_end)
        .execute()
    )
    gross = sum((r.get("rate_total") or 0) for r in (loads.data or []))
    # TODO: wire fuel-card + factoring deductions
    advances = 0.0
    factoring = 0.0
    deductions = 0.0
    net = float(gross) - advances - factoring - deductions
    return {
        "driver_id": driver_id, "week": [week_start, week_end],
        "gross": float(gross), "advances": advances, "factoring": factoring,
        "deductions": deductions, "net": net, "loads": len(loads.data or []),
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    log_agent("settler", "run", payload=payload, result="stub")
    return {"agent": "settler", "status": "stub",
            "note": "TODO: ACH via banking_accounts + Stripe Treasury"}
