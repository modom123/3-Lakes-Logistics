"""Fleet assets — powers the command center `Dispatch` page."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


@router.get("/")
def list_fleet(carrier_id: str | None = None, status: str | None = None) -> dict:
    q = get_supabase().table("fleet_assets").select("*").limit(1000)
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    if status:
        q = q.eq("status", status)
    res = q.execute()
    return {"count": len(res.data or []), "items": res.data or []}


@router.get("/{fleet_id}")
def get_fleet_asset(fleet_id: str) -> dict:
    res = get_supabase().table("fleet_assets").select("*").eq("id", fleet_id).maybe_single().execute()
    if not res.data:
        raise HTTPException(404, "fleet asset not found")
    return res.data


@router.patch("/{fleet_id}/status")
def set_status(fleet_id: str, new_status: str) -> dict:
    if new_status not in {"available", "on_load", "out_of_service", "maintenance"}:
        raise HTTPException(400, "invalid status")
    get_supabase().table("fleet_assets").update({"status": new_status}).eq("id", fleet_id).execute()
    return {"ok": True}
