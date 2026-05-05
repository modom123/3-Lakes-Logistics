"""Driver payouts via Stripe Connect.

Endpoints:
  POST /api/payout/setup — Initialize driver Stripe onboarding
  GET  /api/payout/status — Get payout setup status
  POST /api/payout/request — Request payout for delivered load
  GET  /api/payout/history — View payout history
"""
from __future__ import annotations

from typing import Annotated
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
import stripe

from ..supabase_client import supabase_client
from ..settings import get_settings
from ..logging_service import get_logger
from .routes_driver_auth import require_driver_token

log = get_logger(__name__)
router = APIRouter(prefix="/payout", tags=["payout"])

DriverSession = Annotated[dict, Depends(require_driver_token)]


# ────────────────────────────────────────────────────────────────────────────
# MODELS
# ────────────────────────────────────────────────────────────────────────────

class PayoutSetupResponse(BaseModel):
    onboarding_url: str
    account_id: str


class PayoutRequestModel(BaseModel):
    load_id: str
    amount_cents: int


class PayoutHistoryItem(BaseModel):
    id: str
    load_id: str | None
    amount_cents: int
    net_cents: int
    status: str
    paid_at: str | None


# ────────────────────────────────────────────────────────────────────────────
# HELPERS
# ────────────────────────────────────────────────────────────────────────────

def get_stripe_client():
    """Initialize Stripe with secret key."""
    s = get_settings()
    if not s.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="stripe not configured"
        )
    stripe.api_key = s.stripe_secret_key
    return stripe


# ────────────────────────────────────────────────────────────────────────────
# PAYOUT SETUP
# ────────────────────────────────────────────────────────────────────────────

