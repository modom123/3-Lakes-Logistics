"""Founders inventory + claim lifecycle (step 77).

Flow:
  POST /api/founders/reserve  (public) → creates a soft reserve, +1 reserved
  POST /api/founders/claim    (bearer) → marks paid, +1 claimed -1 reserved
  POST /api/founders/release  (bearer) → reverts a stale reserve
All writes are idempotent on `reservation_id`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..audit import record as audit_record
from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter()

RESERVATION_TTL_MIN = 30


@router.get("/inventory")
def inventory() -> dict:
    res = get_supabase().table("founders_inventory").select("*").execute()
    items = res.data or []
    total = sum(r.get("total") or 0 for r in items)
    claimed = sum(r.get("claimed") or 0 for r in items)
    reserved = sum(r.get("reserved") or 0 for r in items)
    return {
        "total": total, "claimed": claimed, "reserved": reserved,
        "remaining": max(0, total - claimed - reserved),
        "categories": items,
    }


@router.post("/reserve")
def reserve(payload: dict) -> dict:
    """Public soft-hold. Body: { reservation_id, category, email }."""
    rid = payload.get("reservation_id")
    category = payload.get("category")
    if not rid or not category:
        raise HTTPException(400, "reservation_id and category required")
    sb = get_supabase()
    existing = (
        sb.table("founders_reservations").select("id, status")
        .eq("id", rid).limit(1).execute().data or []
    )
    if existing:
        return {"status": "existing", "reservation": existing[0]}
    row = (
        sb.table("founders_inventory").select("*").eq("category", category).limit(1)
        .execute().data or []
    )
    if not row:
        raise HTTPException(404, f"unknown category {category}")
    inv = row[0]
    if (inv.get("total") or 0) - (inv.get("claimed") or 0) - (inv.get("reserved") or 0) <= 0:
        raise HTTPException(409, "category full")
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=RESERVATION_TTL_MIN)).isoformat()
    sb.table("founders_reservations").insert({
        "id": rid, "category": category, "email": payload.get("email"),
        "status": "reserved", "expires_at": expires_at,
    }).execute()
    sb.table("founders_inventory").update(
        {"reserved": (inv.get("reserved") or 0) + 1}
    ).eq("category", category).execute()
    audit_record(actor="public", action="founders.reserve",
                 entity="founders_reservations", entity_id=rid, meta={"category": category})
    return {"status": "reserved", "expires_at": expires_at}


@router.post("/claim", dependencies=[Depends(require_bearer)])
def claim(payload: dict) -> dict:
    """Convert reservation → claim (called after Stripe payment)."""
    rid = payload.get("reservation_id")
    carrier_id = payload.get("carrier_id")
    if not rid or not carrier_id:
        raise HTTPException(400, "reservation_id and carrier_id required")
    sb = get_supabase()
    rsv = (
        sb.table("founders_reservations").select("*").eq("id", rid).limit(1).execute().data
        or []
    )
    if not rsv:
        raise HTTPException(404, "no such reservation")
    res = rsv[0]
    if res.get("status") == "claimed":
        return {"status": "already_claimed"}
    cat = res["category"]
    inv = (sb.table("founders_inventory").select("*").eq("category", cat).execute().data or [{}])[0]
    sb.table("founders_inventory").update({
        "reserved": max(0, (inv.get("reserved") or 0) - 1),
        "claimed":  (inv.get("claimed") or 0) + 1,
    }).eq("category", cat).execute()
    sb.table("founders_reservations").update({
        "status": "claimed", "carrier_id": carrier_id,
        "claimed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", rid).execute()
    audit_record(actor="service", action="founders.claim",
                 entity="founders_reservations", entity_id=rid,
                 carrier_id=carrier_id, meta={"category": cat})
    return {"status": "claimed"}


@router.post("/release", dependencies=[Depends(require_bearer)])
def release(payload: dict) -> dict:
    rid = payload.get("reservation_id")
    sb = get_supabase()
    rsv = (
        sb.table("founders_reservations").select("*").eq("id", rid).limit(1).execute().data
        or []
    )
    if not rsv:
        raise HTTPException(404, "no such reservation")
    if rsv[0]["status"] != "reserved":
        return {"status": "noop"}
    cat = rsv[0]["category"]
    inv = (sb.table("founders_inventory").select("*").eq("category", cat).execute().data or [{}])[0]
    sb.table("founders_inventory").update(
        {"reserved": max(0, (inv.get("reserved") or 0) - 1)}
    ).eq("category", cat).execute()
    sb.table("founders_reservations").update({"status": "released"}).eq("id", rid).execute()
    return {"status": "released"}


@router.post("/reset", dependencies=[Depends(require_bearer)])
def reset_claims() -> dict:
    get_supabase().table("founders_inventory").update(
        {"claimed": 0, "reserved": 0}
    ).neq("category", "").execute()
    return {"ok": True}
