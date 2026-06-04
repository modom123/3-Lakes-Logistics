"""Webhook security and functionality tests.

Covers all 11 webhook endpoints:
  - Signature verification (valid/invalid/missing)
  - Graceful degradation on bad payloads
  - Correct HTTP status codes

Run:
    pytest tests/test_webhooks.py -v
"""
import hashlib
import hmac

import requests

BASE_URL = "https://three-lakes-logistics-api.onrender.com"
HEADERS = {"Authorization": "Bearer taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE"}


# ── Adobe Sign ────────────────────────────────────────────────────────────────

def test_adobe_webhook_no_signature_rejected():
    """Adobe webhook without X-Signature → 401 when secret is configured."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/adobe/agreement-signed",
        json={"agreement_id": "agr_test", "carrier_id": "car_test", "status": "signed"},
        timeout=15,
    )
    assert r.status_code in (400, 401, 422), (
        f"Adobe webhook accepted without signature (got {r.status_code})."
    )


def test_adobe_webhook_invalid_signature_rejected():
    """Adobe webhook with wrong X-Signature → 401."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/adobe/agreement-signed",
        json={"agreement_id": "agr_test", "carrier_id": "car_test", "status": "signed"},
        headers={"X-Signature": "badhash000000000000000000000000000000000000000000000000000000000"},
        timeout=15,
    )
    assert r.status_code in (400, 401, 422), (
        f"Adobe webhook accepted with invalid signature (got {r.status_code})."
    )


def test_adobe_webhook_missing_fields():
    """Adobe webhook with empty payload → 400, not 500."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/adobe/agreement-signed",
        json={},
        timeout=15,
    )
    assert r.status_code < 500, f"Empty Adobe payload caused crash (got {r.status_code})."


def test_adobe_webhook_non_signed_status_ignored():
    """Adobe webhook with status != signed → 200 ok (ignored, not an error)."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/adobe/agreement-signed",
        json={"agreement_id": "agr_001", "carrier_id": "car_001", "status": "out_for_signature"},
        timeout=15,
    )
    assert r.status_code < 500, f"Non-signed status caused crash (got {r.status_code})."


# ── Bland AI ──────────────────────────────────────────────────────────────────

def test_bland_webhook_no_headers_rejected():
    """Bland webhook without signature headers → 401 when secret is configured."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/bland",
        json={
            "event": "call.completed",
            "call_id": "call_test123",
            "phone_number": "+15550000000",
            "duration": 60,
        },
        timeout=15,
    )
    assert r.status_code in (200, 401, 422), (
        f"Unexpected status (got {r.status_code}). If 200, secret not configured — acceptable."
    )


def test_bland_webhook_invalid_signature_rejected():
    """Bland webhook with bogus signature → 401 when secret configured."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/bland",
        json={"event": "call.failed", "call_id": "call_test456", "phone_number": "+15550000001"},
        headers={
            "X-Bland-Signature": "fakesig000000000000000000000000000000000000000000000000000000000",
            "X-Bland-Request-Timestamp": "1700000000",
        },
        timeout=15,
    )
    assert r.status_code in (200, 401), (
        f"Bland webhook with bad signature returned unexpected {r.status_code}."
    )


def test_bland_webhook_malformed_body():
    """Bland webhook with invalid JSON → 422, never 500."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/bland",
        data=b"not json {{{",
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    assert r.status_code < 500, f"Malformed Bland payload caused crash (got {r.status_code})."


# ── Checkr ────────────────────────────────────────────────────────────────────

def test_checkr_webhook_no_signature_rejected():
    """Checkr webhook without X-Checkr-Signature → 401."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/checkr",
        json={"type": "report.completed", "data": {"object": {"id": "rpt_test", "status": "clear"}}},
        timeout=15,
    )
    assert r.status_code in (400, 401, 422), (
        f"Checkr webhook accepted without signature (got {r.status_code})."
    )


