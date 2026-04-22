"""Dashboard aggregates — powers the command center home page KPI tiles."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


def _mtd_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


@router.get("/kpis")
def kpis() -> dict:
    sb = get_supabase()
    mtd = _mtd_iso()

    carriers = sb.table("active_carriers").select("id,status", count="exact").execute()
    active = sb.table("active_carriers").select("id", count="exact").eq("status", "active").execute()
    loads = sb.table("loads").select("id,rate_total,rate_per_mile", count="exact").gte("created_at", mtd).execute()
    unpaid = sb.table("invoices").select("amount", count="exact").eq("status", "Unpaid").execute()

    gross_mtd = sum((r.get("rate_total") or 0) for r in (loads.data or []))
    rpms = [r.get("rate_per_mile") for r in (loads.data or []) if r.get("rate_per_mile")]
    avg_rpm = round(sum(rpms) / len(rpms), 2) if rpms else 0
    unpaid_total = sum((r.get("amount") or 0) for r in (unpaid.data or []))

    return {
        "total_carriers": carriers.count or 0,
        "active_carriers": active.count or 0,
        "mtd_loads": loads.count or 0,
        "mtd_gross": float(gross_mtd),
        "avg_rpm": float(avg_rpm),
        "mtd_dispatch_fees": float(gross_mtd) * 0.10,  # 10% full-service
        "unpaid_invoices": unpaid.count or 0,
        "unpaid_total": float(unpaid_total),
    }


@router.get("/recent-loads")
def recent_loads(limit: int = 10) -> dict:
    res = (
        get_supabase()
        .table("loads")
        .select("id,broker_name,load_number,origin_city,origin_state,dest_city,dest_state,rate_total,status,created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"items": res.data or []}
