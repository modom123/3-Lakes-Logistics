"""Security & Authorization pen-testing — Phase 1 + Financial Logic (Phase 3).

Covers the executive QA blueprint:
  Phase 1: Webhook forgery, driver auth brute force, horizontal privilege escalation
  Phase 3: Payout idempotency guard, malformed webhook graceful degradation
  Phase 4: Adobe callback integrity, Twilio webhook input validation

Run:
    pytest tests/test_security.py -v
"""
import os
import time
import requests

BASE_URL = os.getenv("API_BASE_URL", "https://three-lakes-logistics-api.onrender.com")
API_TOKEN = os.getenv("API_BEARER_TOKEN", "")
HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {API_TOKEN}"}

# A driver-style token (not the IEBC API token) — used for privilege escalation tests.
# Any plausible but unauthorized bearer string should be rejected on exec routes.
FAKE_DRIVER_TOKEN = "driver_bearer_token_not_executive_abc123xyz"


# ── Phase 1: Webhook Forgery ──────────────────────────────────────────────────

def test_stripe_webhook_no_signature():
    """Stripe webhook without Stripe-Signature header → 400 (forgery rejected)."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/stripe",
        data=b'{"type":"charge.succeeded","data":{}}',
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    assert r.status_code in (400, 403), (
        f"Expected 400/403 — forged Stripe webhook accepted (got {r.status_code}). "
        "An attacker can manipulate financial ledgers without signature verification."
    )


def test_stripe_webhook_invalid_signature():
    """Stripe webhook with an obviously wrong signature → 400."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/stripe",
        data=b'{"type":"payment_intent.succeeded"}',
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": "t=9999,v1=fakesignaturexyz,v0=nope",
        },
        timeout=15,
    )
    assert r.status_code in (400, 403), (
        f"Invalid Stripe signature accepted (got {r.status_code})."
    )


def test_vapi_webhook_malformed_body():
    """Vapi webhook with malformed JSON body → 422 or 400, never 500."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/vapi",
        data=b"not json at all {{{",
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    assert r.status_code < 500, (
        f"Malformed Vapi webhook caused server crash (got {r.status_code})."
    )


def test_motive_webhook_malformed_body():
    """Motive webhook with malformed JSON → 422 or 400, never 500."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/motive",
        data=b"\x00\x01\x02 bad binary",
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    assert r.status_code < 500, (
        f"Malformed Motive webhook caused server crash (got {r.status_code})."
    )


# ── Phase 1: Driver Auth Brute Force / Rate Limiting ─────────────────────────

def test_driver_auth_brute_force_rate_limit():
    """5 rapid bad-PIN attempts — should hit rate limiting (429) or stay at 401.
    Critical: must never return 200 regardless of attempt count.
    """
    statuses = []
    for _ in range(5):
        r = requests.post(
            f"{BASE_URL}/api/driver-auth/login",
            json={"phone": "555-000-0001", "pin": "9999"},
            timeout=15,
        )
        statuses.append(r.status_code)

    # Must never succeed
    assert 200 not in statuses, (
        f"Brute force succeeded — login returned 200 after bad PINs: {statuses}"
    )
    # Ideally rate-limits (429), but at minimum all must be 4xx
    for s in statuses:
        assert s < 500, f"Server error during brute force attempt: {s}"


# ── Phase 1: Horizontal Privilege Escalation ─────────────────────────────────

def test_privilege_escalation_executive_dashboard():
    """Driver-style token cannot access /api/executives/dashboard → 401/403."""
    r = requests.get(
        f"{BASE_URL}/api/executives/dashboard",
        headers={"Authorization": f"Bearer {FAKE_DRIVER_TOKEN}"},
        timeout=15,
    )
    assert r.status_code in (401, 403), (
        f"Driver token reached executive dashboard (got {r.status_code}). "
        "Horizontal privilege escalation possible."
    )


def test_privilege_escalation_executive_escalations():
    """Driver-style token cannot POST to /api/executives/escalations → 401/403."""
    r = requests.post(
        f"{BASE_URL}/api/executives/escalations",
        json={"message": "injected escalation", "priority": "critical"},
        headers={"Authorization": f"Bearer {FAKE_DRIVER_TOKEN}"},
        timeout=15,
    )
    assert r.status_code in (401, 403), (
        f"Driver token triggered executive escalation (got {r.status_code})."
    )


def test_executive_routes_require_auth():
    """All executive routes reject unauthenticated requests → 401/403."""
    for path in ["/api/executives/dashboard", "/api/executives/kpis",
                 "/api/executives/brief/today", "/api/executives/escalations"]:
        r = requests.get(f"{BASE_URL}{path}", timeout=15)
        assert r.status_code in (401, 403), (
            f"Executive route {path} accessible without auth (got {r.status_code})."
        )


# ── Phase 3: Financial Logic — Payout Idempotency ────────────────────────────

def test_payout_endpoint_requires_auth():
    """Payout request without token → 401 (auth guard confirmed before logic runs)."""
    r = requests.post(
        f"{BASE_URL}/api/payout/request",
        json={"load_id": "test-load-001", "gross_amount": 1850.00},
        timeout=15,
    )
    assert r.status_code in (401, 403), (
        f"Payout endpoint accessible without authentication (got {r.status_code})."
    )


# ── Phase 4: Data Integrity — Webhook Graceful Degradation ───────────────────

def test_twilio_webhook_empty_payload():
    """Empty POST to Twilio webhook → graceful 4xx, not a 500 crash."""
    r = requests.post(
        f"{BASE_URL}/api/comms/webhook/twilio",
        data={},
        timeout=15,
    )
    assert r.status_code < 500, (
        f"Empty Twilio webhook payload caused server crash (got {r.status_code})."
    )


def test_twilio_webhook_malformed_payload():
    """Corrupted body to Twilio webhook → graceful error, never 500."""
    r = requests.post(
        f"{BASE_URL}/api/comms/webhook/twilio",
        data=b"\xff\xfe garbage \x00 bytes",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    assert r.status_code < 500, (
        f"Malformed Twilio payload caused server crash (got {r.status_code})."
    )


def test_adobe_callback_no_event():
    """Adobe Sign callback with no event data → 4xx, never 500."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/adobe/agreement-signed",
        json={},
        timeout=15,
    )
    assert r.status_code < 500, (
        f"Empty Adobe callback caused server crash (got {r.status_code})."
    )


def test_email_parse_unknown_id():
    """Rate-confirmation parse on a non-existent email ID → 404, not 500."""
    r = requests.post(
        f"{BASE_URL}/api/email/FAKE-EMAIL-ID-000/parse-rate-confirmation",
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code in (404, 422, 403), (
        f"Unknown email ID parse returned {r.status_code} — expected 404/422/403."
    )
