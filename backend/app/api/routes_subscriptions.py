"""Subscription & plan management — Phase 6.

Routes:
  GET  /api/subscriptions/                      — list all carrier subscriptions
  GET  /api/subscriptions/{carrier_id}          — carrier's current plan + status
  POST /api/subscriptions/{carrier_id}/upgrade  — upgrade plan tier
  POST /api/subscriptions/{carrier_id}/downgrade
  POST /api/subscriptions/{carrier_id}/cancel
  POST /api/subscriptions/{carrier_id}/activate — mark carrier active (post-payment)
  GET  /api/subscriptions/kpis                  — MRR, churn, ARR, plan breakdown
  POST /api/subscriptions/webhook               — Stripe subscription webhook handler
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter()

# Plan tier definitions
_PLANS: dict[str, dict[str, Any]] = {
    "standard_5pct": {
        "label":        "5% Standard Dispatch",
        "dispatch_pct": 5,
        "monthly_min":  0,
        "features":     ["load_booking", "rate_conf", "basic_check_calls"],
    },
    "premium_8pct": {
        "label":        "8% Premium Dispatch",
        "dispatch_pct": 8,
        "monthly_min":  0,
        "features":     ["load_booking", "rate_conf", "check_calls_24_7",
                         "after_hours", "eld_monitoring"],
    },
    "full_service_10pct": {
        "label":        "10% Full-Service",
        "dispatch_pct": 10,
        "monthly_min":  0,
        "features":     ["load_booking", "rate_conf", "check_calls_24_7",
                         "after_hours", "eld_monitoring", "ifta_support",
                         "cdl_alerts", "compliance_suite", "settlement_ach"],
    },
    "enterprise": {
        "label":        "Enterprise Fleet",
        "dispatch_pct": 7,
        "monthly_min":  499,
        "features":     ["all"],
    },
}

_TIER_ORDER = ["standard_5pct", "premium_8pct", "full_service_10pct", "enterprise"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_subscription(carrier_id: str) -> dict | None:
    return (
        get_supabase()
        .table("carrier_subscriptions")
        .select("*")
        .eq("carrier_id", carrier_id)
        .maybe_single()
        .execute()
        .data
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", dependencies=[Depends(require_bearer)])
def list_subscriptions(status_filter: str | None = None, limit: int = 200) -> dict:
    q = (
        get_supabase()
        .table("carrier_subscriptions")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status_filter:
        q = q.eq("status", status_filter)
    items = q.execute().data or []
    return {"count": len(items), "items": items}


@router.get("/kpis", dependencies=[Depends(require_bearer)])
def subscription_kpis() -> dict:
    """MRR, ARR, active counts, churn rate, plan distribution."""
    sb = get_supabase()
    subs = sb.table("carrier_subscriptions").select("plan,status,monthly_min,dispatch_pct").execute().data or []

    active   = [s for s in subs if s.get("status") == "active"]
    churned  = [s for s in subs if s.get("status") == "cancelled"]
    trial    = [s for s in subs if s.get("status") == "trial"]

    mrr = sum(float(s.get("monthly_min") or 0) for s in active)
    arr = round(mrr * 12, 2)

    plan_dist: dict[str, int] = {}
    for s in active:
        plan_dist[s.get("plan", "unknown")] = plan_dist.get(s.get("plan", "unknown"), 0) + 1

    # Active carriers total revenue (dispatch fees from invoices MTD)
    month_start = date.today().replace(day=1).isoformat()
    inv_res = (
        sb.table("invoices")
        .select("dispatch_fee,status")
        .gte("invoice_date", month_start)
        .in_("status", ["Paid", "Unpaid", "Overdue"])
        .execute()
    )
    mtd_dispatch_fees = sum(float(i.get("dispatch_fee") or 0) for i in (inv_res.data or []))

    total = len(subs)
    churn_rate = round(len(churned) / total * 100, 1) if total else 0

    return {
        "as_of": date.today().isoformat(),
        "active_carriers": len(active),
        "trial_carriers":  len(trial),
        "churned_carriers": len(churned),
        "mrr":  round(mrr, 2),
        "arr":  arr,
        "churn_rate_pct": churn_rate,
        "mtd_dispatch_fees": round(mtd_dispatch_fees, 2),
        "plan_distribution": plan_dist,
        "plans_available": {k: v["label"] for k, v in _PLANS.items()},
    }


@router.get("/{carrier_id}", dependencies=[Depends(require_bearer)])
def get_subscription(carrier_id: str) -> dict:
    sub = _get_subscription(carrier_id)
    if not sub:
        raise HTTPException(404, "no subscription found for this carrier")
    plan_info = _PLANS.get(sub.get("plan", ""), {})
    return {**sub, "plan_details": plan_info}


@router.post("/{carrier_id}/activate", dependencies=[Depends(require_bearer)],
             status_code=status.HTTP_200_OK)
def activate_subscription(carrier_id: str, body: dict | None = None) -> dict:
    """Mark a carrier's subscription as active (called after first payment clears)."""
    body = body or {}
    sb = get_supabase()
    sub = _get_subscription(carrier_id)
    plan = body.get("plan") or (sub or {}).get("plan") or "standard_5pct"

    if sub:
        sb.table("carrier_subscriptions").update({
            "status": "active",
            "plan": plan,
            "activated_at": _now(),
            "stripe_subscription_id": body.get("stripe_subscription_id") or sub.get("stripe_subscription_id"),
        }).eq("carrier_id", carrier_id).execute()
    else:
        sb.table("carrier_subscriptions").insert({
            "carrier_id": carrier_id,
            "plan": plan,
            "status": "active",
            "dispatch_pct": _PLANS.get(plan, {}).get("dispatch_pct", 5),
            "monthly_min":  _PLANS.get(plan, {}).get("monthly_min", 0),
            "activated_at": _now(),
            "stripe_subscription_id": body.get("stripe_subscription_id"),
        }).execute()

    sb.table("active_carriers").update({"status": "active", "plan": plan}).eq("id", carrier_id).execute()
    log_agent("penny", "subscription_activated", carrier_id=carrier_id, payload={"plan": plan})
    return {"ok": True, "carrier_id": carrier_id, "plan": plan, "status": "active"}


