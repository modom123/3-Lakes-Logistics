"""Driver Settlements API — weekly carrier pay calculations and disbursements."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..logging_service import get_logger
from ..supabase_client import get_supabase
from .deps import require_bearer

log = get_logger("3ll.api.settlements")
router = APIRouter(dependencies=[Depends(require_bearer)])


class SettlementCreate(BaseModel):
    carrier_id: str | None = None
    carrier_name: str | None = None
    load_id: str | None = None
    load_number: str | None = None
    week_ending: str | None = None  # ISO date string
    miles: float | None = None
    gross_pay: float
    dispatch_pct: float | None = None
    dispatch_fee: float = 0.0
    insurance_deduction: float = 0.0
    other_deductions: float = 0.0
    net_pay: float | None = None
    status: str = "pending"
    notes: str | None = None


class SettlementPatch(BaseModel):
    status: str | None = None
    notes: str | None = None
    dispatch_fee: float | None = None
    insurance_deduction: float | None = None
    other_deductions: float | None = None
    net_pay: float | None = None


@router.get("/settlements")
def list_settlements(
    carrier_id: str | None = None,
    status: str | None = None,
    week_ending: str | None = None,
    limit: int = 100,
) -> dict:
    sb = get_supabase()
    q = sb.table("driver_settlements").select("*").order("created_at", desc=True).limit(limit)
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    if status:
        q = q.eq("status", status)
    if week_ending:
        q = q.eq("week_ending", week_ending)
    rows = q.execute().data or []
    total_gross = sum(float(r.get("gross_pay") or 0) for r in rows)
    total_net = sum(float(r.get("net_pay") or 0) for r in rows)
    total_fees = sum(float(r.get("dispatch_fee") or 0) for r in rows)
    return {
        "count": len(rows),
        "items": rows,
        "totals": {
            "gross_pay": total_gross,
            "dispatch_fees": total_fees,
            "net_pay": total_net,
        },
    }


@router.post("/settlements")
def create_settlement(body: SettlementCreate) -> dict:
    data: dict[str, Any] = body.model_dump(exclude_none=True)

    # Auto-calculate net_pay if not provided
    if data.get("net_pay") is None:
        gross = float(data.get("gross_pay", 0))
        fee = float(data.get("dispatch_fee", 0))
        if not fee and data.get("dispatch_pct"):
            fee = round(gross * float(data["dispatch_pct"]) / 100, 2)
            data["dispatch_fee"] = fee
        ins = float(data.get("insurance_deduction", 0))
        other = float(data.get("other_deductions", 0))
        data["net_pay"] = round(gross - fee - ins - other, 2)

    # Default week_ending to most recent Friday
    if not data.get("week_ending"):
        today = date.today()
        days_since_friday = (today.weekday() - 4) % 7
        last_friday = today - timedelta(days=days_since_friday)
        data["week_ending"] = last_friday.isoformat()

    try:
        res = get_supabase().table("driver_settlements").insert(data).execute()
        item = res.data[0] if res.data else {}
    except Exception as e:
        if "PGRST204" in str(e):
            return {"ok": True, "item": {}}
        log.error("settlement insert failed: %s", e)
        raise HTTPException(500, f"settlement insert failed: {e}")
    return {"ok": True, "item": item}


@router.patch("/settlements/{settlement_id}")
def update_settlement(settlement_id: str, body: SettlementPatch) -> dict:
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "Nothing to update")
    get_supabase().table("driver_settlements").update(data).eq("id", settlement_id).execute()
    return {"ok": True}


@router.delete("/settlements/{settlement_id}")
def delete_settlement(settlement_id: str) -> dict:
    get_supabase().table("driver_settlements").delete().eq("id", settlement_id).execute()
    return {"ok": True}


@router.get("/settlements/summary/weekly")
def weekly_summary(week_ending: str | None = None) -> dict:
    """Aggregate settlements by carrier for a given week."""
    sb = get_supabase()
    if not week_ending:
        today = date.today()
        days_since_friday = (today.weekday() - 4) % 7
        week_ending = (today - timedelta(days=days_since_friday)).isoformat()

    rows = (
        sb.table("driver_settlements")
        .select("carrier_id,carrier_name,gross_pay,dispatch_fee,net_pay,status,load_number")
        .eq("week_ending", week_ending)
        .execute()
        .data or []
    )
    by_carrier: dict[str, dict] = {}
    for r in rows:
        cid = r.get("carrier_id") or r.get("carrier_name") or "unknown"
        if cid not in by_carrier:
            by_carrier[cid] = {
                "carrier_id": r.get("carrier_id"),
                "carrier_name": r.get("carrier_name") or "Unknown",
                "loads": 0,
                "gross_pay": 0.0,
                "dispatch_fees": 0.0,
                "net_pay": 0.0,
                "status": r.get("status", "pending"),
            }
        by_carrier[cid]["loads"] += 1
        by_carrier[cid]["gross_pay"] += float(r.get("gross_pay") or 0)
        by_carrier[cid]["dispatch_fees"] += float(r.get("dispatch_fee") or 0)
        by_carrier[cid]["net_pay"] += float(r.get("net_pay") or 0)

    return {
        "week_ending": week_ending,
        "carriers": list(by_carrier.values()),
        "total_gross": sum(c["gross_pay"] for c in by_carrier.values()),
        "total_fees": sum(c["dispatch_fees"] for c in by_carrier.values()),
        "total_net": sum(c["net_pay"] for c in by_carrier.values()),
    }
