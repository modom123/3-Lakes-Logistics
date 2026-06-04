"""Cost Tracking API — IEBC team dashboard for system cost visibility.

Routes:
  GET  /api/costs/summary         — MTD cost summary (API + subscriptions)
  GET  /api/costs/projection      — end-of-month cost projection
  GET  /api/costs/trend           — daily cost for last N days
  GET  /api/costs/by-agent        — per-AI-agent cost breakdown
  GET  /api/costs/entries         — paginated cost entry log
  POST /api/costs/entries         — manual cost entry
  GET  /api/costs/export          — CSV download of cost entries
  GET  /api/costs/subscriptions   — subscription list
  POST /api/costs/subscriptions   — add/update subscription
  GET  /api/costs/budgets         — budget list
  POST /api/costs/budgets         — set budget for a service/category
  GET  /api/costs/alerts          — live budget alerts
  GET  /api/costs/reports         — past report records
  POST /api/costs/reports/send    — generate and email report now
"""
from __future__ import annotations

import calendar
import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..supabase_client import get_supabase
from ..cost_tracking.reporter import get_mtd_summary, get_budget_alerts, send_report
from ..cost_tracking.tracker import track
from ..logging_service import get_logger
from .deps import require_bearer

log = get_logger("3ll.costs")
router = APIRouter(dependencies=[Depends(require_bearer)])


# ── Pydantic models ───────────────────────────────────────────────────────────

class CostEntryCreate(BaseModel):
    service: str
    category: str
    cost_usd: float
    units: float | None = None
    unit_type: str | None = None
    description: str | None = None
    metadata: dict[str, Any] | None = None


class SubscriptionUpsert(BaseModel):
    service: str
    plan_name: str | None = None
    billing_cycle: str = "monthly"
    amount_usd: float
    next_billing_date: str | None = None
    active: bool = True
    notes: str | None = None


class BudgetUpsert(BaseModel):
    service: str | None = None
    category: str | None = None
    monthly_budget_usd: float
    alert_threshold_pct: int = 80


# ── Summary / MTD ─────────────────────────────────────────────────────────────

@router.get("/summary")
def cost_summary() -> dict:
    """Month-to-date cost summary broken down by service and category."""
    return get_mtd_summary()


@router.get("/alerts")
def cost_alerts() -> dict:
    """Live budget alerts for services approaching or over their monthly caps."""
    alerts = get_budget_alerts()
    return {
        "alerts": alerts,
        "critical_count": sum(1 for a in alerts if a["severity"] == "critical"),
        "warning_count": sum(1 for a in alerts if a["severity"] == "warning"),
    }


# ── Cost entries ──────────────────────────────────────────────────────────────

