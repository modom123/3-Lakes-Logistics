"""Shipper authentication — email + password login for shipper portal.

Endpoints:
  POST /api/shipper/auth/register — Create shipper account
  POST /api/shipper/auth/login    — Email + password → session token
  GET  /api/shipper/auth/me       — Get shipper profile (requires token)
  POST /api/shipper/auth/logout   — Invalidate session
  PATCH /api/shipper/auth/me      — Update profile fields
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

log = get_logger(__name__)

router = APIRouter()


# ────────────────────────────────────────────────────────────────────────────
# MODELS
# ────────────────────────────────────────────────────────────────────────────

class ShipperRegisterRequest(BaseModel):
    company_name: str
    email: str
    password: str
    phone: str | None = None
    contact_name: str | None = None


class ShipperLoginRequest(BaseModel):
    email: str
    password: str


class ShipperLoginResponse(BaseModel):
    token: str
    shipper_id: str
    company_name: str
    expires_at: str


class ShipperUpdateRequest(BaseModel):
    company_name: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    contact_name: str | None = None


# ────────────────────────────────────────────────────────────────────────────
# DEPENDENCIES
# ────────────────────────────────────────────────────────────────────────────

def require_shipper_token(authorization: str | None = Header(default=None)) -> dict:
    """Extract & validate shipper session token from Authorization Bearer header.

    Returns dict with shipper_id, expires_at if valid. Raises 401 otherwise.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
        )

    token = authorization.removeprefix("Bearer ").strip()
    if not token or len(token) < 32:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token format",
        )

    try:
        result = get_supabase().table("shipper_sessions").select(
            "id, shipper_id, expires_at"
        ).eq("token", token).single().execute()

        session = result.data
        if not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token not found",
            )

        expires_at = datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00"))
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token expired",
            )

        return {"shipper_id": session["shipper_id"], "expires_at": session["expires_at"]}

    except HTTPException:
        raise
    except Exception as e:
        log.error("Shipper token validation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token validation failed",
        )


ShipperSession = Annotated[dict, Depends(require_shipper_token)]


# ────────────────────────────────────────────────────────────────────────────
# HELPERS
# ────────────────────────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    """Hash password with SHA256 + static salt."""
    salt = "3ll_shipper_v1"
    return hashlib.sha256((salt + password).encode()).hexdigest()


# ────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ────────────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=ShipperLoginResponse)
async def register_shipper(req: ShipperRegisterRequest):
    """Create a new shipper account and return a session token."""
    if not req.email or "@" not in req.email:
        raise HTTPException(status_code=400, detail="invalid email address")
    if not req.password or len(req.password) < 6:
        raise HTTPException(status_code=400, detail="password must be at least 6 characters")
    if not req.company_name or not req.company_name.strip():
        raise HTTPException(status_code=400, detail="company_name is required")

    password_hash = _hash_password(req.password)

    try:
        existing = get_supabase().table("shippers").select("id").eq(
            "email", req.email.lower()
        ).execute()
        if existing.data:
            raise HTTPException(status_code=409, detail="email already registered")

        result = get_supabase().table("shippers").insert({
            "company_name": req.company_name.strip(),
            "email": req.email.lower(),
            "phone": req.phone,
            "contact_name": req.contact_name,
            "password_hash": password_hash,
        }).execute()

        shipper = result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        log.error("Shipper registration failed: %s", e)
        raise HTTPException(status_code=500, detail="registration failed")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=90)

    try:
        get_supabase().table("shipper_sessions").insert({
            "shipper_id": shipper["id"],
            "token": token,
            "expires_at": expires_at.isoformat(),
        }).execute()
    except Exception as e:
        log.error("Failed to create shipper session after register: %s", e)
        raise HTTPException(status_code=500, detail="session creation failed")

    return ShipperLoginResponse(
        token=token,
        shipper_id=shipper["id"],
        company_name=shipper["company_name"],
        expires_at=expires_at.isoformat(),
    )


@router.post("/login", response_model=ShipperLoginResponse)
async def shipper_login(req: ShipperLoginRequest):
    """Shipper login: email + password → 90-day DB-backed session token."""
    password_hash = _hash_password(req.password)

    try:
        result = get_supabase().table("shippers").select(
            "id, company_name, password_hash, status"
        ).eq("email", req.email.lower()).single().execute()

        shipper = result.data
    except Exception:
        raise HTTPException(status_code=401, detail="invalid email or password")

    if not shipper or shipper.get("password_hash") != password_hash:
        log.warning("Password mismatch for email=%s", req.email)
        raise HTTPException(status_code=401, detail="invalid email or password")

    if shipper.get("status") != "active":
        raise HTTPException(status_code=403, detail="account is not active")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=90)

    try:
        get_supabase().table("shipper_sessions").insert({
            "shipper_id": shipper["id"],
            "token": token,
            "expires_at": expires_at.isoformat(),
        }).execute()
    except Exception as e:
        log.error("Failed to create shipper session: %s", e)
        raise HTTPException(status_code=500, detail="login failed")

    return ShipperLoginResponse(
        token=token,
        shipper_id=shipper["id"],
        company_name=shipper["company_name"],
        expires_at=expires_at.isoformat(),
    )


@router.get("/me")
async def get_shipper_me(session: ShipperSession):
    """Get authenticated shipper profile."""
    shipper_id = session["shipper_id"]

    try:
        result = get_supabase().table("shippers").select(
            "id, company_name, email, phone, address, city, state, zip, "
            "contact_name, api_key, webhook_url, webhook_events, status, "
            "credit_limit, payment_terms, total_loads, total_spend, created_at"
        ).eq("id", shipper_id).single().execute()

        shipper = result.data
        if not shipper:
            raise HTTPException(status_code=404, detail="shipper not found")

        return shipper
    except HTTPException:
        raise
    except Exception as e:
        log.error("Failed to fetch shipper profile: %s", e)
        raise HTTPException(status_code=500, detail="failed to fetch profile")


@router.post("/logout")
async def shipper_logout(session: ShipperSession):
    """Invalidate all sessions for this shipper."""
    shipper_id = session["shipper_id"]

    try:
        get_supabase().table("shipper_sessions").delete().eq(
            "shipper_id", shipper_id
        ).execute()
        return {"status": "logged out"}
    except Exception as e:
        log.error("Shipper logout failed: %s", e)
        raise HTTPException(status_code=500, detail="logout failed")


@router.patch("/me")
async def update_shipper_me(req: ShipperUpdateRequest, session: ShipperSession):
    """Update shipper profile fields."""
    shipper_id = session["shipper_id"]

    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="no fields provided to update")

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        result = get_supabase().table("shippers").update(updates).eq(
            "id", shipper_id
        ).execute()

        return result.data[0] if result.data else {"ok": True}
    except Exception as e:
        log.error("Failed to update shipper profile: %s", e)
        raise HTTPException(status_code=500, detail="failed to update profile")
