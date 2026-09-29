# ─────────────────────────────────────────────────────────────
# File:     backend/app/launch_readiness.py
# Created:  2026-09-29 22:31 UTC
# Purpose:  Go / no-go check before taking real customers and money.
# ─────────────────────────────────────────────────────────────
"""Launch readiness — can the business take a paying customer today?

Reports configuration as booleans only; never returns secret values.

  blocking     — without it we can't sign, bill, or talk to a customer
  recommended  — we can open without it, but work is manual or at risk
"""
from __future__ import annotations

from typing import Any

from . import pricing
from .settings import get_settings


def _item(name: str, ok: bool, fix: str, blocking: bool) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "blocking": blocking, "fix": "" if ok else fix}


def _stripe_is_live(key: str) -> bool:
    return key.startswith(("sk_live_", "rk_live_"))


def _verify_stripe_prices(s) -> list[dict[str, Any]]:
    """Confirm the configured price ids charge what the website promises."""
    import stripe
    stripe.api_key = s.stripe_secret_key
    out = []
    for label, price_id, usd in (
        ("Stripe Founders price is $%d/mo" % pricing.FOUNDERS_MONTHLY_USD, s.stripe_price_founders, pricing.FOUNDERS_MONTHLY_USD),
        ("Stripe Pro price is $%d/mo" % pricing.PRO_MONTHLY_USD, s.stripe_price_pro, pricing.PRO_MONTHLY_USD),
    ):
        ok, fix = False, "Run `python -m scripts.init_stripe_product` with the live key and set the new price ids on Render."
        if price_id:
            try:
                p = stripe.Price.retrieve(price_id)
                ok = p.get("unit_amount") == usd * 100 and (p.get("recurring") or {}).get("interval") == "month"
                if not ok:
                    fix = f"{price_id} charges {p.get('unit_amount')} cents/{(p.get('recurring') or {}).get('interval')}. " + fix
            except Exception as exc:  # noqa: BLE001
                fix = f"Could not read {price_id}: {exc}. " + fix
        out.append(_item(label, ok, fix, blocking=True))
    return out


def _lead_counts() -> list[dict[str, Any]]:
    from .prospecting.call_list import build_call_list
    from .supabase_client import get_supabase
    try:
        rows = get_supabase().table("leads").select("*").limit(2000).execute().data or []
    except Exception as exc:  # noqa: BLE001
        return [_item("Leads table readable", False, f"Supabase error: {exc}", blocking=True)]
    callable_now = build_call_list(rows, limit=10_000)
    return [
        _item("Leads table readable", True, "", blocking=True),
        _item(f"At least 50 callable leads (have {len(callable_now)})", len(callable_now) >= 50,
              "POST /api/prospecting/run (or wait for Naomi's 07:15 UTC run) to pull FMCSA carriers.",
              blocking=False),
    ]


def check(verify_stripe: bool = False, include_leads: bool = False) -> dict[str, Any]:
    s = get_settings()
    from .prospecting.loadboard_clients import get_connection_status
    boards = [b["name"] for b in get_connection_status() if b.get("connected")]

    items = [
        # ── Blocking: sign, bill, communicate ────────────────────────────────
        _item("ENV=production", s.env == "production", "Set ENV=production on Render.", True),
        _item("Supabase service role key", bool(s.supabase_service_role_key),
              "Set SUPABASE_SERVICE_ROLE_KEY on Render.", True),
        _item("API bearer token (protects Eagle Eye APIs)", bool(s.api_bearer_token),
              "Set API_BEARER_TOKEN on Render.", True),
        _item("Stripe key is LIVE (not test)", _stripe_is_live(s.stripe_secret_key or ""),
              "Activate the Stripe account, then set STRIPE_SECRET_KEY=sk_live_... on Render.", True),
        _item("Stripe Founders price id", bool(s.stripe_price_founders),
              "Set STRIPE_PRICE_FOUNDERS (see scripts/init_stripe_product.py).", True),
        _item("Stripe Pro price id", bool(s.stripe_price_pro),
              "Set STRIPE_PRICE_PRO (see scripts/init_stripe_product.py).", True),
        _item("Stripe billing webhook secret", bool(s.stripe_webhook_secret),
              "Create the live webhook to /api/webhooks/stripe and set STRIPE_WEBHOOK_SECRET.", True),
        _item("Postmark email (welcome + onboarding)", bool(s.postmark_server_token),
              "Set POSTMARK_SERVER_TOKEN.", True),
        _item("Twilio SMS (dispatch + driver login)",
              bool(s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number),
              "Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER.", True),
        # ── Recommended ──────────────────────────────────────────────────────
        _item("Load board API connected" + (f" ({', '.join(boards)})" if boards else ""), bool(boards),
              "Book manually in DAT One / Truckstop web until an API is set (DAT_CLIENT_ID/SECRET).", False),
        _item("DOT open-data app token (FMCSA lead pulls)", bool(s.dot_api_key),
              "Free token at data.transportation.gov → set DOT_API_KEY to avoid rate limits.", False),
        _item("Stripe Connect webhook secret (driver payouts)", bool(s.stripe_connect_webhook_secret),
              "Set STRIPE_CONNECT_WEBHOOK_SECRET.", False),
        _item("Bland AI (automated outbound calls)", bool(s.bland_ai_api_key),
              "Optional for launch — hand-dial the call list first.", False),
        _item("Sentry error tracking", bool(s.sentry_dsn), "Set SENTRY_DSN.", False),
        _item("Automated AI calls / SMS to cold leads are off", not s.automated_cold_outreach,
              "Daily Vance calls and SMS blasts hit FMCSA leads who never opted in (TCPA risk). "
              "Set AUTOMATED_COLD_OUTREACH=false until leads give written consent; hand-dial instead.", False),
    ]
    if verify_stripe and s.stripe_secret_key:
        items += _verify_stripe_prices(s)
    if include_leads:
        items += _lead_counts()

    blockers = [i for i in items if i["blocking"] and not i["ok"]]
    return {
        "ready": not blockers,
        "blocking_open": len(blockers),
        "recommended_open": sum(1 for i in items if not i["blocking"] and not i["ok"]),
        "pricing": {
            "founders_monthly_usd": pricing.FOUNDERS_MONTHLY_USD,
            "pro_monthly_usd": pricing.PRO_MONTHLY_USD,
            "heavy_payg_fee_pct": pricing.HEAVY_PAYG_FEE_PCT * 100,
            "light_fleet_fee_pct": pricing.LIGHT_FLEET_FEE_PCT * 100,
        },
        "items": items,
    }
