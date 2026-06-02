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


@router.get("/carrier/{carrier_id}")
def list_carrier_fleet(carrier_id: str) -> dict:
    """List all trucks for a carrier."""
    res = get_supabase().table("fleet_assets").select("*").eq("carrier_id", carrier_id).order("created_at").execute()
    return {"count": len(res.data or []), "items": res.data or []}


@router.get("/{fleet_id}")
def get_fleet_asset(fleet_id: str) -> dict:
    res = get_supabase().table("fleet_assets").select("*").eq("id", fleet_id).maybe_single().execute()
    if not res.data:
        raise HTTPException(404, "fleet asset not found")
    return res.data


@router.post("/")
def add_fleet_asset(payload: dict) -> dict:
    """Add a truck to a carrier's fleet."""
    carrier_id = payload.get("carrier_id")
    truck_id = payload.get("truck_id", "").strip()
    if not carrier_id:
        raise HTTPException(400, "carrier_id required")
    if not truck_id:
        raise HTTPException(400, "truck_id (unit number) required")
    # Prevent duplicate unit numbers per carrier
    existing = get_supabase().table("fleet_assets").select("id").eq("carrier_id", carrier_id).eq("truck_id", truck_id).execute()
    if existing.data:
        raise HTTPException(409, f"Unit {truck_id} already exists for this carrier")
    data = {
        "carrier_id": carrier_id,
        "truck_id": truck_id,
        "trailer_type": payload.get("trailer_type"),
        "year": payload.get("year"),
        "make": payload.get("make"),
        "model": payload.get("model"),
        "vin": payload.get("vin"),
        "max_weight_lbs": payload.get("max_weight_lbs"),
        "status": "available",
    }
    data = {k: v for k, v in data.items() if v is not None}
    res = get_supabase().table("fleet_assets").insert(data).execute()
    return {"ok": True, "item": res.data[0] if res.data else {}}


@router.delete("/{fleet_id}")
def delete_fleet_asset(fleet_id: str) -> dict:
    """Remove a truck from a carrier's fleet."""
    get_supabase().table("fleet_assets").delete().eq("id", fleet_id).execute()
    return {"ok": True}


@router.patch("/{fleet_id}/status")
def set_status(fleet_id: str, new_status: str) -> dict:
    if new_status not in {"available", "on_load", "out_of_service", "maintenance"}:
        raise HTTPException(400, "invalid status")
    get_supabase().table("fleet_assets").update({"status": new_status}).eq("id", fleet_id).execute()
    return {"ok": True}


# ── Public endpoints (no auth) — used by carrier-facing website ───────────────

@public_router.get("/public/loads")
def public_loads(limit: int = 50) -> dict:
    """Return loads marked post_to_website=true. No auth required."""
    try:
        # Status values used by Eagle Eye (mixed case) and legacy lowercase
        active_statuses = [
            "Booked", "booked",
            "Open", "open",
            "available", "Available",
            "En Route", "en_route",
        ]
        res = (
            get_supabase()
            .table("loads")
            .select(
                "load_number,origin,destination,origin_city,origin_state,"
                "dest_city,dest_state,rate_total,rate,miles,rate_per_mile,"
                "pickup_at,pickup_date,equipment_type,weight,weight_lbs,commodity"
            )
            .eq("post_to_website", True)
            .in_("status", active_statuses)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        # Normalise: merge rate/rate_total so website always has a rate field
        loads = []
        for l in (res.data or []):
            l["rate_total"] = l.get("rate_total") or l.get("rate") or 0
            l["pickup_at"] = l.get("pickup_at") or l.get("pickup_date")
            loads.append(l)
        return {"loads": loads, "count": len(loads)}
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
