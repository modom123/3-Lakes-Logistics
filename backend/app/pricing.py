# ─────────────────────────────────────────────────────────────
# File:     backend/app/pricing.py
# Created:  2026-09-29 22:31 UTC
# Purpose:  Single source of truth for 3LL customer pricing.
# ─────────────────────────────────────────────────────────────
"""Customer pricing — every fee the platform charges lives here.

These numbers must match what the public site (index.html, light-fleet.html)
and the signed agreements promise. Change them here, not in route handlers.

Heavy fleet (CDL carriers / owner-operators):
  founders        $300/mo per truck, locked for life   — 0% per load
  pro / standard  $500/mo per truck, month-to-month    — 0% per load
  enterprise      custom contract                       — 0% per load
  pay_as_you_go   no monthly fee                        — 8% of gross per load

Light fleet (cargo van, sedan, SUV, NEMT, courier):
  15% of each completed trip, no monthly fee.

IEBC / FALCON channel (TruckSmarter owner-operators dispatched by IEBC):
  15% of gross per load — the rate the FALCON portal shows the carrier.
"""
from __future__ import annotations

FOUNDERS_MONTHLY_USD = 300
PRO_MONTHLY_USD = 500
HEAVY_PAYG_FEE_PCT = 0.08
LIGHT_FLEET_FEE_PCT = 0.15
IEBC_FALCON_FEE_PCT = 0.15

# Plans billed by flat monthly subscription — no per-load dispatch fee.
SUBSCRIPTION_PLANS = frozenset({"founders", "pro", "standard", "enterprise"})


def heavy_fee_pct(plan: str | None) -> float:
    """Per-load dispatch fee for a heavy-fleet carrier on `plan`.

    Unknown or missing plans fall back to pay-as-you-go so a carrier with no
    active subscription is never dispatched for free.
    """
    return 0.0 if (plan or "").strip().lower() in SUBSCRIPTION_PLANS else HEAVY_PAYG_FEE_PCT


def carrier_plan(sb, carrier_id: str | None) -> str | None:
    """Look up a carrier's plan from active_carriers; None if unknown."""
    if not carrier_id:
        return None
    try:
        r = sb.table("active_carriers").select("plan").eq("id", carrier_id).maybe_single().execute()
        return (getattr(r, "data", None) or {}).get("plan")
    except Exception:  # noqa: BLE001
        return None
