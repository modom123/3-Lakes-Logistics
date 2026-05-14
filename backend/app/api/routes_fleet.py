"""Fleet assets — powers the EAGLE EYE `Dispatch` page."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..supabase_client import get_supabase
from .deps import require_bearer

router        = APIRouter(dependencies=[Depends(require_bearer)])
public_router = APIRouter()  # no auth — used by public carrier website


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


# ── Public endpoints (no auth) — used by carrier-facing website ───────────────

@public_router.get("/public/loads")
def public_loads(limit: int = 20) -> dict:
    """Return loads marked post_to_website=true. No auth required."""
    try:
        res = (
            get_supabase()
            .table("loads")
            .select("load_number,origin,destination,origin_city,origin_state,dest_city,dest_state,rate_total,miles,rate_per_mile,pickup_at,equipment_type,weight")
            .eq("post_to_website", True)
            .in_("status", ["booked", "open", "available"])
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return {"loads": res.data or [], "count": len(res.data or [])}
    except Exception:
        return {"loads": [], "count": 0}


@public_router.get("/public/stats")
def public_stats() -> dict:
    """Return live stats for the public site (founders joined, active trucks, loads posted)."""
    try:
        sb = get_supabase()
        carriers = sb.table("active_carriers").select("id", count="exact").execute()
        founders = sb.table("active_carriers").select("id", count="exact").eq("plan", "founders").execute()
        loads    = sb.table("loads").select("id", count="exact").eq("post_to_website", True).execute()
        return {
            "founders_joined":  getattr(founders,  "count", 0) or 0,
            "total_carriers":   getattr(carriers,  "count", 0) or 0,
            "loads_posted":     getattr(loads,     "count", 0) or 0,
        }
    except Exception:
        return {"founders_joined": 0, "total_carriers": 0, "loads_posted": 0}
