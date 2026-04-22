"""Carriers CRUD — powers the command center `Carriers` page."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


@router.get("/")
def list_carriers(
    status_filter: str | None = Query(default=None, alias="status"),
    plan: str | None = None,
    limit: int = 200,
) -> dict:
    q = get_supabase().table("active_carriers").select("*").order("created_at", desc=True).limit(limit)
    if status_filter:
        q = q.eq("status", status_filter)
    if plan:
        q = q.eq("plan", plan)
    res = q.execute()
    return {"count": len(res.data or []), "items": res.data or []}


@router.get("/{carrier_id}")
def get_carrier(carrier_id: str) -> dict:
    res = get_supabase().table("active_carriers").select("*").eq("id", carrier_id).maybe_single().execute()
    if not res.data:
        raise HTTPException(404, "carrier not found")
    return res.data


@router.patch("/{carrier_id}/status")
def update_status(carrier_id: str, new_status: str) -> dict:
    if new_status not in {"onboarding", "active", "suspended", "churned"}:
        raise HTTPException(400, "invalid status")
    get_supabase().table("active_carriers").update({"status": new_status}).eq("id", carrier_id).execute()
    return {"ok": True, "carrier_id": carrier_id, "status": new_status}
