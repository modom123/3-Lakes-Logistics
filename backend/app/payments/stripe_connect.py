"""Shared Stripe Connect (Express) payout-account helpers.

One implementation of "provision a driver's payout account / hand them an
onboarding link / sync their status from Stripe" for every driver model:

  • light fleet  → public.light_vehicle_drivers
  • heavy fleet  → public.drivers

Used by driver onboarding (agents.maya), the light-fleet + heavy-fleet payout
routes, and the account.updated Connect webhook. All functions are best-effort:
they log and return None/…{"ok": False} on Stripe or DB errors rather than
raising, so a payment hiccup can never block driver activation.

Requires migration 025_stripe_connect_payouts.sql (adds the stripe_account_*
columns these functions read/write).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import stripe

from ..logging_service import get_logger
from ..settings import get_settings
from ..supabase_client import get_supabase

log = get_logger(__name__)

# Driver tables that carry the stripe_account_* columns.
DRIVER_TABLES = ("light_vehicle_drivers", "drivers")

# Where the Stripe-hosted onboarding flow returns the driver to.
_PWA_BASE = "https://www.3lakeslogistics.com/driver-pwa"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_configured() -> bool:
    """True when a Stripe secret key is set (payouts can be provisioned)."""
    return bool(get_settings().stripe_secret_key)


def _client():
    """Return the stripe module with the api key set, or None if not configured."""
    s = get_settings()
    if not s.stripe_secret_key:
        return None
    stripe.api_key = s.stripe_secret_key
    return stripe


def ensure_connect_account(
    table: str,
    driver_id: str,
    *,
    email: str | None = None,
    name: str | None = None,
    metadata: dict | None = None,
) -> str | None:
    """Return the driver's existing Stripe Express account id, or create one.

    On first creation the new account id is persisted to the driver row with
    status='pending'. Returns None if Stripe is not configured or the create
    fails (logged).
    """
    sc = _client()
    if sc is None:
        return None
    sb = get_supabase()

    # Select only columns common to every driver table (drivers uses
    # first_name/last_name, light_vehicle_drivers uses name) — the display name
    # is always supplied by the caller.
    try:
        row = (
            sb.table(table)
            .select("stripe_account_id,email")
            .eq("id", str(driver_id))
            .maybe_single()
            .execute()
            .data
            or {}
        )
    except Exception as e:  # noqa: BLE001
        log.error("ensure_connect_account: lookup failed %s/%s: %s", table, driver_id, e)
        row = {}

    existing = row.get("stripe_account_id")
    if existing:
        return existing

    try:
        account = sc.Account.create(
            type="express",
            country="US",
            email=email or row.get("email") or None,
            capabilities={"transfers": {"requested": True}},
            business_type="individual",
            settings={"payouts": {"schedule": {"interval": "manual"}}},
            metadata={
                "driver_id": str(driver_id),
                "driver_name": name or "",
                **(metadata or {}),
            },
        )
    except Exception as e:  # noqa: BLE001
        log.error("Connect account create failed %s/%s: %s", table, driver_id, e)
        return None

    account_id = account.id
    try:
        sb.table(table).update(
            {"stripe_account_id": account_id, "stripe_account_status": "pending"}
        ).eq("id", str(driver_id)).execute()
    except Exception as e:  # noqa: BLE001
        log.error("Persist stripe_account_id failed %s/%s: %s", table, driver_id, e)

    return account_id


def create_onboarding_link(
    account_id: str, *, return_url: str, refresh_url: str
) -> str | None:
    """Create a fresh Stripe-hosted account_onboarding AccountLink URL."""
    sc = _client()
    if sc is None:
        return None
    try:
        link = sc.AccountLink.create(
            account=account_id,
            type="account_onboarding",
            return_url=return_url,
            refresh_url=refresh_url,
        )
        return link.url
    except Exception as e:  # noqa: BLE001
        log.error("AccountLink create failed for %s: %s", account_id, e)
        return None


def start_onboarding(
    table: str,
    driver_id: str,
    *,
    email: str | None = None,
    name: str | None = None,
    base_url: str | None = None,
    metadata: dict | None = None,
) -> tuple[str | None, str | None]:
    """Ensure the driver has a Connect account and return (account_id, onboarding_url).

    Returns (None, None) if Stripe is not configured or provisioning fails.
    """
    account_id = ensure_connect_account(
        table, driver_id, email=email, name=name, metadata=metadata
    )
    if not account_id:
        return None, None
    base = (base_url or _PWA_BASE).rstrip("/")
    url = create_onboarding_link(
        account_id,
        return_url=f"{base}/index.html?payout=success",
        refresh_url=f"{base}/index.html?payout=refresh",
    )
    return account_id, url


def sync_account_status(account_id: str, *, table: str | None = None) -> dict[str, Any]:
    """Retrieve the account from Stripe and update the matching driver row.

    Mapping:
      payouts_enabled & details_submitted → 'connected'
      details_submitted only              → 'pending'
      otherwise                           → 'restricted'

    Searches both driver tables when ``table`` is not given. Returns a dict with
    the resolved status.
    """
    sc = _client()
    if sc is None:
        return {"ok": False, "reason": "stripe_not_configured"}
    try:
        acct = sc.Account.retrieve(account_id)
    except Exception as e:  # noqa: BLE001
        log.error("Account.retrieve failed for %s: %s", account_id, e)
        return {"ok": False, "reason": str(e)}

    payouts_enabled = bool(acct.get("payouts_enabled"))
    details_submitted = bool(acct.get("details_submitted"))
    if payouts_enabled and details_submitted:
        status = "connected"
    elif details_submitted:
        status = "pending"
    else:
        status = "restricted"

    sb = get_supabase()
    updated_table = None
    for t in ((table,) if table else DRIVER_TABLES):
        upd: dict = {
            "stripe_account_status": status,
            "stripe_payouts_enabled": payouts_enabled,
        }
        if status == "connected":
            upd["stripe_onboarded_at"] = _now()
        try:
            res = (
                sb.table(t)
                .update(upd)
                .eq("stripe_account_id", account_id)
                .execute()
            )
            if res.data:
                updated_table = t
                break
        except Exception as e:  # noqa: BLE001
            log.error("status update failed on %s for %s: %s", t, account_id, e)

    return {
        "ok": True,
        "status": status,
        "payouts_enabled": payouts_enabled,
        "table": updated_table,
    }
