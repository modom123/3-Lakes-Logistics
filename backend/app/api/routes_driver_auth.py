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

from ..supabase_client import get_supabase
from ..logging_service import get_logger
from ..settings import get_settings
from ..cost_tracking import track_twilio
from .deps import require_bearer

log = get_logger(__name__)

FALCON_URL = "https://www.3lakeslogistics.com/driver-pwa/login.html"


def _send_falcon_welcome(phone_e164: str, first_name: str, pin: str) -> None:
    """Send Falcon onboarding SMS to a newly created driver. Non-fatal on failure."""
    s = get_settings()
    if not (s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number):
        log.warning("Twilio not configured — skipping Falcon welcome SMS for %s", phone_e164)
        return
    body = (
        f"Welcome to 3 Lakes Logistics, {first_name}!\n\n"
        f"Your Falcon driver portal is ready 24/7:\n{FALCON_URL}\n\n"
        f"Phone: {phone_e164}\n"
        f"PIN: {pin}\n\n"
        f"Tap the link and add it to your Home Screen for quick access.\n"
        f"Questions? Reply to this message or call dispatch."
    )
    try:
        from twilio.rest import Client
        Client(s.twilio_account_sid, s.twilio_auth_token).messages.create(
            to=phone_e164,
            from_=s.twilio_from_number,
            body=body,
        )
        track_twilio(sms_count=1)
        log.info("Falcon welcome SMS sent to %s", phone_e164)
    except Exception as exc:
        log.error("Falcon welcome SMS failed for %s: %s", phone_e164, exc)


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
        result = get_supabase().table("driver_sessions").select(
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
        get_supabase().table("driver_sessions").update(
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
        result = get_supabase().table("drivers").select(
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
        get_supabase().table("driver_sessions").insert({
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
        get_supabase().table("driver_sessions").delete().eq(
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
        result = get_supabase().table("drivers").select(
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
        get_supabase().table("drivers").update(
            {"pin_hash": pin_hash}
        ).eq("id", driver_id).execute()

        return {"status": "PIN updated"}
    except Exception as e:
        log.error("Failed to update PIN: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="failed to update PIN"
        )


# ────────────────────────────────────────────────────────────────────────────
# ADMIN — create / manage drivers (Eagle Eye dispatcher UI)
# ────────────────────────────────────────────────────────────────────────────

class CreateDriverRequest(BaseModel):
    carrier_id: str
    first_name: str
    last_name: str
    phone: str = Field(..., description="10-digit US number or E.164")
    pin: str    = Field(..., description="4-digit PIN")
    driver_code: str | None = None
    cdl_number:  str | None = None
    truck_id:    str | None = None


@router.post("/create", dependencies=[Depends(require_bearer)])
async def create_driver(req: CreateDriverRequest):
    """Admin: create a new driver account (called from Eagle Eye)."""
    if not req.pin or len(req.pin) != 4 or not req.pin.isdigit():
        raise HTTPException(status_code=400, detail="PIN must be 4 digits")

    try:
        phone_e164 = normalize_phone(req.phone)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    pin_hash = hash_pin(req.pin)
    driver_code = req.driver_code or f"DRV-{phone_e164[-4:]}"

    try:
        existing = get_supabase().table("drivers").select("id").eq("phone_e164", phone_e164).execute()
        if existing.data:
            raise HTTPException(status_code=409, detail="Driver with this phone already exists")

        result = get_supabase().table("drivers").insert({
            "carrier_id":  req.carrier_id,
            "driver_code": driver_code,
            "first_name":  req.first_name,
            "last_name":   req.last_name,
            "phone":       phone_e164,
            "phone_e164":  phone_e164,
            "pin_hash":    pin_hash,
            "status":      "active",
        }).execute()

        driver = result.data[0]

        _send_falcon_welcome(phone_e164, req.first_name, req.pin)

        return {
            "ok": True,
            "driver_id":   driver["id"],
            "driver_code": driver["driver_code"],
            "phone":       phone_e164,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error("Create driver failed: %s", e)
        raise HTTPException(status_code=500, detail="failed to create driver")


@router.get("/list", dependencies=[Depends(require_bearer)])
async def list_drivers(carrier_id: str | None = None, limit: int = 200):
    """Admin: list all drivers (optionally filtered by carrier)."""
    try:
        q = get_supabase().table("drivers").select(
            "id, carrier_id, driver_code, first_name, last_name, phone_e164, status, created_at"
        ).order("created_at", desc=True).limit(limit)
        if carrier_id:
            q = q.eq("carrier_id", carrier_id)
        result = q.execute()
        return {"count": len(result.data or []), "items": result.data or []}
    except Exception as e:
        log.error("List drivers failed: %s", e)
        raise HTTPException(status_code=500, detail="failed to list drivers")


@router.delete("/{driver_id}", dependencies=[Depends(require_bearer)])
async def delete_driver(driver_id: str):
    """Admin: deactivate a driver (sets status=inactive)."""
    try:
        get_supabase().table("drivers").update({"status": "inactive"}).eq("id", driver_id).execute()
        return {"ok": True}
    except Exception as e:
        log.error("Delete driver failed: %s", e)
        raise HTTPException(status_code=500, detail="failed to deactivate driver")
