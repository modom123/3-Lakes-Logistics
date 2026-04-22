"""PII encryption + webhook signature verification (steps 74-76).

`encrypt_str` / `decrypt_str` — symmetric Fernet over `PII_ENCRYPTION_KEY`.
Used for bank_account, ELD api tokens, anything that must not leak if
Supabase is compromised.

`verify_stripe`, `verify_motive`, `verify_vapi`, `verify_twilio` — signed
webhook verification. Each returns True or raises `SignatureError`.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

from .settings import get_settings


class SignatureError(Exception):
    pass


def _fernet() -> Fernet:
    s = get_settings()
    if not s.pii_encryption_key:
        raise RuntimeError("PII_ENCRYPTION_KEY not set")
    # Accept a 32-byte secret (raw or urlsafe b64). Derive Fernet key.
    key = s.pii_encryption_key.encode()
    if len(key) == 44 and key.endswith(b"="):
        return Fernet(key)
    digest = hashlib.sha256(key).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_str(plain: str | None) -> str | None:
    if plain in (None, ""):
        return plain
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_str(token: str | None) -> str | None:
    if token in (None, ""):
        return token
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise SignatureError("decryption failed — key rotated or tampered") from exc


def mask_last4(value: str | None) -> str:
    if not value:
        return ""
    v = "".join(c for c in value if c.isalnum())
    return f"••••{v[-4:]}" if len(v) >= 4 else "••••"


# -------- Webhook verification --------

@dataclass
class Signed:
    verified: bool
    body: bytes


def verify_stripe(body: bytes, sig_header: str | None, tolerance: int = 300) -> Signed:
    """Verify a Stripe-Signature header (t=...,v1=...)."""
    s = get_settings()
    if not s.stripe_webhook_secret or not sig_header:
        raise SignatureError("missing stripe webhook secret or signature")
    parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
    ts = parts.get("t")
    v1 = parts.get("v1")
    if not ts or not v1:
        raise SignatureError("malformed stripe signature")
    if abs(int(time.time()) - int(ts)) > tolerance:
        raise SignatureError("stripe timestamp out of tolerance")
    payload = f"{ts}.".encode() + body
    mac = hmac.new(s.stripe_webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, v1):
        raise SignatureError("stripe signature mismatch")
    return Signed(True, body)


def verify_motive(body: bytes, sig_header: str | None) -> Signed:
    s = get_settings()
    if not s.motive_webhook_secret or not sig_header:
        raise SignatureError("missing motive webhook secret or signature")
    mac = hmac.new(s.motive_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, sig_header.removeprefix("sha256=")):
        raise SignatureError("motive signature mismatch")
    return Signed(True, body)


def verify_vapi(body: bytes, sig_header: str | None) -> Signed:
    s = get_settings()
    if not s.vapi_webhook_secret:
        # vapi did not enforce signatures in early releases; allow if unconfigured.
        return Signed(False, body)
    if not sig_header:
        raise SignatureError("missing vapi signature")
    mac = hmac.new(s.vapi_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, sig_header):
        raise SignatureError("vapi signature mismatch")
    return Signed(True, body)


def verify_twilio(url: str, params: dict, sig_header: str | None) -> Signed:
    """Twilio: sign(url + sorted k+v concatenation) with auth token, base64."""
    s = get_settings()
    if not s.twilio_auth_token or not sig_header:
        raise SignatureError("missing twilio auth token or signature")
    joined = url + "".join(f"{k}{v}" for k, v in sorted(params.items()))
    mac = hmac.new(s.twilio_auth_token.encode(), joined.encode(), hashlib.sha1).digest()
    expected = base64.b64encode(mac).decode()
    if not hmac.compare_digest(expected, sig_header):
        raise SignatureError("twilio signature mismatch")
    return Signed(True, b"")
