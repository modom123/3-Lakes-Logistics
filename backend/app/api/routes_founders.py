"""Founders inventory — read by index (7).html's countdown table and the
command center `Subscriptions` page. Public GET, bearer-guarded writes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter()


@router.get("/inventory")
def inventory() -> dict:
    res = get_supabase().table("founders_inventory").select("*").execute()
    items = res.data or []
    total = sum(r["total"] for r in items)
    claimed = sum(r["claimed"] for r in items)
    return {
        "total": total,
        "claimed": claimed,
        "remaining": total - claimed,
        "categories": items,
    }


@router.post("/reset", dependencies=[Depends(require_bearer)])
def reset_claims() -> dict:
    get_supabase().table("founders_inventory").update({"claimed": 0}).neq("category", "").execute()
    return {"ok": True}
