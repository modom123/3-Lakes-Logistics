"""Step 17: one-shot script to create the $200/mo Founders product in Stripe.
Run once per environment. Prints the price_id you should paste into
STRIPE_PRICE_FOUNDERS in .env.

    python -m scripts.init_stripe_product
"""
from __future__ import annotations

import sys

import stripe

from app.settings import get_settings


def main() -> int:
    s = get_settings()
    if not s.stripe_secret_key:
        print("STRIPE_SECRET_KEY missing", file=sys.stderr)
        return 1
    stripe.api_key = s.stripe_secret_key

    product = stripe.Product.create(
        name="3 Lakes Logistics — Founders",
        description="Locked $200/mo lifetime rate for the first 1,000 carriers.",
        metadata={"plan": "founders"},
    )
    price = stripe.Price.create(
        product=product.id,
        unit_amount=20000,  # $200.00
        currency="usd",
        recurring={"interval": "month"},
        metadata={"plan": "founders"},
    )
    print(f"product_id: {product.id}")
    print(f"price_id:   {price.id}")
    print()
    print("Paste into .env as:")
    print(f"STRIPE_PRICE_FOUNDERS={price.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
