"""Penny — Steps 17, 29-30. Stripe subscription lifecycle."""
from __future__ import annotations

from typing import Any

import stripe

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase


def _sk() -> str:
    s = get_settings().stripe_secret_key
    if not s:
        raise RuntimeError("STRIPE_SECRET_KEY not set")
    stripe.api_key = s
    return s


def create_checkout_session(carrier_id: str, plan: str, email: str) -> str | None:
    """Step 17: after intake we hand the carrier a Stripe checkout URL."""
    s = get_settings()
    if not s.stripe_secret_key or not s.stripe_price_founders:
        log_agent("penny", "checkout", carrier_id=carrier_id, error="stripe_not_configured")
        return None
    try:
        _sk()
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=email,
            line_items=[{"price": s.stripe_price_founders, "quantity": 1}],
            success_url="https://3lakeslogistics.com/welcome?cid=" + carrier_id,
            cancel_url="https://3lakeslogistics.com/?cid=" + carrier_id,
            metadata={"carrier_id": carrier_id, "plan": plan},
        )
        get_supabase().table("active_carriers").update(
            {"stripe_customer_id": session.customer or None}
        ).eq("id", carrier_id).execute()
        log_agent("penny", "checkout_created", carrier_id=carrier_id, result=session.id)
        return session.url
    except Exception as e:  # noqa: BLE001
        log_agent("penny", "checkout", carrier_id=carrier_id, error=str(e))
        return None


def verify_and_parse(payload: bytes, sig: str | None) -> dict[str, Any]:
    _sk()
    secret = get_settings().stripe_webhook_secret
    if not secret or not sig:
        raise ValueError("webhook signature not configured")
    event = stripe.Webhook.construct_event(payload, sig, secret)
    return event


def handle_event(event: dict[str, Any]) -> None:
    """Steps 29-30: invoice.paid → activate; invoice.payment_failed → suspend."""
    etype = event.get("type")
    data = event.get("data", {}).get("object", {})
    carrier_id = (data.get("metadata") or {}).get("carrier_id")
    sb = get_supabase()

    if etype == "checkout.session.completed" and carrier_id:
        sb.table("active_carriers").update({
            "subscription_status": "active",
            "stripe_subscription_id": data.get("subscription"),
            "status": "active",
            "onboarded_at": "now()",
        }).eq("id", carrier_id).execute()
        log_agent("penny", "activated", carrier_id=carrier_id, result=etype)

    elif etype == "invoice.payment_failed" and carrier_id:
        sb.table("active_carriers").update({
            "subscription_status": "past_due", "status": "suspended",
        }).eq("id", carrier_id).execute()
        log_agent("penny", "suspended", carrier_id=carrier_id, result=etype)

    elif etype == "customer.subscription.deleted" and carrier_id:
        sb.table("active_carriers").update({
            "subscription_status": "canceled", "status": "churned",
        }).eq("id", carrier_id).execute()


