"""Shared route dependencies (auth guard for admin endpoints)."""
from __future__ import annotations

from fastapi import Header, HTTPException, status

from ..settings import get_settings


def require_bearer(authorization: str | None = Header(default=None)) -> None:
    """Simple bearer-token guard for the EAGLE EYE + internal calls.

    Accepts API_BEARER_TOKEN, BOND_API_KEY, or the legacy taiOFL40 token
    so that browsers with any cached version of shared/config.js work
    without requiring a hard refresh after a token rotation.
    """
    s = get_settings()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    # Accept env-configured tokens + legacy token for browser-cache backward compat
    _LEGACY = "taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE"
    valid = {t for t in (s.api_bearer_token, s.bond_api_key, _LEGACY) if t}
    if token not in valid:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid bearer token")
