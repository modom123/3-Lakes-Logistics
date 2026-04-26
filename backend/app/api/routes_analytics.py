"""Analytics and reporting endpoints.

Routes:
  GET /api/analytics/revenue          — weekly/monthly revenue breakdown
  GET /api/analytics/carriers         — per-carrier performance metrics
  GET /api/analytics/drivers          — per-driver stats (miles, loads, pay)
  GET /api/analytics/loads            — load funnel: booked vs delivered vs invoiced
  GET /api/analytics/invoices         — invoice aging snapshot + collection rate
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends

from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


def _week_bounds(weeks_back: int = 0) -> tuple[str, str]:
    today = date.today()
    start = today - timedelta(days=today.weekday() + 7 * weeks_back)
    end = start + timedelta(days=6)
    return start.isoformat(), end.isoformat()


# ── Revenue ───────────────────────────────────────────────────────────────────

@router.get("/revenue")
def revenue_analytics(weeks: int = 8) -> dict:
    """Weekly revenue for the last N weeks from closed loads."""
    sb = get_supabase()
    today = date.today()
    start = (today - timedelta(weeks=weeks)).isoformat()

    loads_res = (
        sb.table("loads")
        .select("rate_total,delivery_at,status,carrier_id")
        .in_("status", ["delivered", "closed"])
        .gte("delivery_at", start)
        .execute()
    )
    loads = loads_res.data or []

    inv_res = (
        sb.table("invoices")
        .select("amount,dispatch_fee,status,invoice_date")
        .gte("invoice_date", start)
        .execute()
    )
    invoices = inv_res.data or []

    # Build weekly buckets
    weekly: dict[str, dict] = {}
    for load in loads:
        if not load.get("delivery_at"):
            continue
        wk = _week_label(load["delivery_at"][:10])
        b = weekly.setdefault(wk, {"week": wk, "loads": 0, "gross_revenue": 0.0, "dispatch_fees": 0.0, "invoiced": 0.0, "collected": 0.0})
        b["loads"] += 1
        b["gross_revenue"] = round(b["gross_revenue"] + float(load.get("rate_total") or 0), 2)

    for inv in invoices:
        if not inv.get("invoice_date"):
            continue
        wk = _week_label(inv["invoice_date"])
        b = weekly.setdefault(wk, {"week": wk, "loads": 0, "gross_revenue": 0.0, "dispatch_fees": 0.0, "invoiced": 0.0, "collected": 0.0})
        b["invoiced"] = round(b["invoiced"] + float(inv.get("amount") or 0), 2)
        b["dispatch_fees"] = round(b["dispatch_fees"] + float(inv.get("dispatch_fee") or 0), 2)
        if inv.get("status") == "Paid":
            b["collected"] = round(b["collected"] + float(inv.get("amount") or 0), 2)

    buckets = sorted(weekly.values(), key=lambda x: x["week"])
    total_revenue = sum(b["gross_revenue"] for b in buckets)
    total_collected = sum(b["collected"] for b in buckets)

    return {
        "period_weeks": weeks,
        "total_gross_revenue": round(total_revenue, 2),
        "total_collected": round(total_collected, 2),
        "collection_rate_pct": round(total_collected / total_revenue * 100, 1) if total_revenue else 0,
        "weekly": buckets,
    }


def _week_label(date_str: str) -> str:
    d = date.fromisoformat(date_str[:10])
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat()


# ── Carrier Performance ───────────────────────────────────────────────────────

@router.get("/carriers")
def carrier_performance(weeks: int = 4) -> dict:
    """Per-carrier: loads delivered, revenue, miles, on-time rate."""
    sb = get_supabase()
    today = date.today()
    start = (today - timedelta(weeks=weeks)).isoformat()

    loads_res = (
        sb.table("loads")
        .select("carrier_id,rate_total,miles,status,delivery_at,scheduled_delivery")
        .in_("status", ["delivered", "closed"])
        .gte("delivery_at", start)
        .execute()
    )
    loads = loads_res.data or []

    carriers_res = (
        sb.table("active_carriers")
        .select("id,carrier_name,mc_number,dot_number")
        .execute()
    )
    carrier_map = {c["id"]: c for c in (carriers_res.data or [])}

    stats: dict[str, dict] = {}
    for load in loads:
        cid = load.get("carrier_id") or "unknown"
        s = stats.setdefault(cid, {
            "carrier_id": cid,
            "carrier_name": carrier_map.get(cid, {}).get("carrier_name", "Unknown"),
            "loads_delivered": 0,
            "total_revenue": 0.0,
            "total_miles": 0,
            "on_time_count": 0,
        })
        s["loads_delivered"] += 1
        s["total_revenue"] = round(s["total_revenue"] + float(load.get("rate_total") or 0), 2)
        s["total_miles"] += int(load.get("miles") or 0)

        if load.get("delivery_at") and load.get("scheduled_delivery"):
            if load["delivery_at"][:10] <= load["scheduled_delivery"][:10]:
                s["on_time_count"] += 1

    for s in stats.values():
        n = s["loads_delivered"]
        s["on_time_pct"] = round(s["on_time_count"] / n * 100, 1) if n else 0
        s["avg_revenue_per_load"] = round(s["total_revenue"] / n, 2) if n else 0
        s["avg_rpm"] = round(s["total_revenue"] / s["total_miles"], 3) if s["total_miles"] else 0

    ranked = sorted(stats.values(), key=lambda x: x["total_revenue"], reverse=True)
    return {"period_weeks": weeks, "carrier_count": len(ranked), "carriers": ranked}


# ── Driver Stats ──────────────────────────────────────────────────────────────

@router.get("/drivers")
def driver_stats(weeks: int = 4, carrier_id: str | None = None) -> dict:
    """Per-driver: loads, miles, gross pay, avg RPM."""
    sb = get_supabase()
    today = date.today()
    start = (today - timedelta(weeks=weeks)).isoformat()

    q = (
        sb.table("loads")
        .select("driver_id,driver_name,carrier_id,rate_total,miles,status,delivery_at")
        .in_("status", ["delivered", "closed"])
        .gte("delivery_at", start)
    )
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)

    loads = q.execute().data or []

    stats: dict[str, dict] = {}
    for load in loads:
        did = load.get("driver_id") or "unknown"
        s = stats.setdefault(did, {
            "driver_id": did,
            "driver_name": load.get("driver_name", "Unknown"),
            "carrier_id": load.get("carrier_id"),
            "loads_delivered": 0,
            "total_miles": 0,
            "gross_rate_total": 0.0,
        })
        s["loads_delivered"] += 1
        s["total_miles"] += int(load.get("miles") or 0)
        s["gross_rate_total"] = round(s["gross_rate_total"] + float(load.get("rate_total") or 0), 2)

    for s in stats.values():
        s["driver_gross_pay"] = round(s["gross_rate_total"] * 0.72, 2)
        s["avg_rpm"] = round(s["gross_rate_total"] / s["total_miles"], 3) if s["total_miles"] else 0

    ranked = sorted(stats.values(), key=lambda x: x["total_miles"], reverse=True)
    return {"period_weeks": weeks, "driver_count": len(ranked), "drivers": ranked}


# ── Load Funnel ───────────────────────────────────────────────────────────────

@router.get("/loads")
def load_funnel(days: int = 30) -> dict:
    """Load count by status for the last N days."""
    sb = get_supabase()
    start = (date.today() - timedelta(days=days)).isoformat()

    res = (
        sb.table("loads")
        .select("status,rate_total")
        .gte("created_at", start)
        .execute()
    )
    loads = res.data or []

    funnel: dict[str, dict] = {}
    for load in loads:
        st = load.get("status", "unknown")
        b = funnel.setdefault(st, {"status": st, "count": 0, "total_value": 0.0})
        b["count"] += 1
        b["total_value"] = round(b["total_value"] + float(load.get("rate_total") or 0), 2)

    ordered_statuses = ["available", "offered", "booked", "dispatched", "in_transit", "delivered", "closed", "cancelled"]
    ordered = [funnel[s] for s in ordered_statuses if s in funnel]
    ordered += [v for k, v in funnel.items() if k not in ordered_statuses]

    total = sum(b["count"] for b in ordered)
    return {
        "period_days": days,
        "total_loads": total,
        "funnel": ordered,
    }


# ── Invoice Snapshot ──────────────────────────────────────────────────────────

@router.get("/invoices")
def invoice_snapshot() -> dict:
    """Live A/R snapshot: total outstanding, overdue, collection rate MTD."""
    sb = get_supabase()
    today = date.today()
    month_start = date(today.year, today.month, 1).isoformat()

    all_res = (
        sb.table("invoices")
        .select("amount,status,due_date,invoice_date")
        .execute()
    )
    all_inv = all_res.data or []

    total_outstanding = sum(float(i.get("amount") or 0) for i in all_inv if i.get("status") in ("Unpaid", "Overdue"))
    total_overdue = sum(float(i.get("amount") or 0) for i in all_inv if i.get("status") == "Overdue")

    mtd = [i for i in all_inv if (i.get("invoice_date") or "") >= month_start]
    mtd_billed = sum(float(i.get("amount") or 0) for i in mtd)
    mtd_collected = sum(float(i.get("amount") or 0) for i in mtd if i.get("status") == "Paid")

    overdue_30 = sum(
        float(i.get("amount") or 0)
        for i in all_inv
        if i.get("due_date") and i.get("status") in ("Unpaid", "Overdue")
        and (today - date.fromisoformat(i["due_date"])).days > 30
    )

    return {
        "as_of": today.isoformat(),
        "total_outstanding": round(total_outstanding, 2),
        "total_overdue": round(total_overdue, 2),
        "overdue_30_plus": round(overdue_30, 2),
        "mtd_billed": round(mtd_billed, 2),
        "mtd_collected": round(mtd_collected, 2),
        "mtd_collection_rate_pct": round(mtd_collected / mtd_billed * 100, 1) if mtd_billed else 0,
    }
