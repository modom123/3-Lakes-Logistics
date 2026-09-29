# ─────────────────────────────────────────────────────────────
# File:     backend/scripts/init_stripe_product.py
# Updated:  2026-09-29 22:31 UTC — create Founders + Pro from app/pricing.py
# ─────────────────────────────────────────────────────────────
"""Step 17: one-shot script to create the Founders and Pro subscription prices.

Run once per Stripe mode (once with the test key, once with the live key).
Prints the price ids to paste into Render as STRIPE_PRICE_FOUNDERS and
STRIPE_PRICE_PRO.

    cd backend && python -m scripts.init_stripe_product
"""
from __future__ import annotations

import sys

import stripe

from app import pricing
from app.settings import get_settings

PLANS = [
    ("founders", "3 Lakes Logistics — Founders",
     f"${pricing.FOUNDERS_MONTHLY_USD}/mo per truck, locked for life. 0% commission.",
     pricing.FOUNDERS_MONTHLY_USD, "STRIPE_PRICE_FOUNDERS"),
    ("pro", "3 Lakes Logistics — Pro",
     f"${pricing.PRO_MONTHLY_USD}/mo per truck, month-to-month. 0% commission.",
     pricing.PRO_MONTHLY_USD, "STRIPE_PRICE_PRO"),
]


def main() -> int:
    s = get_settings()
    if not s.stripe_secret_key:
        print("STRIPE_SECRET_KEY missing", file=sys.stderr)
        return 1
    stripe.api_key = s.stripe_secret_key
    mode = "LIVE" if s.stripe_secret_key.startswith(("sk_live_", "rk_live_")) else "TEST"
    print(f"Stripe mode: {mode}\n")

    env_lines = []
    for plan, name, desc, usd, env_key in PLANS:
        product = stripe.Product.create(name=name, description=desc, metadata={"plan": plan})
        price = stripe.Price.create(
            product=product.id,
            unit_amount=usd * 100,
            currency="usd",
            recurring={"interval": "month"},
            metadata={"plan": plan},
        )
        print(f"{plan:9s} product={product.id} price={price.id} (${usd}/mo)")
        env_lines.append(f"{env_key}={price.id}")

    print("\nSet these on Render (Environment tab):")
    print("\n".join(env_lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
