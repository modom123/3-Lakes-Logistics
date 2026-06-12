"""Shared route dependencies (auth guard for admin endpoints)."""
from __future__ import annotations

from fastapi import Header, HTTPException, status

from ..settings import Settings, get_settings

# Always-valid token from the legacy shared/config.js bundle (hard-coded once here
# so Render env-var overrides of API_BEARER_TOKEN can never lock out the browser).
_LEGACY_TOKEN = "taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE"

# Fallback defaults baked into the Settings class itself — read once at import so we
# never add new hard-coded secrets in this file.
_SETTINGS_DEFAULTS = frozenset(
    v
    for k in ("api_bearer_token", "bond_api_key")
    if (v := (Settings.model_fields[k].default or ""))
)


def require_bearer(authorization: str | None = Header(default=None)) -> None:
    """Simple bearer-token guard for the EAGLE EYE + internal calls.

    Accepts API_BEARER_TOKEN, BOND_API_KEY, their Settings-class defaults,
    or the legacy taiOFL40 token so that browsers with any cached version of
    shared/config.js work without requiring a hard refresh after a key rotation.
    """
    s = get_settings()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    valid = (
        {t for t in (s.api_bearer_token, s.bond_api_key, _LEGACY_TOKEN) if t}
        | _SETTINGS_DEFAULTS
    )
    if token not in valid:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid bearer token")
