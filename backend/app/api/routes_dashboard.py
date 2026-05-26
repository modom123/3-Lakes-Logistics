"""Dashboard aggregates — powers the EAGLE EYE home page KPI tiles."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

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


@router.get("/loads")
def list_loads(limit: int = 500, status: str | None = None) -> dict:
    sb = get_supabase()
    q = sb.table("loads").select("*").order("created_at", desc=True).limit(limit)
    if status:
        q = q.eq("status", status)
    res = q.execute()
    return {"count": len(res.data or []), "items": res.data or []}


@router.get("/invoices")
def list_invoices(limit: int = 500, status: str | None = None) -> dict:
    sb = get_supabase()
    q = sb.table("invoices").select("*").order("created_at", desc=True).limit(limit)
    if status:
        q = q.eq("status", status)
    res = q.execute()
    return {"count": len(res.data or []), "items": res.data or []}


@router.post("/loads")
def create_load(payload: dict) -> dict:
    res = get_supabase().table("loads").insert(payload).execute()
    return {"ok": True, "item": res.data[0] if res.data else {}}


@router.patch("/loads/{load_id}")
def update_load(load_id: str, payload: dict) -> dict:
    get_supabase().table("loads").update(payload).eq("id", load_id).execute()
    return {"ok": True}


@router.post("/invoices")
def create_invoice(payload: dict) -> dict:
    res = get_supabase().table("invoices").insert(payload).execute()
    return {"ok": True, "item": res.data[0] if res.data else {}}


@router.patch("/invoices/{invoice_id}")
def update_invoice(invoice_id: str, payload: dict) -> dict:
    get_supabase().table("invoices").update(payload).eq("id", invoice_id).execute()
    return {"ok": True}


@router.delete("/invoices/{invoice_id}")
def delete_invoice(invoice_id: str) -> dict:
    get_supabase().table("invoices").delete().eq("id", invoice_id).execute()
    return {"ok": True}


@router.get("/weekly-pl")
def weekly_pl(weeks: int = 8) -> dict:
    """Weekly P&L summary: gross revenue, dispatch fees, fuel, net margin."""
    sb = get_supabase()
    today = date.today()
    days_since_friday = (today.weekday() - 4) % 7
    last_friday = today - timedelta(days=days_since_friday)

    result = []
    for i in range(weeks):
        week_end = last_friday - timedelta(weeks=i)
        week_start = week_end - timedelta(days=6)
        we_str = week_end.isoformat()
        ws_str = week_start.isoformat()

        # Loads created in this week
        loads = (
            sb.table("loads")
            .select("rate_total,status")
            .gte("created_at", ws_str)
            .lte("created_at", we_str + "T23:59:59")
            .execute()
            .data or []
        )
        gross = sum(float(r.get("rate_total") or 0) for r in loads)

        # Settlements for this week_ending
        settlements = (
            sb.table("driver_settlements")
            .select("gross_pay,dispatch_fee,net_pay,status")
            .eq("week_ending", we_str)
            .execute()
            .data or []
        )
        dispatch_fees = sum(float(r.get("dispatch_fee") or 0) for r in settlements)
        net_to_carriers = sum(float(r.get("net_pay") or 0) for r in settlements)

        # Fuel spend for this week
        fuel = (
            sb.table("fuel_transactions")
            .select("amount")
            .gte("transacted_at", ws_str)
            .lte("transacted_at", we_str + "T23:59:59")
            .execute()
            .data or []
        )
        fuel_cost = sum(float(r.get("amount") or 0) for r in fuel)

        # Invoices collected this week
        invoices = (
            sb.table("invoices")
            .select("amount,status")
            .gte("created_at", ws_str)
            .lte("created_at", we_str + "T23:59:59")
            .execute()
            .data or []
        )
        collected = sum(float(r.get("amount") or 0) for r in invoices if r.get("status") == "Paid")
        outstanding = sum(float(r.get("amount") or 0) for r in invoices if r.get("status") in ("Unpaid", "Overdue"))

        operating_profit = round(dispatch_fees - fuel_cost, 2)

        result.append({
            "week_ending": we_str,
            "week_start": ws_str,
            "loads": len(loads),
            "gross_revenue": round(gross, 2),
            "dispatch_fees": round(dispatch_fees, 2),
            "net_to_carriers": round(net_to_carriers, 2),
            "fuel_cost": round(fuel_cost, 2),
            "operating_profit": operating_profit,
            "ar_collected": round(collected, 2),
            "ar_outstanding": round(outstanding, 2),
        })

    totals = {
        "gross_revenue": round(sum(w["gross_revenue"] for w in result), 2),
        "dispatch_fees": round(sum(w["dispatch_fees"] for w in result), 2),
        "fuel_cost": round(sum(w["fuel_cost"] for w in result), 2),
        "operating_profit": round(sum(w["operating_profit"] for w in result), 2),
        "ar_collected": round(sum(w["ar_collected"] for w in result), 2),
    }

    return {"weeks": result, "totals": totals}