@router.post("/{carrier_id}/upgrade", dependencies=[Depends(require_bearer)])
def upgrade_plan(carrier_id: str, body: dict) -> dict:
    new_plan = body.get("plan", "")
    if new_plan not in _PLANS:
        raise HTTPException(400, f"invalid plan — choose from: {list(_PLANS)}")
    sub = _get_subscription(carrier_id)
    if sub:
        current_tier = _TIER_ORDER.index(sub.get("plan", "standard_5pct")) if sub.get("plan") in _TIER_ORDER else 0
        new_tier     = _TIER_ORDER.index(new_plan)
        if new_tier <= current_tier:
            raise HTTPException(409, "use /downgrade to move to a lower plan")
    get_supabase().table("carrier_subscriptions").update({
        "plan":         new_plan,
        "dispatch_pct": _PLANS[new_plan]["dispatch_pct"],
        "monthly_min":  _PLANS[new_plan]["monthly_min"],
        "updated_at":   _now(),
    }).eq("carrier_id", carrier_id).execute()
    get_supabase().table("active_carriers").update({"plan": new_plan}).eq("id", carrier_id).execute()
    log_agent("penny", "plan_upgraded", carrier_id=carrier_id, payload={"plan": new_plan})
    return {"ok": True, "carrier_id": carrier_id, "plan": new_plan}


@router.post("/{carrier_id}/downgrade", dependencies=[Depends(require_bearer)])
def downgrade_plan(carrier_id: str, body: dict) -> dict:
    new_plan = body.get("plan", "")
    if new_plan not in _PLANS:
        raise HTTPException(400, f"invalid plan — choose from: {list(_PLANS)}")
    get_supabase().table("carrier_subscriptions").update({
        "plan":         new_plan,
        "dispatch_pct": _PLANS[new_plan]["dispatch_pct"],
        "monthly_min":  _PLANS[new_plan]["monthly_min"],
        "updated_at":   _now(),
    }).eq("carrier_id", carrier_id).execute()
    get_supabase().table("active_carriers").update({"plan": new_plan}).eq("id", carrier_id).execute()
    log_agent("penny", "plan_downgraded", carrier_id=carrier_id, payload={"plan": new_plan})
    return {"ok": True, "carrier_id": carrier_id, "plan": new_plan}


@router.post("/{carrier_id}/cancel", dependencies=[Depends(require_bearer)])
def cancel_subscription(carrier_id: str, body: dict | None = None) -> dict:
    body = body or {}
    reason = body.get("reason", "")
    get_supabase().table("carrier_subscriptions").update({
        "status":      "cancelled",
        "cancelled_at": _now(),
        "cancel_reason": reason,
    }).eq("carrier_id", carrier_id).execute()
    get_supabase().table("active_carriers").update({"status": "churned"}).eq("id", carrier_id).execute()
    log_agent("penny", "subscription_cancelled", carrier_id=carrier_id, payload={"reason": reason})
    return {"ok": True, "carrier_id": carrier_id, "status": "cancelled"}


@router.post("/webhook")
async def stripe_subscription_webhook(request: Request) -> dict:
    """Handle Stripe subscription lifecycle webhooks."""
    import hmac, hashlib
    s = get_settings()
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    if s.stripe_webhook_secret:
        try:
            import stripe as stripe_lib
            stripe_lib.api_key = s.stripe_secret_key
            event = stripe_lib.Webhook.construct_event(payload, sig, s.stripe_webhook_secret)
        except Exception:
            raise HTTPException(400, "invalid stripe signature")
        event_type = event["type"]
        data = event["data"]["object"]
    else:
        import json
        data = json.loads(payload)
        event_type = data.get("type", "")

    carrier_id = (data.get("metadata") or {}).get("carrier_id")

    if event_type == "customer.subscription.created":
        if carrier_id:
            activate_subscription(carrier_id, {
                "plan": (data.get("metadata") or {}).get("plan", "standard_5pct"),
                "stripe_subscription_id": data.get("id"),
            })

    elif event_type == "customer.subscription.deleted":
        if carrier_id:
            cancel_subscription(carrier_id, {"reason": "stripe_cancelled"})

    elif event_type == "invoice.payment_failed":
        if carrier_id:
            get_supabase().table("carrier_subscriptions").update({
                "status": "past_due", "updated_at": _now(),
            }).eq("carrier_id", carrier_id).execute()
            log_agent("penny", "payment_failed", carrier_id=carrier_id)

    return {"received": True, "event": event_type}
