"""Settler — weekly driver payout calculator and ACH initiator.

Flow:
  1. Pull all delivered loads for driver in the settlement window
  2. Sum gross pay at the carrier's configured driver % (default 72%)
  3. Subtract fuel advances, escrow deductions, cash advances
  4. Add lumper reimbursements and approved detention
  5. Initiate Stripe payout to driver's connected bank account
  6. Write settlement record + email statement via Nova
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import stripe

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase

# Default driver pay percentage of gross rate
_DEFAULT_DRIVER_PCT = 0.72
# Dispatch fee percentage (kept by 3 Lakes)
_DISPATCH_FEE_PCT = 0.08


def calc_driver_payout(
    driver_id: str,
    week_start: str,
    week_end: str,
    driver_pct: float = _DEFAULT_DRIVER_PCT,
) -> dict[str, Any]:
    """Build a full settlement breakdown for one driver over a date window."""
    sb = get_supabase()

    # ── 1. Delivered loads ────────────────────────────────────────────────────
    loads_res = (
        sb.table("loads")
        .select("id,load_number,rate_total,miles,origin_city,dest_city,delivery_at")
        .eq("driver_code", driver_id)
        .eq("status", "delivered")
        .gte("delivery_at", week_start)
        .lte("delivery_at", week_end)
        .execute()
    )
    loads = loads_res.data or []
    gross_rate = sum(float(r.get("rate_total") or 0) for r in loads)
    total_miles = sum(int(r.get("miles") or 0) for r in loads)

    # ── 2. Driver gross share ─────────────────────────────────────────────────
    driver_gross = round(gross_rate * driver_pct, 2)
    dispatch_fee = round(gross_rate * _DISPATCH_FEE_PCT, 2)

    # ── 3. Fuel advances (from agent_log) ────────────────────────────────────
    advances_res = (
        sb.table("agent_log")
        .select("payload")
        .eq("agent", "audit")
        .eq("action", "fuel_advance_approved")
        .ilike("payload->>carrier_id", f"%{driver_id}%")
        .gte("ts", week_start)
        .lte("ts", week_end)
        .execute()
    )
    fuel_advances = sum(
        float((r.get("payload") or {}).get("amount", 0))
        for r in (advances_res.data or [])
    )

    # ── 4. Escrow deduction (standard $50/wk for owner-ops) ──────────────────
    escrow_deduction = 50.0 if loads else 0.0

    # ── 5. Lumper reimbursements (from agent_log) ─────────────────────────────
    lumper_res = (
        sb.table("agent_log")
        .select("payload")
        .eq("agent", "transit")
        .eq("action", "lumper_approved")
        .ilike("payload->>driver_id", f"%{driver_id}%")
        .gte("ts", week_start)
        .lte("ts", week_end)
        .execute()
    )
    lumper_total = sum(
        float((r.get("payload") or {}).get("amount", 0))
        for r in (lumper_res.data or [])
    )

    # ── 6. Detention pay (from agent_log) ────────────────────────────────────
    detention_res = (
        sb.table("agent_log")
        .select("payload")
        .eq("agent", "transit")
        .eq("action", "detention_approved")
        .ilike("payload->>driver_id", f"%{driver_id}%")
        .gte("ts", week_start)
        .lte("ts", week_end)
        .execute()
    )
    detention_total = sum(
        float((r.get("payload") or {}).get("amount", 0))
        for r in (detention_res.data or [])
    )

    # ── 7. Net pay ───────────────────────────────────────────────────────────
    net_pay = round(
        driver_gross
        - fuel_advances
        - escrow_deduction
        + lumper_total
        + detention_total,
        2,
    )

    return {
        "driver_id": driver_id,
        "week": [week_start, week_end],
        "loads_delivered": len(loads),
        "total_miles": total_miles,
        "gross_rate": gross_rate,
        "driver_pct": driver_pct,
        "driver_gross": driver_gross,
        "dispatch_fee": dispatch_fee,
        "fuel_advances": fuel_advances,
        "escrow_deduction": escrow_deduction,
        "lumper_reimbursements": lumper_total,
        "detention_pay": detention_total,
        "net_pay": net_pay,
        "loads": loads,
    }


def initiate_ach(
    carrier_id: str,
    driver_id: str,
    amount: float,
    settlement: dict,
) -> dict[str, Any]:
    """Initiate payout to driver via Stripe — uses connected account transfer."""
    s = get_settings()

    if not s.stripe_secret_key:
        log_agent("settler", "ach_skipped", carrier_id=carrier_id,
                  payload={"reason": "stripe_not_configured", "amount": amount})
        return {"status": "skipped", "reason": "stripe_not_configured"}

    if amount <= 0:
        return {"status": "skipped", "reason": "zero_or_negative_amount"}

    stripe.api_key = s.stripe_secret_key

    # Lookup Stripe connected account or destination for this carrier
    sb = get_supabase()
    banking = (
        sb.table("banking_accounts")
        .select("account_token")
        .eq("carrier_id", carrier_id)
        .single()
        .execute()
        .data
    )
    if not banking or not banking.get("account_token"):
        log_agent("settler", "ach_skipped", carrier_id=carrier_id,
                  payload={"reason": "no_bank_token", "amount": amount})
        return {"status": "skipped", "reason": "no_bank_token — manual payout required"}

    try:
        # Transfer in cents to connected account
        transfer = stripe.Transfer.create(
            amount=int(amount * 100),
            currency="usd",
            destination=banking["account_token"],
            metadata={
                "carrier_id": carrier_id,
                "driver_id": driver_id,
                "week_start": settlement["week"][0],
                "week_end": settlement["week"][1],
                "loads": settlement["loads_delivered"],
            },
            description=f"3LL Settlement {settlement['week'][0]} to {settlement['week'][1]}",
        )
        log_agent("settler", "ach_initiated", carrier_id=carrier_id,
                  payload={"transfer_id": transfer.id, "amount": amount})
        return {"status": "initiated", "transfer_id": transfer.id, "amount": amount}

    except stripe.StripeError as exc:
        log_agent("settler", "ach_failed", carrier_id=carrier_id, error=str(exc))
        return {"status": "failed", "error": str(exc)}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    """Agent entrypoint — called from routes_agents.py or execution engine."""
    driver_id = payload.get("driver_id", "")
    carrier_id = payload.get("carrier_id", "")
    week_start = payload.get("week_start", "")
    week_end = payload.get("week_end", "")
    driver_pct = float(payload.get("driver_pct", _DEFAULT_DRIVER_PCT))

    if not all([driver_id, week_start, week_end]):
        return {"agent": "settler", "error": "driver_id, week_start, week_end required"}

    settlement = calc_driver_payout(driver_id, week_start, week_end, driver_pct)

    ach_result = {"status": "not_attempted"}
    if carrier_id and settlement["net_pay"] > 0:
        ach_result = initiate_ach(carrier_id, driver_id, settlement["net_pay"], settlement)

    log_agent("settler", "run", carrier_id=carrier_id,
              payload={"driver_id": driver_id, "net_pay": settlement["net_pay"]},
              result=ach_result.get("status"))

    return {"agent": "settler", "settlement": settlement, "ach": ach_result}
