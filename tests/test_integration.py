"""Integration, concurrency & data integrity testing — Phase 2 + Phase 4.

Covers the executive QA blueprint:
  Phase 2: Telemetry avalanche, agent race conditions, heavy process timeouts
  Phase 4: End-to-end event tracing, malformed email/webhook resilience

Run:
    pytest tests/test_integration.py -v
"""
import concurrent.futures
import time
import requests

BASE_URL = "https://three-lakes-logistics-api.onrender.com"
API_TOKEN = "taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE"
HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {API_TOKEN}"}


def _ping_telemetry(i: int) -> tuple[int, int]:
    """Single telemetry ping — returns (index, status_code)."""
    r = requests.post(
        f"{BASE_URL}/api/telemetry/ping",
        json={
            "carrier_id": f"burst-carrier-{i:03d}",
            "truck_id": f"burst-truck-{i:03d}",
            "eld_provider": "samsara",
            "lat": 41.8781 + (i * 0.001),
            "lng": -87.6298 - (i * 0.001),
            "speed_mph": 55.0,
            "heading_deg": 90.0,
        },
        headers=HEADERS,
        timeout=20,
    )
    return i, r.status_code


# ── Phase 2: Telemetry Avalanche ──────────────────────────────────────────────

def test_telemetry_burst_20_concurrent():
    """20 simultaneous telemetry pings — no 5xx under write-heavy load."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(_ping_telemetry, range(20)))

    failures = [(i, s) for i, s in results if s >= 500]
    assert not failures, (
        f"Server errors during telemetry burst: {failures}. "
        "Database locking or memory leak under concurrent write load."
    )
    successes = sum(1 for _, s in results if s == 200)
    assert successes >= 18, (
        f"Only {successes}/20 telemetry pings succeeded — throughput too low."
    )


def test_telemetry_burst_status_codes_all_4xx_or_2xx():
    """10 concurrent pings — every response must be 2xx or 4xx, never 5xx."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(_ping_telemetry, range(100, 110)))

    server_errors = [(i, s) for i, s in results if s >= 500]
    assert not server_errors, f"5xx during concurrent telemetry: {server_errors}"


# ── Phase 2: Agent Race Conditions ────────────────────────────────────────────

def _run_agent(agent: str) -> tuple[str, int]:
    r = requests.post(
        f"{BASE_URL}/api/agents/{agent}/run",
        json={},
        headers=HEADERS,
        timeout=30,
    )
    return agent, r.status_code


def test_concurrent_agent_runs_no_crash():
    """3 agents fired simultaneously — no 5xx crashes or queue corruption."""
    agents = ["beacon", "sonny", "naomi"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(_run_agent, agents))

    crashes = [(a, s) for a, s in results if s >= 500]
    assert not crashes, (
        f"Agent race condition caused server crash: {crashes}. "
        "Worker queues may be corrupting under concurrent execution."
    )


def test_agent_list_reachable():
    """Agent registry responds correctly — all known agents registered."""
    d = requests.get(f"{BASE_URL}/api/agents/list", headers=HEADERS, timeout=15).json()
    agents = d.get("agents", [])
    assert len(agents) > 0, "No agents registered in registry"
    assert "beacon" in agents or "bond_courier" in agents, (
        f"Expected core agents missing. Got: {agents}"
    )


# ── Phase 2: Heavy Process Timeouts ──────────────────────────────────────────

def test_compliance_and_analytics_concurrent_no_timeout():
    """Compliance sweep + analytics trigger fired simultaneously → no 502/504."""
    def compliance():
        return requests.post(
            f"{BASE_URL}/api/triggers/compliance",
            json={"carrier_ids": []},
            headers=HEADERS,
            timeout=30,
        ).status_code

    def analytics():
        return requests.post(
            f"{BASE_URL}/api/triggers/analytics",
            json={},
            headers=HEADERS,
            timeout=30,
        ).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(compliance)
        f2 = pool.submit(analytics)
        s1, s2 = f1.result(), f2.result()

    assert s1 not in (502, 504), f"Compliance sweep gateway timeout under load: {s1}"
    assert s2 not in (502, 504), f"Analytics trigger gateway timeout under load: {s2}"


def test_dat_load_board_reachable():
    """DAT load board fetch endpoint is reachable — no 5xx hanging."""
    r = requests.post(
        f"{BASE_URL}/api/loads/fetch-dat",
        json={"origin": "Chicago, IL", "destination": "Detroit, MI", "equipment": "dry_van"},
        headers=HEADERS,
        timeout=30,
    )
    assert r.status_code < 500, (
        f"DAT load board fetch returned {r.status_code}. "
        "External API integration may be hanging under concurrent load."
    )


# ── Phase 4: End-to-End Event Tracing ────────────────────────────────────────

def test_twilio_webhook_sms_trace():
    """Simulated inbound SMS to Twilio webhook — server processes without crashing."""
    r = requests.post(
        f"{BASE_URL}/api/comms/webhook/twilio",
        data={
            "From": "+13135550001",
            "To": "+13135559000",
            "Body": "Test SMS from integration test",
            "MessageSid": "SM_test_integration_001",
            "AccountSid": "AC_test_account",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    assert r.status_code < 500, (
        f"Twilio SMS webhook crashed (got {r.status_code}). "
        "End-to-end SMS → database event trace broken."
    )


def test_adobe_sign_callback_event_trace():
    """Simulate Adobe Sign agreement event — parsing does not crash server."""
    r = requests.post(
        f"{BASE_URL}/api/webhooks/adobe/agreement-signed",
        json={
            "event": "AGREEMENT_ACTION_COMPLETED",
            "agreement": {
                "id": "test-agreement-integration-001",
                "name": "3 Lakes Carrier Agreement",
                "status": "SIGNED",
            },
        },
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    assert r.status_code < 500, (
        f"Adobe Sign callback crashed server (got {r.status_code}). "
        "Carrier intake pipeline may halt on delayed signatures."
    )


def test_email_parse_malformed_nested_mime():
    """Malformed MIME-style payload to email parse → graceful 4xx, never 500."""
    r = requests.post(
        f"{BASE_URL}/api/email/MALFORMED-MIME-TEST/parse-rate-confirmation",
        json={
            "raw": "------=_Part_0_\r\nContent-Type: text/plain\r\n\r\n" + ("X" * 5000),
            "attachments": [{"filename": None, "data": "\x00\xff\xfe"}],
        },
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code < 500, (
        f"Malformed MIME email parse crashed server (got {r.status_code})."
    )


def test_email_log_reachable():
    """Email log endpoint is reachable and returns structured data."""
    r = requests.get(f"{BASE_URL}/api/email-log", headers=HEADERS, timeout=15)
    assert r.status_code == 200, f"Email log unreachable: {r.status_code}"
    d = r.json()
    assert isinstance(d, (list, dict)), f"Unexpected email log shape: {type(d)}"
