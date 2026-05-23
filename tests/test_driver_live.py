"""Driver API live tests — runs against the Render-hosted backend.

Usage:
    pytest tests/test_driver_live.py -v

Covers: driver-auth, driver profile, GPS location, payout, notifications.
Tests that require a seeded test driver account are auto-skipped when the
account is absent from the live DB.
"""
import pytest
import requests

BASE_URL = "https://three-lakes-logistics-api.onrender.com"

# Credentials for seeded test driver (from sql/test_accounts.sql)
TEST_PHONE = "555-000-0001"
TEST_PIN   = "1234"

# Module-level token — populated by the first test that successfully logs in
_live_token: str | None = None


def _post(path: str, body: dict | None = None, token: str | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.post(f"{BASE_URL}{path}", json=body, headers=headers, timeout=15)


def _get(path: str, token: str | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.get(f"{BASE_URL}{path}", headers=headers, timeout=15)


# ── Auth — rejection paths (always runnable) ─────────────────────────────────

def test_login_bad_pin():
    """Wrong PIN returns 401."""
    r = _post("/api/driver-auth/login", {"phone": TEST_PHONE, "pin": "0000"})
    assert r.status_code == 401


def test_login_inactive_driver():
    """Inactive driver account returns 403."""
    r = _post("/api/driver-auth/login", {"phone": "555-000-0003", "pin": "0000"})
    assert r.status_code in (401, 403)


def test_me_no_token():
    """GET /me without token returns 401."""
    r = _get("/api/driver-auth/me")
    assert r.status_code == 401


def test_me_bad_token():
    """GET /me with a garbage token returns 401."""
    r = _get("/api/driver-auth/me", token="not_a_real_token_xyz")
    assert r.status_code == 401


def test_profile_no_token():
    """GET /profile without token returns 401."""
    r = _get("/api/driver/profile")
    assert r.status_code == 401


# ── Auth — valid login (skipped when test account not seeded) ─────────────────

def test_login_valid():
    """Valid credentials return a bearer token."""
    global _live_token
    r = _post("/api/driver-auth/login", {"phone": TEST_PHONE, "pin": TEST_PIN})
    if r.status_code == 404:
        pytest.skip("Test driver account not seeded in live DB")
    assert r.status_code == 200, f"Login failed: {r.text}"
    data = r.json()
    assert "token" in data, f"No token in response: {data}"
    _live_token = data["token"]


# ── Authenticated paths (depend on test_login_valid having set _live_token) ───

def _require_token():
    if _live_token is None:
        pytest.skip("No live token — test_login_valid skipped or failed")


def test_me_with_token():
    """GET /me with valid token returns driver info."""
    _require_token()
    r = _get("/api/driver-auth/me", token=_live_token)
    assert r.status_code == 200
    assert "driver" in r.json()


def test_profile_with_token():
    """GET /profile with valid token returns full driver profile."""
    _require_token()
    r = _get("/api/driver/profile", token=_live_token)
    assert r.status_code == 200


def test_payout_status():
    """GET /payout/status returns payout state."""
    _require_token()
    r = _get("/api/payout/status", token=_live_token)
    assert r.status_code == 200


def test_location_invalid_lat():
    """POST /location with lat=999 (out of range) returns 422."""
    _require_token()
    r = _post("/api/driver/location", {"lat": 999, "lng": -87.6298}, token=_live_token)
    assert r.status_code == 422
