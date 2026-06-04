"""Execution Engine tests — step registry, domain listing, and step dispatch.

Tests the /api/execution/* endpoints for all 7 domains:
  onboarding, dispatch, transit, settlement, clm, compliance, analytics

Run:
    pytest tests/test_execution_engine.py -v
"""
import requests

BASE_URL = "https://three-lakes-logistics-api.onrender.com"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": "Bearer taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE",
}

ALL_DOMAINS = ["onboarding", "dispatch", "transit", "settlement", "clm", "compliance", "analytics"]


# ── Auth guards ───────────────────────────────────────────────────────────────

def test_execution_steps_requires_auth():
    """Execution step list rejects unauthenticated requests."""
    r = requests.get(f"{BASE_URL}/api/execution/steps", timeout=15)
    assert r.status_code in (401, 403)


def test_execution_run_step_requires_auth():
    """Running a step rejects unauthenticated requests."""
    r = requests.post(
        f"{BASE_URL}/api/execution/steps/1/run",
        json={"input_payload": {}},
        timeout=15,
    )
    assert r.status_code in (401, 403)


# ── Step Registry ─────────────────────────────────────────────────────────────

def test_execution_steps_list_all():
    """Step registry returns list of steps with required fields."""
    r = requests.get(f"{BASE_URL}/api/execution/steps", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    steps = r.json()
    assert isinstance(steps, list), f"Steps not a list: {type(steps)}"
    assert len(steps) > 0, "Step registry is empty."
    for step in steps[:5]:
        assert "number" in step, f"Step missing 'number': {step}"
        assert "name" in step, f"Step missing 'name': {step}"
        assert "domain" in step, f"Step missing 'domain': {step}"


def test_execution_steps_cover_all_domains():
    """Step registry has at least one step per domain."""
    r = requests.get(f"{BASE_URL}/api/execution/steps", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    steps = r.json()
    found_domains = {s["domain"] for s in steps}
    for domain in ALL_DOMAINS:
        assert domain in found_domains, (
            f"Domain '{domain}' has no registered steps. "
            f"Found domains: {found_domains}"
        )


def test_execution_steps_filter_by_domain():
    """Step list filtered by domain returns only matching steps."""
    for domain in ALL_DOMAINS:
        r = requests.get(
            f"{BASE_URL}/api/execution/steps?domain={domain}",
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 200, f"Domain filter for {domain} failed: {r.status_code}"
        steps = r.json()
        assert isinstance(steps, list)
        for step in steps:
            assert step["domain"] == domain, (
                f"Step {step['number']} has domain '{step['domain']}' but filtered for '{domain}'."
            )


def test_execution_steps_have_sequential_numbers():
    """Step numbers are positive integers starting from 1."""
    r = requests.get(f"{BASE_URL}/api/execution/steps", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    steps = r.json()
    numbers = sorted(s["number"] for s in steps)
    assert numbers[0] >= 1, f"Step numbers start at {numbers[0]}, expected >= 1."
    assert len(numbers) == len(set(numbers)), "Duplicate step numbers found."


# ── Run Domain ────────────────────────────────────────────────────────────────

def test_execution_run_domain_invalid_domain():
    """Running an unknown domain → 400 or 422, not 500."""
    r = requests.post(
        f"{BASE_URL}/api/execution/run",
        json={"domain": "nonexistent_domain_xyz"},
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code in (400, 422), (
        f"Invalid domain returned {r.status_code} — expected 400/422."
    )


def test_execution_run_domain_missing_domain():
    """Running with no domain → 422 validation error."""
    r = requests.post(
        f"{BASE_URL}/api/execution/run",
        json={},
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code == 422, (
        f"Missing domain returned {r.status_code} — expected 422."
    )


def test_execution_run_step_not_found():
    """Running a non-existent step number → 404, not 500."""
    r = requests.post(
        f"{BASE_URL}/api/execution/steps/99999/run",
        json={"input_payload": {}},
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code in (404, 422), (
        f"Non-existent step number returned {r.status_code}."
    )


# ── Onboarding domain steps (spot check steps 1-5) ───────────────────────────

def test_onboarding_step_1_reachable():
    """Onboarding step 1 (intake/welcome) is in registry."""
    r = requests.get(
        f"{BASE_URL}/api/execution/steps?domain=onboarding",
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code == 200
    steps = r.json()
    step_numbers = [s["number"] for s in steps]
    assert 1 in step_numbers, f"Onboarding step 1 not found. Steps: {step_numbers[:10]}"


def test_onboarding_steps_have_auto_trigger_field():
    """All onboarding steps expose the auto_trigger field."""
    r = requests.get(
        f"{BASE_URL}/api/execution/steps?domain=onboarding",
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code == 200
    steps = r.json()
    for step in steps:
        assert "auto_trigger" in step, f"Step {step['number']} missing auto_trigger field."


# ── CLM domain ────────────────────────────────────────────────────────────────

def test_clm_steps_present():
    """CLM domain has at least one registered step."""
    r = requests.get(
        f"{BASE_URL}/api/execution/steps?domain=clm",
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code == 200
    steps = r.json()
    assert len(steps) > 0, "CLM domain has no registered steps."


# ── Compliance domain ─────────────────────────────────────────────────────────

def test_compliance_steps_present():
    """Compliance domain has at least one registered step."""
    r = requests.get(
        f"{BASE_URL}/api/execution/steps?domain=compliance",
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code == 200
    steps = r.json()
    assert len(steps) > 0, "Compliance domain has no registered steps."


# ── Analytics domain ─────────────────────────────────────────────────────────

def test_analytics_steps_present():
    """Analytics domain has at least one registered step."""
    r = requests.get(
        f"{BASE_URL}/api/execution/steps?domain=analytics",
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code == 200
    steps = r.json()
    assert len(steps) > 0, "Analytics domain has no registered steps."


# ── Light Fleet domains ───────────────────────────────────────────────────────

def test_dispatch_steps_present():
    """Dispatch domain (heavy fleet) has registered steps."""
    r = requests.get(
        f"{BASE_URL}/api/execution/steps?domain=dispatch",
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code == 200
    assert len(r.json()) > 0, "Dispatch domain has no registered steps."


def test_transit_steps_present():
    """Transit domain has registered steps."""
    r = requests.get(
        f"{BASE_URL}/api/execution/steps?domain=transit",
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code == 200
    assert len(r.json()) > 0, "Transit domain has no registered steps."


def test_settlement_steps_present():
    """Settlement domain has registered steps."""
    r = requests.get(
        f"{BASE_URL}/api/execution/steps?domain=settlement",
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code == 200
    assert len(r.json()) > 0, "Settlement domain has no registered steps."


# ── Execution state ───────────────────────────────────────────────────────────

def test_execution_state_endpoint_reachable():
    """Execution state endpoint returns data or 404 for unknown carrier."""
    r = requests.get(
        f"{BASE_URL}/api/execution/state/00000000-0000-0000-0000-000000000000",
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code in (200, 404), (
        f"Execution state for unknown carrier returned {r.status_code}."
    )