def run(payload: dict[str, Any]) -> dict[str, Any]:  # noqa: C901
    action = payload.get("action", "margin_preview")
    carrier_id = payload.get("carrier_id", "")

    # ── Stripe checkout ────────────────────────────────────────────────────────
    if action == "checkout":
        plan = payload.get("plan", "standard_5pct")
        email = payload.get("email", "")
        url = create_checkout_session(carrier_id, plan, email)
        return {"agent": "penny", "action": action, "checkout_url": url, "ok": bool(url)}

    # ── Stripe event handler ───────────────────────────────────────────────────
    if action == "handle_event":
        event = payload.get("event", payload)
        handle_event(event)
        log_agent("penny", "event_handled", carrier_id=carrier_id)
        return {"agent": "penny", "action": action, "ok": True}

    # ── Pre-dispatch margin preview ────────────────────────────────────────────
    if action == "margin_preview":
        rate = float(payload.get("rate_total", 0))
        fuel_est = float(payload.get("miles", 0)) * 0.55
        driver_pay = rate * 0.72
        margin = rate - driver_pay - fuel_est
        result = {
            "gross": rate, "driver_pay": driver_pay,
            "fuel_est": fuel_est, "margin": margin,
            "margin_pct": margin / max(rate, 1),
        }
        log_agent("penny", "margin_preview", carrier_id=carrier_id, result=result)
        return {"agent": "penny", "action": action, **result, "ok": True}

    # ── Fuel cost tracking ─────────────────────────────────────────────────────
    if action == "fuel_cost_track":
        load_id = payload.get("load_id", "")
        sb = get_supabase()
        rows = (sb.table("fuel_card_transactions").select("amount")
                  .eq("load_id", load_id).execute().data or []) if load_id else []
        total_fuel = sum(float(r.get("amount") or 0) for r in rows)
        log_agent("penny", "fuel_cost_track", carrier_id=carrier_id,
                  result={"load_id": load_id, "total_fuel": total_fuel})
        return {"agent": "penny", "action": action,
                "load_id": load_id, "total_fuel": total_fuel, "ok": True}

    # ── Final load margin ──────────────────────────────────────────────────────
    if action == "load_margin":
        load_id = payload.get("load_id", "")
        sb = get_supabase()
        load = (sb.table("loads").select("rate_total,miles")
                  .eq("id", load_id).maybe_single().execute().data or {}) if load_id else {}
        rate = float(load.get("rate_total") or payload.get("rate_total", 0))
        miles = float(load.get("miles") or payload.get("miles", 0))

        pay_rows = (sb.table("driver_settlements").select("driver_pay")
                      .eq("load_id", load_id).execute().data or []) if load_id else []
        driver_pay = sum(float(r.get("driver_pay") or 0) for r in pay_rows) or rate * 0.72

        fuel_rows = (sb.table("fuel_card_transactions").select("amount")
                       .eq("load_id", load_id).execute().data or []) if load_id else []
        fuel_cost = sum(float(r.get("amount") or 0) for r in fuel_rows) or miles * 0.55

        dispatch_pct = float(payload.get("dispatch_pct", 5))
        dispatch_fee = rate * dispatch_pct / 100
        margin = rate - driver_pay - fuel_cost - dispatch_fee
        result = {
            "gross": rate, "driver_pay": driver_pay, "fuel_cost": fuel_cost,
            "dispatch_fee": dispatch_fee, "margin": margin,
            "margin_pct": margin / max(rate, 1),
        }
        log_agent("penny", "load_margin", carrier_id=carrier_id, result=result)
        return {"agent": "penny", "action": action, **result, "ok": True}

    # ── MTD KPI update ─────────────────────────────────────────────────────────
    if action == "update_mtd_kpis":
        from datetime import date
        month_start = date.today().replace(day=1).isoformat()
        sb = get_supabase()
        inv_rows = (
            sb.table("invoices").select("total_amount,dispatch_fee,status")
              .eq("carrier_id", carrier_id).gte("invoice_date", month_start)
              .execute().data or []
        ) if carrier_id else []
        mtd_gross = sum(float(r.get("total_amount") or 0) for r in inv_rows)
        mtd_dispatch = sum(float(r.get("dispatch_fee") or 0) for r in inv_rows)
        load_rows = (
            sb.table("loads").select("rate_total,miles")
              .eq("carrier_id", carrier_id).gte("created_at", month_start)
              .execute().data or []
        ) if carrier_id else []
        total_miles = sum(float(r.get("miles") or 0) for r in load_rows)
        rpm = round(mtd_gross / max(total_miles, 1), 4)
        if carrier_id:
            sb.table("active_carriers").update({
                "mtd_gross": mtd_gross,
                "mtd_dispatch_fees": mtd_dispatch,
            }).eq("id", carrier_id).execute()
        result = {"mtd_gross": mtd_gross, "mtd_dispatch": mtd_dispatch,
                  "total_miles": total_miles, "rpm": rpm}
        log_agent("penny", "update_mtd_kpis", carrier_id=carrier_id, result=result)
        return {"agent": "penny", "action": action, **result, "ok": True}

    log_agent("penny", "unknown_action", carrier_id=carrier_id, payload=payload)
    return {"agent": "penny", "action": action, "ok": False, "note": "unknown action"}
