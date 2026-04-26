"""Shared route dependencies (auth guard for admin endpoints)."""
from __future__ import annotations

from fastapi import Header, HTTPException, status

from ..settings import get_settings


def require_bearer(authorization: str | None = Header(default=None)) -> str:
    """Auth guard: accepts a Supabase JWT *or* the legacy static bearer token.

    Priority:
      1. Valid Supabase JWT signed with SUPABASE_JWT_SECRET → passes, returns sub (user id)
      2. Static api_bearer_token → passes, returns "service"
      3. Anything else → 401/403

    Set SUPABASE_JWT_SECRET in .env (Supabase project → Settings → API → JWT Secret).
    Until that env var is populated the old static token continues to work unchanged.
    """
    s = get_settings()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()

    # ── Try Supabase JWT first ────────────────────────────────────────────────
    if s.supabase_jwt_secret:
        try:
            import jwt  # PyJWT

            payload = jwt.decode(
                token,
                s.supabase_jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
            return payload.get("sub", "jwt-user")
        except Exception:  # noqa: BLE001
            pass  # fall through to static token check

    # ── Fall back to static bearer token ─────────────────────────────────────
    if token == s.api_bearer_token:
        return "service"

    raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid or expired token")