@router.get("/entries")
def list_cost_entries(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    service: str | None = None,
    category: str | None = None,
) -> dict:
    sb = get_supabase()
    q = (
        sb.table("cost_entries")
        .select("*")
        .order("recorded_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if service:
        q = q.eq("service", service)
    if category:
        q = q.eq("category", category)
    res = q.execute()
    return {"count": len(res.data or []), "items": res.data or []}


@router.post("/entries", status_code=status.HTTP_201_CREATED)
def create_cost_entry(payload: CostEntryCreate) -> dict:
    """Manually record a cost entry (e.g. for services without auto-tracking)."""
    track(
        payload.service,
        payload.category,
        payload.cost_usd,
        units=payload.units,
        unit_type=payload.unit_type,
        description=payload.description,
        metadata=payload.metadata,
    )
    return {"ok": True}


# ── Subscriptions ─────────────────────────────────────────────────────────────

@router.get("/subscriptions")
def list_subscriptions() -> dict:
    sb = get_supabase()
    res = sb.table("cost_subscriptions").select("*").order("service").execute()
    items = res.data or []
    total = sum(float(s.get("amount_usd") or 0) for s in items if s.get("active"))
    return {"count": len(items), "monthly_total_usd": round(total, 2), "items": items}


@router.post("/subscriptions", status_code=status.HTTP_201_CREATED)
def upsert_subscription(payload: SubscriptionUpsert) -> dict:
    """Add or replace a subscription record for a service."""
    sb = get_supabase()
    existing = (
        sb.table("cost_subscriptions")
        .select("id")
        .eq("service", payload.service)
        .limit(1)
        .execute()
        .data or []
    )
    row = {
        "service": payload.service,
        "plan_name": payload.plan_name,
        "billing_cycle": payload.billing_cycle,
        "amount_usd": payload.amount_usd,
        "next_billing_date": payload.next_billing_date,
        "active": payload.active,
        "notes": payload.notes,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing:
        sb.table("cost_subscriptions").update(row).eq("id", existing[0]["id"]).execute()
        return {"ok": True, "action": "updated"}
    sb.table("cost_subscriptions").insert(row).execute()
    return {"ok": True, "action": "created"}


@router.delete("/subscriptions/{service}")
def deactivate_subscription(service: str) -> dict:
    get_supabase().table("cost_subscriptions").update({"active": False}).eq("service", service).execute()
    return {"ok": True, "service": service, "active": False}


# ── Budgets ───────────────────────────────────────────────────────────────────

@router.get("/budgets")
def list_budgets() -> dict:
    sb = get_supabase()
    res = sb.table("cost_budgets").select("*").eq("active", True).order("service").execute()
    return {"count": len(res.data or []), "items": res.data or []}


@router.post("/budgets", status_code=status.HTTP_201_CREATED)
def upsert_budget(payload: BudgetUpsert) -> dict:
    """Set a monthly budget cap for a service or category."""
    if not payload.service and not payload.category:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "service or category required")
    sb = get_supabase()
    q = sb.table("cost_budgets").select("id")
    if payload.service:
        q = q.eq("service", payload.service)
    elif payload.category:
        q = q.eq("category", payload.category)
    existing = q.limit(1).execute().data or []
    row = {
        "service": payload.service,
        "category": payload.category,
        "monthly_budget_usd": payload.monthly_budget_usd,
        "alert_threshold_pct": payload.alert_threshold_pct,
        "active": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing:
        sb.table("cost_budgets").update(row).eq("id", existing[0]["id"]).execute()
        return {"ok": True, "action": "updated"}
    sb.table("cost_budgets").insert(row).execute()
    return {"ok": True, "action": "created"}


@router.delete("/budgets/{budget_id}")
def delete_budget(budget_id: str) -> dict:
    get_supabase().table("cost_budgets").update({"active": False}).eq("id", budget_id).execute()
    return {"ok": True, "budget_id": budget_id, "active": False}


# ── Reports ───────────────────────────────────────────────────────────────────

@router.get("/reports")
def list_reports(limit: int = Query(20, ge=1, le=100)) -> dict:
    sb = get_supabase()
    res = (
        sb.table("cost_reports")
        .select("id,report_period,report_type,total_cost_usd,sent_to,sent_at,created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"count": len(res.data or []), "items": res.data or []}


@router.post("/reports/send")
def send_cost_report(recipients: list[str] | None = None) -> dict:
    """Generate and immediately email a cost report to Mark Odom (and optional extra recipients)."""
    summary = get_mtd_summary()
    alerts = get_budget_alerts()
    period = datetime.now(timezone.utc).strftime("%Y-%m (Manual Run %b %d)")
    result = send_report(summary, alerts, period_label=period, recipients=recipients or None)
    return {"ok": result.get("sent", False), **result}


# ── Analytics endpoints ───────────────────────────────────────────────────────

@router.get("/projection")
def cost_projection() -> dict:
    """End-of-month cost projection based on current daily burn rate."""
    summary = get_mtd_summary()
    now = datetime.now(timezone.utc)
    days_elapsed = now.day
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    days_remaining = days_in_month - days_elapsed

    daily_rate = summary["api_cost_usd"] / max(days_elapsed, 1)
    projected_api = round(daily_rate * days_in_month, 4)
    projected_total = round(projected_api + summary["subscription_cost_usd"], 2)
    pct_month_elapsed = round(days_elapsed / days_in_month * 100, 1)

    return {
        "period": summary["period"],
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "days_in_month": days_in_month,
        "pct_month_elapsed": pct_month_elapsed,
        "api_mtd_usd": summary["api_cost_usd"],
        "daily_burn_rate_usd": round(daily_rate, 6),
        "projected_api_eom_usd": projected_api,
        "subscription_monthly_usd": summary["subscription_cost_usd"],
        "projected_total_eom_usd": projected_total,
    }


@router.get("/trend")
def cost_trend(days: int = Query(7, ge=1, le=30)) -> dict:
    """Daily cost breakdown for the last N days."""
    sb = get_supabase()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = (
        sb.table("cost_entries")
        .select("service,cost_usd,recorded_at")
        .gte("recorded_at", since)
        .order("recorded_at", desc=False)
        .execute()
        .data or []
    )

    daily: dict[str, dict] = {}
    for r in rows:
        day = r["recorded_at"][:10]
        if day not in daily:
            daily[day] = {"date": day, "cost_usd": 0.0, "entry_count": 0, "by_service": {}}
        amt = float(r.get("cost_usd") or 0)
        daily[day]["cost_usd"] = round(daily[day]["cost_usd"] + amt, 6)
        daily[day]["entry_count"] += 1
        svc = r.get("service", "unknown")
        daily[day]["by_service"][svc] = round(daily[day]["by_service"].get(svc, 0) + amt, 6)

    trend = sorted(daily.values(), key=lambda x: x["date"])
    return {"days": days, "trend": trend, "total_usd": round(sum(d["cost_usd"] for d in trend), 4)}


@router.get("/by-agent")
def cost_by_agent() -> dict:
    """API cost breakdown per AI agent (from metadata.agent field)."""
    sb = get_supabase()
    start, end = _mtd_iso_range()
    rows = (
        sb.table("cost_entries")
        .select("cost_usd,metadata,service")
        .gte("recorded_at", start)
        .lte("recorded_at", end)
        .execute()
        .data or []
    )

    by_agent: dict[str, dict] = {}
    for r in rows:
        meta = r.get("metadata") or {}
        agent = meta.get("agent") or "unattributed"
        amt = float(r.get("cost_usd") or 0)
        if agent not in by_agent:
            by_agent[agent] = {"agent": agent, "cost_usd": 0.0, "call_count": 0, "services": set()}
        by_agent[agent]["cost_usd"] = round(by_agent[agent]["cost_usd"] + amt, 6)
        by_agent[agent]["call_count"] += 1
        by_agent[agent]["services"].add(r.get("service", ""))

    result = sorted(
        [{"agent": v["agent"], "cost_usd": v["cost_usd"], "call_count": v["call_count"],
          "services": list(v["services"])} for v in by_agent.values()],
        key=lambda x: -x["cost_usd"],
    )
    return {
        "period": datetime.now(timezone.utc).strftime("%Y-%m"),
        "agents": result,
        "total_attributed_usd": round(sum(a["cost_usd"] for a in result if a["agent"] != "unattributed"), 4),
    }


@router.get("/export")
def export_csv(
    days: int = Query(30, ge=1, le=365),
) -> StreamingResponse:
    """Download cost entries as a CSV file."""
    sb = get_supabase()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = (
        sb.table("cost_entries")
        .select("recorded_at,service,category,cost_usd,units,unit_type,description")
        .gte("recorded_at", since)
        .order("recorded_at", desc=True)
        .limit(5000)
        .execute()
        .data or []
    )

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["recorded_at", "service", "category", "cost_usd", "units", "unit_type", "description"])
    w.writeheader()
    w.writerows(rows)
    buf.seek(0)

    filename = f"3ll-costs-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _mtd_iso_range() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day = calendar.monthrange(now.year, now.month)[1]
    end = now.replace(day=last_day, hour=23, minute=59, second=59)
    return start.isoformat(), end.isoformat()
