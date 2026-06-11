"""Shared route dependencies (auth guard for admin endpoints)."""
from __future__ import annotations

from fastapi import Header, HTTPException, status

from ..settings import get_settings


def require_bearer(authorization: str | None = Header(default=None)) -> None:
    """Simple bearer-token guard for the EAGLE EYE + internal calls.

    Accepts either API_BEARER_TOKEN or BOND_API_KEY so Eagle Eye and
    Bond tooling both authenticate without needing separate tokens.
    """
    s = get_settings()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    valid = {t for t in (s.api_bearer_token, s.bond_api_key) if t}
    if not valid or token not in valid:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid bearer token")
