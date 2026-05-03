"""Security hardening — rate limiting, input validation, CORS, HTTPS."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Callable

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .logging_service import get_logger

log = get_logger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# RATE LIMITING
# ────────────────────────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address)


def rate_limit_by_driver(driver_id: str, requests_per_minute: int = 60):
    """Rate limit API calls by driver ID."""
    # In production: use redis for distributed rate limiting
    # This is a placeholder for local in-memory limiting
    pass


# ────────────────────────────────────────────────────────────────────────────
# INPUT VALIDATION
# ────────────────────────────────────────────────────────────────────────────

def validate_phone_e164(phone: str) -> str:
    """Validate and normalize phone to E.164 format."""
    digits = re.sub(r'\D', '', phone)

    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits[0] == '1':
        return f"+{digits}"
    elif phone.startswith('+'):
        if not re.match(r'^\+\d{10,15}$', phone):
            raise ValueError("invalid E.164 format")
        return phone
    else:
        raise ValueError("invalid phone format")


def validate_pin(pin: str) -> bool:
    """Validate 4-digit PIN."""
    return bool(re.match(r'^\d{4}$', pin))


def validate_uuid(value: str) -> bool:
    """Validate UUID v4 format."""
    uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
    return bool(re.match(uuid_pattern, value.lower()))


def sanitize_string(value: str, max_length: int = 1000) -> str:
    """Sanitize string input (remove null bytes, limit length)."""
    if not isinstance(value, str):
        raise ValueError("must be string")

    # Remove null bytes
    value = value.replace('\x00', '')

    # Limit length
    if len(value) > max_length:
        value = value[:max_length]

    return value.strip()


def validate_email(email: str) -> bool:
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


# ────────────────────────────────────────────────────────────────────────────
# SECURITY MIDDLEWARE
# ────────────────────────────────────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Enable XSS protection
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://fonts.googleapis.com; "
            "connect-src 'self' https://api.stripe.com https://cdn.supabase.com;"
        )

        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions Policy (formerly Feature Policy)
        response.headers["Permissions-Policy"] = (
            "geolocation=(self), "
            "microphone=(), "
            "camera=(), "
            "payment=(self)"
        )

        return response


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect HTTP to HTTPS in production."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip in development
        if request.url.hostname in ("localhost", "127.0.0.1"):
            return await call_next(request)

        # In production, redirect HTTP to HTTPS
        if request.url.scheme == "http":
            url = request.url.replace(scheme="https")
            from starlette.responses import RedirectResponse
            return RedirectResponse(url=url, status_code=301)

        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests for security auditing."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Log request
        log.info(
            f"{request.method} {request.url.path} "
            f"| Client: {request.client.host if request.client else 'unknown'} "
            f"| User-Agent: {request.headers.get('user-agent', 'unknown')[:50]}"
        )

        response = await call_next(request)

        # Log response
        log.info(f"{request.url.path} → {response.status_code}")

        return response


# ────────────────────────────────────────────────────────────────────────────
# SECURITY CHECKS
# ────────────────────────────────────────────────────────────────────────────

def check_sql_injection(value: str) -> bool:
    """Check for common SQL injection patterns."""
    dangerous_patterns = [
        r"(\bUNION\b.*\bSELECT\b)",
        r"(\bDROP\b|\bDELETE\b)",
        r"(\bEXEC\b|\bEXECUTE\b)",
        r"(;.*--)",
        r"(\bOR\b.*\b1\s*=\s*1)",
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, value, re.IGNORECASE):
            log.warning(f"Possible SQL injection detected: {value[:50]}")
            return False

    return True


def check_xss_injection(value: str) -> bool:
    """Check for common XSS patterns."""
    dangerous_patterns = [
        r"<script",
        r"javascript:",
        r"onerror=",
        r"onclick=",
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, value, re.IGNORECASE):
            log.warning(f"Possible XSS injection detected: {value[:50]}")
            return False

    return True


def check_brute_force(ip_address: str, attempt_count: int = 5, window_minutes: int = 15):
    """Check if IP has exceeded brute force threshold.

    In production: use Redis for distributed tracking.
    """
    # Placeholder for local in-memory tracking
    # Production: query from cache with key: f"brute_force:{ip_address}"
    pass


# ────────────────────────────────────────────────────────────────────────────
# ENCRYPTION HELPERS
# ────────────────────────────────────────────────────────────────────────────

def hash_sensitive_data(data: str) -> str:
    """Hash sensitive data (PII at rest)."""
    import hashlib
    return hashlib.sha256(data.encode()).hexdigest()


def mask_phone(phone: str) -> str:
    """Mask phone number for logs (show only last 4 digits)."""
    if len(phone) >= 4:
        return f"***-***-{phone[-4:]}"
    return "***"


def mask_email(email: str) -> str:
    """Mask email for logs."""
    if "@" in email:
        local, domain = email.split("@")
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
        return f"{masked_local}@{domain}"
    return "***"