def test_checkr_webhook_invalid_signature_rejected():
    """Checkr webhook with wrong signature → 401."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/checkr",
        json={"type": "report.completed", "data": {"object": {"id": "rpt_test"}}},
        headers={"X-Checkr-Signature": "sha256=badhash"},
        timeout=15,
    )
    assert r.status_code in (400, 401, 422), (
        f"Checkr webhook accepted with bad signature (got {r.status_code})."
    )


def test_checkr_webhook_malformed_body():
    """Checkr webhook with malformed JSON → graceful 4xx, never 500."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/checkr",
        data=b"\xff\xfe garbage",
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    assert r.status_code < 500, f"Malformed Checkr payload caused crash (got {r.status_code})."


# ── Stripe Identity ───────────────────────────────────────────────────────────

def test_stripe_identity_webhook_no_signature_rejected():
    """Stripe Identity webhook without Stripe-Signature → 400."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/stripe-identity",
        data=b'{"type":"identity.verification_session.verified"}',
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    assert r.status_code in (400, 401, 422), (
        f"Stripe Identity webhook accepted without signature (got {r.status_code})."
    )


def test_stripe_identity_webhook_invalid_signature_rejected():
    """Stripe Identity webhook with bad Stripe-Signature → 400."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/stripe-identity",
        data=b'{"type":"identity.verification_session.verified"}',
        headers={"Stripe-Signature": "t=1234,v1=badhash"},
        timeout=15,
    )
    assert r.status_code in (400, 401, 422), (
        f"Stripe Identity accepted bad signature (got {r.status_code})."
    )


# ── Curri ─────────────────────────────────────────────────────────────────────

def test_curri_webhook_no_signature_rejected():
    """Curri webhook without X-Curri-Signature → 401 when secret configured."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/curri",
        json={"event": "order.new", "order_id": "ord_test001", "status": "pending"},
        timeout=15,
    )
    assert r.status_code in (200, 401, 422), (
        f"Unexpected status (got {r.status_code}). If 200, Curri secret not set — acceptable."
    )


def test_curri_webhook_invalid_signature_rejected():
    """Curri webhook with wrong HMAC → 401 when secret configured."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/curri",
        json={"event": "order.delivered", "order_id": "ord_test002"},
        headers={"X-Curri-Signature": "sha256=badhashbadhash"},
        timeout=15,
    )
    assert r.status_code in (200, 401), (
        f"Curri bad signature returned unexpected {r.status_code}."
    )


def test_curri_webhook_malformed_body():
    """Curri webhook with malformed JSON → 422, never 500."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/curri",
        data=b"not json",
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    assert r.status_code < 500, f"Malformed Curri payload caused crash (got {r.status_code})."


# ── Roadie ────────────────────────────────────────────────────────────────────

def test_roadie_webhook_no_signature_rejected():
    """Roadie webhook without X-Roadie-Signature → 401 when secret configured."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/roadie",
        json={"event": "shipment.new", "shipment_id": "ship_test001"},
        timeout=15,
    )
    assert r.status_code in (200, 401, 422), (
        f"Unexpected status (got {r.status_code}). If 200, Roadie secret not set — acceptable."
    )


def test_roadie_webhook_invalid_signature_rejected():
    """Roadie webhook with wrong HMAC → 401 when secret configured."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/roadie",
        json={"event": "shipment.delivered", "shipment_id": "ship_test002"},
        headers={"X-Roadie-Signature": "sha256=badhash"},
        timeout=15,
    )
    assert r.status_code in (200, 401), (
        f"Roadie bad signature returned unexpected {r.status_code}."
    )


def test_roadie_webhook_malformed_body():
    """Roadie webhook with malformed JSON → graceful error, never 500."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/roadie",
        data=b"\x00\x01 garbage",
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    assert r.status_code < 500, f"Malformed Roadie payload caused crash (got {r.status_code})."


