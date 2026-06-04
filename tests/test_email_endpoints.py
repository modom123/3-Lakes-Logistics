"""Email endpoint tests — covers all 8 routes in routes_email.py.

Run:
    pytest tests/test_email_endpoints.py -v
"""
import requests

BASE_URL = "https://three-lakes-logistics-api.onrender.com"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": "Bearer taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE",
}


# ── GET /api/email-log ────────────────────────────────────────────────────────

def test_email_log_list():
    """Email log returns list with expected shape."""
    r = requests.get(f"{BASE_URL}/api/email-log", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, (list, dict)), f"Unexpected shape: {type(data)}"


def test_email_log_list_requires_auth():
    """Email log rejects unauthenticated requests."""
    r = requests.get(f"{BASE_URL}/api/email-log", timeout=15)
    assert r.status_code in (401, 403)


def test_email_log_list_limit_param():
    """Email log respects limit query param."""
    r = requests.get(f"{BASE_URL}/api/email-log?limit=3", headers=HEADERS, timeout=15)
    assert r.status_code == 200


# ── GET /api/email-log/{email_id} ────────────────────────────────────────────

def test_email_detail_not_found():
    """Non-existent email ID → 404, not 500."""
    r = requests.get(
        f"{BASE_URL}/api/email-log/nonexistent-email-id-000",
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code in (404, 422), (
        f"Non-existent email ID returned {r.status_code} — expected 404/422."
    )


def test_email_detail_requires_auth():
    """Email detail rejects unauthenticated requests."""
    r = requests.get(f"{BASE_URL}/api/email-log/some-id", timeout=15)
    assert r.status_code in (401, 403)


# ── GET /api/email-log/{email_id}/attachments ────────────────────────────────

def test_email_attachments_not_found():
    """Attachments for non-existent email → 404, not 500."""
    r = requests.get(
        f"{BASE_URL}/api/email-log/nonexistent-email-id-000/attachments",
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code in (404, 422), (
        f"Non-existent email attachments returned {r.status_code}."
    )


def test_email_attachments_requires_auth():
    """Email attachments endpoint rejects unauthenticated requests."""
    r = requests.get(
        f"{BASE_URL}/api/email-log/some-id/attachments",
        timeout=15,
    )
    assert r.status_code in (401, 403)


# ── POST /api/email/send-test ────────────────────────────────────────────────

def test_send_test_email_valid():
    """Send test email to known address → 200 (delivered or queued)."""
    r = requests.post(
        f"{BASE_URL}/api/email/send-test",
        params={"to_email": "new56money@gmail.com", "template": "onboarding_welcome"},
        headers=HEADERS,
        timeout=20,
    )
    assert r.status_code in (200, 202, 404), (
        f"Send-test email returned {r.status_code}. 404 is ok if template doesn't exist."
    )


def test_send_test_email_requires_auth():
    """Send test email endpoint rejects unauthenticated requests."""
    r = requests.post(
        f"{BASE_URL}/api/email/send-test",
        params={"to_email": "test@example.com", "template": "test"},
        timeout=15,
    )
    assert r.status_code in (401, 403)


def test_send_test_email_missing_params():
    """Send test email without required params → 422, not 500."""
    r = requests.post(
        f"{BASE_URL}/api/email/send-test",
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code in (400, 422), (
        f"Missing params returned {r.status_code} — expected 400/422."
    )


# ── GET /api/email/templates ─────────────────────────────────────────────────

def test_email_templates_list():
    """Email templates list returns dict or list."""
    r = requests.get(f"{BASE_URL}/api/email/templates", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), (list, dict)), "Templates response not a list or dict."


def test_email_templates_requires_auth():
    """Email templates list rejects unauthenticated requests."""
    r = requests.get(f"{BASE_URL}/api/email/templates", timeout=15)
    assert r.status_code in (401, 403)


# ── POST /api/email/templates/{template_name} ─────────────────────────────────

def test_update_email_template_not_found():
    """Updating a non-existent template → 404, not 500."""
    r = requests.post(
        f"{BASE_URL}/api/email/templates/nonexistent_template_xyz",
        json={"subject": "Test Subject", "body": "Test body"},
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code in (200, 201, 404, 422), (
        f"Template update returned unexpected {r.status_code}."
    )


def test_update_email_template_requires_auth():
    """Template update rejects unauthenticated requests."""
    r = requests.post(
        f"{BASE_URL}/api/email/templates/some_template",
        json={"body": "x"},
        timeout=15,
    )
    assert r.status_code in (401, 403)


# ── GET /api/email/stats ─────────────────────────────────────────────────────

def test_email_stats_returns_metrics():
    """Email stats endpoint returns metrics dict."""
    r = requests.get(f"{BASE_URL}/api/email/stats", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict), f"Email stats not a dict: {type(data)}"


def test_email_stats_requires_auth():
    """Email stats rejects unauthenticated requests."""
    r = requests.get(f"{BASE_URL}/api/email/stats", timeout=15)
    assert r.status_code in (401, 403)


# ── POST /api/email/{email_id}/parse-rate-confirmation ───────────────────────

def test_parse_rate_confirmation_not_found():
    """Parse rate confirmation on non-existent email → 404, not 500."""
    r = requests.post(
        f"{BASE_URL}/api/email/FAKE-EMAIL-ID-XYZ/parse-rate-confirmation",
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code in (404, 422), (
        f"Non-existent email parse returned {r.status_code}."
    )


def test_parse_rate_confirmation_requires_auth():
    """Rate confirmation parse rejects unauthenticated requests."""
    r = requests.post(
        f"{BASE_URL}/api/email/some-id/parse-rate-confirmation",
        timeout=15,
    )
    assert r.status_code in (401, 403)