@router.post("/setup", response_model=PayoutSetupResponse)
async def setup_driver_payout(session: DriverSession):
    """Initialize Stripe Connect onboarding for driver.

    Creates a Stripe Connected Account and sends driver to onboarding.
    """
    driver_id = session["driver_id"]
    stripe_client = get_stripe_client()

    try:
        # Get driver details
        driver_result = supabase_client.table("drivers").select(
            "id, first_name, last_name, phone_e164, email, stripe_account_id, stripe_account_status"
        ).eq("id", driver_id).single().execute()

        driver = driver_result.data

        # If already connected, return existing onboarding link
        if driver.get("stripe_account_id") and driver.get("stripe_account_status") == "connected":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="payout already set up"
            )

        # Create or retrieve Stripe Connected Account
        account_id = driver.get("stripe_account_id")
        if not account_id:
            # Create new Connected Account
            account = stripe_client.Account.create(
                type="express",
                country="US",
                email=driver.get("email") or "noreply@3lakes.io",
                settings={
                    "payouts": {
                        "debit_negative_balances": True,
                        "schedule": {"interval": "manual"}  # Manual payout requests
                    }
                },
                metadata={
                    "driver_id": driver_id,
                    "driver_name": f"{driver.get('first_name')} {driver.get('last_name')}"
                }
            )
            account_id = account.id

            # Save to database
            supabase_client.table("drivers").update({
                "stripe_account_id": account_id,
                "stripe_account_status": "pending"
            }).eq("id", driver_id).execute()

        # Create onboarding link
        onboarding_link = stripe_client.AccountLink.create(
            account=account_id,
            type="account_onboarding",
            refresh_url=f"https://3lakes.driver/payout/setup",
            return_url=f"https://3lakes.driver/payout/success"
        )

        return PayoutSetupResponse(
            onboarding_url=onboarding_link.url,
            account_id=account_id
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error("Payout setup failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="payout setup failed"
        )


@router.get("/status")
async def get_payout_status(session: DriverSession):
    """Get driver payout setup status."""
    driver_id = session["driver_id"]

    try:
        driver_result = supabase_client.table("drivers").select(
            "stripe_account_id, stripe_account_status"
        ).eq("id", driver_id).single().execute()

        driver = driver_result.data
        return {
            "account_id": driver.get("stripe_account_id"),
            "status": driver.get("stripe_account_status", "not_connected"),
            "can_receive_payouts": driver.get("stripe_account_status") == "connected"
        }

    except Exception as e:
        log.error("Failed to get payout status: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="status fetch failed"
        )


# ────────────────────────────────────────────────────────────────────────────
# PAYOUT REQUEST
# ────────────────────────────────────────────────────────────────────────────

@router.post("/request")
async def request_payout(req: PayoutRequestModel, session: DriverSession):
    """Request instant payout for delivered load.

    Calculates deductions (8% dispatch fee, $45 insurance) and creates
    Stripe Transfer to driver's connected account.
    """
    driver_id = session["driver_id"]
    stripe_client = get_stripe_client()

    try:
        # Validate load exists & is delivered by this driver
        load_result = supabase_client.table("loads").select(
            "id, driver_id, rate_total, delivered_at"
        ).eq("id", req.load_id).eq("driver_id", driver_id).eq("status", "delivered").single().execute()

        load = load_result.data
        if not load:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="load not found or not delivered"
            )

        # Get driver Stripe account
        driver_result = supabase_client.table("drivers").select(
            "stripe_account_id, stripe_account_status"
        ).eq("id", driver_id).single().execute()

        driver = driver_result.data
        if driver.get("stripe_account_status") != "connected":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="payout not set up - complete onboarding first"
            )

        # Calculate net pay: gross - dispatch fee (8%) - insurance ($45)
        gross_cents = int(load.get("rate_total", 0) * 100)
        dispatch_fee = int(gross_cents * 0.08)
        insurance_cents = 4500  # $45
        net_cents = gross_cents - dispatch_fee - insurance_cents

        if net_cents <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="payout amount too low after deductions"
            )

        # Check if already paid out
        existing_payout = supabase_client.table("driver_payouts").select(
            "id, status"
        ).eq("load_id", req.load_id).eq("driver_id", driver_id).execute()

        if existing_payout.data and existing_payout.data[0].get("status") == "paid":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="load already paid out"
            )

        # Create Stripe Transfer
        transfer = stripe_client.Transfer.create(
            amount=net_cents,
            currency="usd",
            destination=driver["stripe_account_id"],
            metadata={
                "driver_id": driver_id,
                "load_id": req.load_id
            }
        )

        # Store payout record
        payout_result = supabase_client.table("driver_payouts").insert({
            "driver_id": driver_id,
            "load_id": req.load_id,
            "amount_cents": gross_cents,
            "dispatch_fee_cents": dispatch_fee,
            "insurance_cents": insurance_cents,
            "net_cents": net_cents,
            "stripe_transfer_id": transfer.id,
            "status": "processing" if transfer.status == "in_transit" else "paid"
        }).execute()

        payout_id = payout_result.data[0]["id"]

        return {
            "payout_id": payout_id,
            "transfer_id": transfer.id,
            "amount_cents": net_cents,
            "status": "processing",
            "arrives_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error("Payout request failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="payout request failed"
        )


# ────────────────────────────────────────────────────────────────────────────
# PAYOUT HISTORY
# ────────────────────────────────────────────────────────────────────────────

@router.get("/history", response_model=list[PayoutHistoryItem])
async def get_payout_history(session: DriverSession):
    """Get driver's payout history (last 30 payouts)."""
    driver_id = session["driver_id"]

    try:
        result = supabase_client.table("driver_payouts").select(
            "id, load_id, amount_cents, net_cents, status, paid_at"
        ).eq("driver_id", driver_id).order("requested_at", desc=True).limit(30).execute()

        return [PayoutHistoryItem(
            id=p["id"],
            load_id=p.get("load_id"),
            amount_cents=p.get("amount_cents", 0),
            net_cents=p.get("net_cents", 0),
            status=p.get("status", "pending"),
            paid_at=p.get("paid_at")
        ) for p in (result.data or [])]

    except Exception as e:
        log.error("Failed to get payout history: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="history fetch failed"
        )
