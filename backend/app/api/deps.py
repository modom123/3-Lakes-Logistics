"""Shared route dependencies.

Stage 5 upgrades:
- `require_bearer`  — legacy service-to-service token (command center).
- `require_jwt`     — Supabase JWT verification via HS256 secret.
- `require_role`    — factory returning a dependency that enforces a role set.
- `require_plan`    — factory enforcing Stripe plan tiers (step 73).
"""
from __future__ import annotations

from typing import Callable, Iterable

import jwt
from fastapi import Depends, Header, HTTPException, status

from ..settings import get_settings

VALID_ROLES = {"admin", "owner", "dispatcher", "driver", "viewer"}


def require_bearer(authorization: str | None = Header(default=None)) -> None:
    """Simple service-token guard for backend-to-backend calls."""
    s = get_settings()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != s.api_bearer_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid bearer token")


def require_jwt(authorization: str | None = Header(default=None)) -> dict:
    """Verify a Supabase-issued JWT and return its claims.

    Returns a dict with at least: sub, role, carrier_id (if mapped),
    email. Endpoints can downstream-use this for record scoping.
    """
    s = get_settings()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing jwt")
    token = authorization.removeprefix("Bearer ").strip()

    # Allow the legacy service token during migration.
    if token == s.api_bearer_token:
        return {"sub": "service", "role": "admin", "carrier_id": None}

    if not s.supabase_jwt_secret:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "SUPABASE_JWT_SECRET not configured",
        )
    try:
        claims = jwt.decode(
            token,
            s.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "jwt expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid jwt") from exc
    return claims


def require_role(*roles: str) -> Callable:
    """Factory: return a dependency that enforces one of the listed roles."""
    for r in roles:
        if r not in VALID_ROLES:
            raise ValueError(f"unknown role: {r}")

    def _dep(claims: dict = Depends(require_jwt)) -> dict:
        role = claims.get("role") or (claims.get("app_metadata") or {}).get("role")
        if role not in roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"role {role!r} not authorised; need one of {sorted(roles)}",
            )
        return claims

    return _dep


PLAN_ORDER = ["founders", "pro", "scale"]


def require_plan(min_plan: str) -> Callable:
    """Step 73: feature-gate endpoints by Stripe plan tier."""
    if min_plan not in PLAN_ORDER:
        raise ValueError(f"unknown plan: {min_plan}")
    need_ix = PLAN_ORDER.index(min_plan)

    def _dep(claims: dict = Depends(require_jwt)) -> dict:
        if (claims.get("role") or "") == "admin":
            return claims
        plan = (claims.get("app_metadata") or {}).get("plan") or claims.get("plan")
        if not plan or plan not in PLAN_ORDER or PLAN_ORDER.index(plan) < need_ix:
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                f"plan {plan!r} below required tier {min_plan!r}",
            )
        return claims

    return _dep


def carrier_scope(claims: dict = Depends(require_jwt)) -> str | None:
    """Return the carrier_id the JWT is scoped to, or None for admins."""
    if (claims.get("role") or "") == "admin":
        return None
    return claims.get("carrier_id") or (claims.get("app_metadata") or {}).get("carrier_id")


def assert_carrier_access(claims: dict, carrier_id: str) -> None:
    if (claims.get("role") or "") == "admin":
        return
    scoped = claims.get("carrier_id") or (claims.get("app_metadata") or {}).get("carrier_id")
    if scoped != carrier_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "carrier scope mismatch")


def any_role_in(claims: dict, allowed: Iterable[str]) -> bool:
    role = claims.get("role") or (claims.get("app_metadata") or {}).get("role")
    return role in set(allowed)
