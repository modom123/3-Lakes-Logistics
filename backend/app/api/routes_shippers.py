"""Shippers / Customer CRM API — manage shipper and broker relationships."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..logging_service import get_logger
from ..supabase_client import get_supabase
from .deps import require_bearer

log = get_logger("3ll.api.shippers")
router = APIRouter(dependencies=[Depends(require_bearer)])


class ShipperCreate(BaseModel):
    company_name: str
    shipper_type: str = "shipper"  # shipper | broker | both
    status: str = "active"
    mc_number: str | None = None
    dot_number: str | None = None
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    payment_terms: str | None = None
    credit_limit: float | None = None
    notes: str | None = None


class ShipperPatch(BaseModel):
    company_name: str | None = None
    shipper_type: str | None = None
    status: str | None = None
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    payment_terms: str | None = None
    credit_limit: float | None = None
    notes: str | None = None


@router.get("/shippers")
def list_shippers(
    status: str | None = None,
    shipper_type: str | None = None,
    search: str | None = None,
    limit: int = 200,
) -> dict:
    sb = get_supabase()
    q = (
        sb.table("shippers")
        .select("*")
        .order("company_name")
        .limit(limit)
    )
    if status:
        q = q.eq("status", status)
    if shipper_type:
        q = q.eq("shipper_type", shipper_type)
    rows = q.execute().data or []
    if search:
        search_lower = search.lower()
        rows = [
            r for r in rows
            if search_lower in (r.get("company_name") or "").lower()
            or search_lower in (r.get("contact_name") or "").lower()
            or search_lower in (r.get("email") or "").lower()
        ]
    return {"count": len(rows), "items": rows}


@router.get("/shippers/{shipper_id}")
def get_shipper(shipper_id: str) -> dict:
    result = get_supabase().table("shippers").select("*").eq("id", shipper_id).maybe_single().execute()
    if not result.data:
        raise HTTPException(404, f"Shipper {shipper_id} not found")
    return result.data


@router.post("/shippers")
def create_shipper(body: ShipperCreate) -> dict:
    data = body.model_dump(exclude_none=True)
    try:
        res = get_supabase().table("shippers").insert(data).execute()
        item = res.data[0] if res.data else {}
    except Exception as e:
        if "PGRST204" in str(e):
            return {"ok": True, "item": {}}
        log.error("shipper insert failed: %s", e)
        raise HTTPException(500, f"shipper insert failed: {e}")
    return {"ok": True, "item": item}


@router.patch("/shippers/{shipper_id}")
def update_shipper(shipper_id: str, body: ShipperPatch) -> dict:
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "Nothing to update")
    get_supabase().table("shippers").update(data).eq("id", shipper_id).execute()
    return {"ok": True}


@router.delete("/shippers/{shipper_id}")
def delete_shipper(shipper_id: str) -> dict:
    get_supabase().table("shippers").delete().eq("id", shipper_id).execute()
    return {"ok": True}


@router.get("/shippers/search/top")
def top_shippers(limit: int = 10) -> dict:
    """Top shippers by total_revenue for relationship prioritization."""
    rows = (
        get_supabase()
        .table("shippers")
        .select("id,company_name,contact_name,email,total_loads,total_revenue,status")
        .order("total_revenue", desc=True)
        .limit(limit)
        .execute()
        .data or []
    )
    return {"count": len(rows), "items": rows}
