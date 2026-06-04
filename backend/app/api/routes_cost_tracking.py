"""Cost Tracking API — IEBC team dashboard for system cost visibility.

Routes:
  GET  /api/costs/summary         — MTD cost summary (API + subscriptions)
  GET  /api/costs/entries         — paginated cost entry log
  POST /api/costs/entries         — manual cost entry
  GET  /api/costs/subscriptions   — subscription list
  POST /api/costs/subscriptions   — add/update subscription
  GET  /api/costs/budgets         — budget list
  POST /api/costs/budgets         — set budget for a service/category
  GET  /api/costs/alerts          — live budget alerts
  GET  /api/costs/reports         — past report records
  POST /api/costs/reports/send    — generate and email report now
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
