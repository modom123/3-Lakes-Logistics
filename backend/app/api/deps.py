"""Shared route dependencies (auth guard for admin endpoints)."""
from __future__ import annotations

from fastapi import Header, HTTPException, status

from ..settings import get_settings


def require_bearer(authorization: str | None = Header(default=None)) -> None:
    """Simple bearer-token guard for the command center + internal calls.

    Production should swap this for proper Supabase JWT verification.
    """
    s = get_settings()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != s.api_bearer_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid bearer token")
