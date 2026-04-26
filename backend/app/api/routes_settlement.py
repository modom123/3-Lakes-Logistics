"""Settlement routes — preview and history for driver payouts."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..agents import settler
from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


@router.get("/preview")
def settlement_preview(
    driver_id: str,
    week_start: str,
    week_end: str,
    driver_pct: float = 0.72,
) -> dict:
    """Return a full settlement breakdown without initiating ACH.

    Used by the ops dashboard payout preview panel (Fridays).
    """
    if not all([driver_id, week_start, week_end]):
        raise HTTPException(400, "driver_id, week_start, week_end required")
    breakdown = settler.calc_driver_payout(driver_id, week_start, week_end, driver_pct)
    return {"ok": True, "preview": breakdown}


@router.post("/run")
def run_settlement(payload: dict) -> dict:
    """Execute a full settlement (calc + ACH initiation) for a driver."""
    result = settler.run(payload)
    if result.get("error"):
        raise HTTPException(400, result["error"])
    return result


@router.get("/history")
def settlement_history(
    driver_id: str | None = None,
    carrier_id: str | None = None,
    limit: int = 52,
) -> dict:
    """Return past settlement records from agent_log."""
    q = (
        get_supabase()
        .table("agent_log")
        .select("ts,carrier_id,payload,result")
        .eq("agent", "settler")
        .eq("action", "run")
        .order("ts", desc=True)
        .limit(limit)
    )
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    res = q.execute()
    rows = res.data or []

    if driver_id:
        rows = [r for r in rows if (r.get("payload") or {}).get("driver_id") == driver_id]

    return {"count": len(rows), "items": rows}
