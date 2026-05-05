"""Driver authentication — PIN-based login for mobile app.

Endpoints:
  POST /api/driver-auth/login — Phone + PIN → JWT session token
  POST /api/driver-auth/logout — Invalidate session
  GET  /api/driver-auth/me — Get driver profile (requires token)
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Header, status, Depends
from pydantic import BaseModel, Field

from ..supabase_client import supabase_client
from ..logging_service import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/driver-auth", tags=["driver-auth"])


# ────────────────────────────────────────────────────────────────────────────
# MODELS
# ────────────────────────────────────────────────────────────────────────────

class DriverLoginRequest(BaseModel):
    phone: str = Field(..., description="Phone number (10 digits, e.g. 3125550100)")
    pin: str = Field(..., description="4-digit PIN")


class DriverLoginResponse(BaseModel):
    token: str
    driver_id: str
    driver_name: str
    carrier_id: str
    expires_at: str
    refresh_token: str | None = None


class DriverMe(BaseModel):
    driver_id: str
    driver_name: str
    phone: str
    carrier_id: str
    cdl_number: str | None
    truck_number: str | None


# ────────────────────────────────────────────────────────────────────────────
# DEPENDENCIES
# ────────────────────────────────────────────────────────────────────────────

def require_driver_token(authorization: str | None = Header(default=None)) -> dict:
    """Extract & validate driver session token from Authorization header.

    Returns: {driver_id, expires_at} if valid, raises 401 otherwise.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token"
        )

    token = authorization.removeprefix("Bearer ").strip()
    if not token or len(token) < 32:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token format"
        )

    # Query driver_sessions table
    try:
        result = supabase_client.table("driver_sessions").select(
            "id, driver_id, expires_at"
        ).eq("token", token).single().execute()

        session = result.data
        if not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token not found"
            )

        # Check expiry
        expires_at = datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00"))
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token expired"
            )

        # Update last_activity_at
        supabase_client.table("driver_sessions").update(
            {"last_activity_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", session["id"]).execute()

        return {"driver_id": session["driver_id"], "expires_at": session["expires_at"]}

    except Exception as e:
        log.error("Token validation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token validation failed"
        )


DriverSession = Annotated[dict, Depends(require_driver_token)]


# ────────────────────────────────────────────────────────────────────────────
# HELPERS
# ────────────────────────────────────────────────────────────────────────────

def hash_pin(pin: str) -> str:
    """Hash PIN using SHA256 + salt (production: use argon2)."""
    salt = "3ll_driver_pin_salt_v1"  # In production, use per-driver unique salt
    return hashlib.sha256((salt + pin).encode()).hexdigest()


def normalize_phone(phone: str) -> str:
    """Normalize phone to E.164 format (+1 XXXXXXXXXX)."""
    digits = ''.join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits[0] == '1':
        return f"+{digits}"
    else:
        raise ValueError(f"invalid phone format: {phone}")


# ────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ────────────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=DriverLoginResponse)
async def driver_login(req: DriverLoginRequest):
    """Driver login: phone + 4-digit PIN.

    Returns JWT-like session token (stored in DB, 30-day expiry).
    """
    # Validate input
    if not req.pin or len(req.pin) != 4 or not req.pin.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PIN must be 4 digits"
        )

    # Normalize phone
    try:
        phone_e164 = normalize_phone(req.phone)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # Hash PIN
    pin_hash = hash_pin(req.pin)

    # Look up driver
    try:
        result = supabase_client.table("drivers").select(
            "id, first_name, last_name, carrier_id, pin_hash"
        ).eq("phone_e164", phone_e164).single().execute()

        driver = result.data
    except Exception:
        # For security, don't reveal if phone exists
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid phone or PIN"
        )

    # Verify PIN
    if not driver.get("pin_hash") or driver["pin_hash"] != pin_hash:
        log.warning("PIN mismatch for phone=%s", phone_e164)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid phone or PIN"
        )

    # Create session
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    try:
        supabase_client.table("driver_sessions").insert({
            "driver_id": driver["id"],
            "token": token,
            "expires_at": expires_at.isoformat(),
            "ip_address": "unknown",  # Would get from request context in production
            "user_agent": "mobile-app"
        }).execute()
    except Exception as e:
        log.error("Failed to create session: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="login failed"
        )

    return DriverLoginResponse(
        token=token,
        driver_id=driver["id"],
        driver_name=f"{driver['first_name']} {driver['last_name']}".strip(),
        carrier_id=driver["carrier_id"],
        expires_at=expires_at.isoformat(),
        refresh_token=None  # Implement refresh tokens in phase 2
    )


@router.post("/logout")
async def driver_logout(session: DriverSession):
    """Invalidate driver session."""
    try:
        driver_id = session["driver_id"]
        supabase_client.table("driver_sessions").delete().eq(
            "driver_id", driver_id
        ).execute()
        return {"status": "logged out"}
    except Exception as e:
        log.error("Logout failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="logout failed"
        )


@router.get("/me", response_model=DriverMe)
async def get_driver_me(session: DriverSession):
    """Get authenticated driver profile."""
    driver_id = session["driver_id"]

    try:
        result = supabase_client.table("drivers").select(
            "id, first_name, last_name, phone_e164, carrier_id, cdl_number"
        ).eq("id", driver_id).single().execute()

        driver = result.data

        return DriverMe(
            driver_id=driver["id"],
            driver_name=f"{driver['first_name']} {driver['last_name']}".strip(),
            phone=driver["phone_e164"],
            carrier_id=driver["carrier_id"],
            cdl_number=driver.get("cdl_number")
        )
    except Exception as e:
        log.error("Failed to fetch driver profile: %s", e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="driver not found"
        )


@router.post("/set-pin")
async def set_driver_pin(pin: str, session: DriverSession):
    """Driver sets or updates their PIN."""
    if not pin or len(pin) != 4 or not pin.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PIN must be 4 digits"
        )

    driver_id = session["driver_id"]
    pin_hash = hash_pin(pin)

    try:
        supabase_client.table("drivers").update(
            {"pin_hash": pin_hash}
        ).eq("id", driver_id).execute()

        return {"status": "PIN updated"}
    except Exception as e:
        log.error("Failed to update PIN: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="failed to update PIN"
        )