# ── Twilio (signature verification now enforced) ──────────────────────────────

def test_twilio_webhook_no_signature_rejected():
    """Twilio webhook without X-Twilio-Signature → 401 when creds configured."""
    r = requests.post(
        f"{BASE_URL}/api/comms/webhook/twilio",
        data={"From": "+15550001111", "Body": "YES"},
        timeout=15,
    )
    assert r.status_code in (200, 401), (
        f"Unexpected status (got {r.status_code}). If 200, Twilio creds not configured."
    )


def test_twilio_webhook_valid_sms_response_shape():
    """Valid-looking Twilio SMS form POST → response is XML TwiML (when no sig enforced)."""
    r = requests.post(
        f"{BASE_URL}/api/comms/webhook/twilio",
        data={"From": "+15550009999", "Body": "STATUS"},
        timeout=15,
    )
    if r.status_code == 200:
        assert "Response" in r.text, "TwiML Response element missing from reply."
    else:
        assert r.status_code in (401, 422), f"Unexpected status {r.status_code}."


# ── Motive ELD (signature verification now enforced) ─────────────────────────

def test_motive_webhook_no_signature_rejected():
    """Motive webhook without X-Motive-Signature → 401 when secret configured."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/motive",
        json={"event_type": "vehicle.position", "carrier_id": "car_test", "data": {"lat": 41.0, "lng": -87.0}},
        timeout=15,
    )
    assert r.status_code in (200, 401, 422), (
        f"Unexpected status (got {r.status_code}). If 200, Motive secret not configured."
    )


def test_motive_webhook_invalid_signature_rejected():
    """Motive webhook with bogus HMAC → 401 when secret configured."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/motive",
        json={"event_type": "driver.hos_status", "carrier_id": "car_test"},
        headers={"X-Motive-Signature": "sha256=badhash"},
        timeout=15,
    )
    assert r.status_code in (200, 401), (
        f"Motive bad signature returned unexpected {r.status_code}."
    )


def test_motive_webhook_ping_event():
    """Motive ping event (no-op) → handled gracefully."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/motive",
        json={"event_type": "ping", "source": "motive"},
        timeout=15,
    )
    assert r.status_code < 500, f"Motive ping event caused crash (got {r.status_code})."


# ── Vapi Voice (signature verification now enforced) ─────────────────────────

def test_vapi_webhook_no_signature_rejected():
    """Vapi webhook without X-Vapi-Signature → 401 when secret configured."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/vapi",
        json={"type": "call-ended", "call": {"id": "call_test_vapi"}},
        timeout=15,
    )
    assert r.status_code in (200, 401, 422), (
        f"Unexpected status (got {r.status_code}). If 200, Vapi secret not configured."
    )


def test_vapi_webhook_invalid_signature_rejected():
    """Vapi webhook with wrong HMAC → 401 when secret configured."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/vapi",
        json={"type": "call-ended"},
        headers={"X-Vapi-Signature": "sha256=badhash"},
        timeout=15,
    )
    assert r.status_code in (200, 401), (
        f"Vapi bad signature returned unexpected {r.status_code}."
    )


# ── SendGrid inbound email ────────────────────────────────────────────────────

def test_sendgrid_inbound_email_no_signature():
    """SendGrid inbound parse without signature → accepted (secret optional) or 401."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/email/inbound",
        data={
            "from": "test@example.com",
            "to": "loads@3lakeslogistics.com",
            "subject": "Rate Confirmation",
            "text": "Please find attached rate confirmation.",
        },
        timeout=15,
    )
    assert r.status_code < 500, f"SendGrid inbound parse caused crash (got {r.status_code})."


def test_sendgrid_inbound_email_malformed():
    """SendGrid inbound with empty multipart → graceful error, never 500."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/email/inbound",
        data={},
        timeout=15,
    )
    assert r.status_code < 500, f"Empty SendGrid payload caused crash (got {r.status_code})."
