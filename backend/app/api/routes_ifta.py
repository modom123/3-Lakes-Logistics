"""IFTA & Fuel Card API — quarterly filings and fuel transaction tracking."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..logging_service import get_logger
from ..supabase_client import get_supabase
from .deps import require_bearer

log = get_logger("3ll.api.ifta")
router = APIRouter(dependencies=[Depends(require_bearer)])


class FuelTxCreate(BaseModel):
    carrier_id: str | None = None
    truck_id: str | None = None
    load_id: str | None = None
    transaction_id: str | None = None
    amount: float | None = None
    gallons: float | None = None
    price_per_gal: float | None = None
    location: str | None = None
    lat: float | None = None
    lng: float | None = None
    card_number: str | None = None
    is_advance: bool = False
    flagged: bool = False
    flag_reason: str | None = None


class FuelTxPatch(BaseModel):
    flagged: bool | None = None
    flag_reason: str | None = None
    amount: float | None = None
    gallons: float | None = None


class IftaFilingCreate(BaseModel):
    carrier_id: str
    quarter: str          # e.g. "2025-Q1"
    due_date: str         # ISO date
    filed_date: str | None = None
    status: str = "pending"


class IftaFilingPatch(BaseModel):
    status: str | None = None
    filed_date: str | None = None


# ── Fuel transactions ────────────────────────────────────────────────────────

@router.get("/ifta/fuel")
def list_fuel(
    carrier_id: str | None = None,
    truck_id: str | None = None,
    flagged: bool | None = None,
    limit: int = 200,
) -> dict:
    q = (
        get_supabase()
        .table("fuel_transactions")
        .select("*")
        .order("transacted_at", desc=True)
        .limit(limit)
    )
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    if truck_id:
        q = q.eq("truck_id", truck_id)
    if flagged is not None:
        q = q.eq("flagged", flagged)
    rows = q.execute().data or []
    total_gallons = sum(float(r.get("gallons") or 0) for r in rows)
    total_amount = sum(float(r.get("amount") or 0) for r in rows)
    return {
        "count": len(rows),
        "items": rows,
        "totals": {"gallons": round(total_gallons, 2), "amount": round(total_amount, 2)},
    }


@router.post("/ifta/fuel")
def create_fuel_tx(body: FuelTxCreate) -> dict:
    data: dict[str, Any] = body.model_dump(exclude_none=True)
    if data.get("amount") is None and data.get("gallons") and data.get("price_per_gal"):
        data["amount"] = round(float(data["gallons"]) * float(data["price_per_gal"]), 2)
    try:
        res = get_supabase().table("fuel_transactions").insert(data).execute()
        item = res.data[0] if res.data else {}
    except Exception as e:
        if "PGRST204" in str(e):
            return {"ok": True, "item": {}}
        log.error("fuel_transactions insert failed: %s", e)
        raise HTTPException(500, f"fuel insert failed: {e}")
    return {"ok": True, "item": item}


@router.patch("/ifta/fuel/{tx_id}")
def patch_fuel_tx(tx_id: str, body: FuelTxPatch) -> dict:
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "Nothing to update")
    get_supabase().table("fuel_transactions").update(data).eq("id", tx_id).execute()
    return {"ok": True}


@router.delete("/ifta/fuel/{tx_id}")
def delete_fuel_tx(tx_id: str) -> dict:
    get_supabase().table("fuel_transactions").delete().eq("id", tx_id).execute()
    return {"ok": True}


# ── IFTA filings ─────────────────────────────────────────────────────────────

@router.get("/ifta/filings")
def list_filings(
    carrier_id: str | None = None,
    status: str | None = None,
    quarter: str | None = None,
    limit: int = 100,
) -> dict:
    q = (
        get_supabase()
        .table("ifta_filings")
        .select("*")
        .order("due_date", desc=True)
        .limit(limit)
    )
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    if status:
        q = q.eq("status", status)
    if quarter:
        q = q.eq("quarter", quarter)
    rows = q.execute().data or []
    return {"count": len(rows), "items": rows}


@router.post("/ifta/filings")
def create_filing(body: IftaFilingCreate) -> dict:
    data = body.model_dump(exclude_none=True)
    try:
        res = get_supabase().table("ifta_filings").insert(data).execute()
        item = res.data[0] if res.data else {}
    except Exception as e:
        if "PGRST204" in str(e):
            return {"ok": True, "item": {}}
        log.error("ifta_filings insert failed: %s", e)
        raise HTTPException(500, f"filing insert failed: {e}")
    return {"ok": True, "item": item}


@router.patch("/ifta/filings/{filing_id}")
def patch_filing(filing_id: str, body: IftaFilingPatch) -> dict:
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "Nothing to update")
    get_supabase().table("ifta_filings").update(data).eq("id", filing_id).execute()
    return {"ok": True}


# ── Summary ──────────────────────────────────────────────────────────────────

@router.get("/ifta/summary")
def ifta_summary(carrier_id: str | None = None) -> dict:
    """Aggregate fuel consumption and filing status by quarter."""
    fuel_q = get_supabase().table("fuel_transactions").select("carrier_id,gallons,amount,transacted_at")
    if carrier_id:
        fuel_q = fuel_q.eq("carrier_id", carrier_id)
    fuel_rows = fuel_q.execute().data or []

    by_quarter: dict[str, dict] = {}
    for r in fuel_rows:
        ts = r.get("transacted_at") or ""
        if ts and len(ts) >= 7:
            month = int(ts[5:7])
            year = ts[:4]
            q_num = (month - 1) // 3 + 1
            key = f"{year}-Q{q_num}"
        else:
            key = "unknown"
        if key not in by_quarter:
            by_quarter[key] = {"quarter": key, "gallons": 0.0, "amount": 0.0, "tx_count": 0}
        by_quarter[key]["gallons"] += float(r.get("gallons") or 0)
        by_quarter[key]["amount"] += float(r.get("amount") or 0)
        by_quarter[key]["tx_count"] += 1

    for v in by_quarter.values():
        v["gallons"] = round(v["gallons"], 2)
        v["amount"] = round(v["amount"], 2)

    filings_q = get_supabase().table("ifta_filings").select("quarter,status,due_date,filed_date")
    if carrier_id:
        filings_q = filings_q.eq("carrier_id", carrier_id)
    filings = {r["quarter"]: r for r in (filings_q.execute().data or [])}

    quarters = sorted(set(list(by_quarter.keys()) + list(filings.keys())), reverse=True)
    result = []
    for q in quarters:
        fuel = by_quarter.get(q, {"gallons": 0.0, "amount": 0.0, "tx_count": 0})
        filing = filings.get(q)
        result.append({
            "quarter": q,
            "gallons": fuel["gallons"],
            "amount": fuel["amount"],
            "tx_count": fuel["tx_count"],
            "filing_status": filing["status"] if filing else None,
            "due_date": filing["due_date"] if filing else None,
            "filed_date": filing["filed_date"] if filing else None,
        })

    return {"quarters": result}
