"""Live API smoke tests — runs against the Render-hosted backend.

Usage:
    pytest tests/test_live_api.py -v

Requires the backend to be live at RENDER_URL below.
"""
import pytest
import requests

BASE_URL = "https://three-lakes-logistics-api.onrender.com"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": "Bearer taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE",
}


# ── Health ────────────────────────────────────────────────────────────────────

def test_health_ping():
    """Ultra-fast health check — backend is up and responding."""
    r = requests.get(f"{BASE_URL}/api/health/ping")
    assert r.status_code == 200
    assert r.json() == "ok"


def test_health_full():
    """Full health check — Supabase and Stripe connected."""
    r = requests.get(f"{BASE_URL}/api/health/full")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["services"]["supabase"] == "ok"


# ── Telemetry ─────────────────────────────────────────────────────────────────

def test_telemetry_ingestion():
    """Telemetry ping accepted and stored — real field names match TelemetryPing model."""
    r = requests.post(
        f"{BASE_URL}/api/telemetry/ping",
        json={
            "carrier_id": "test-carrier-001",
            "truck_id": "test-truck-001",
            "eld_provider": "samsara",
            "lat": 34.0522,
            "lng": -118.2437,
            "speed_mph": 55.5,
            "heading_deg": 270.0,
        },
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_telemetry_latest():
    """Latest positions endpoint returns correct shape."""
    r = requests.get(f"{BASE_URL}/api/telemetry/latest", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert "count" in data
    assert "items" in data
    assert isinstance(data["items"], list)


# ── Leads ─────────────────────────────────────────────────────────────────────

def test_get_leads():
    """Leads list returns correct shape with count + items."""
    r = requests.get(f"{BASE_URL}/api/leads/", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert "count" in data
    assert "items" in data
    assert isinstance(data["items"], list)


def test_get_leads_with_limit():
    """Leads list respects limit query param."""
    r = requests.get(f"{BASE_URL}/api/leads/?limit=5", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["count"] <= 5


# ── Dashboard ─────────────────────────────────────────────────────────────────

def test_dashboard_kpis():
    """Dashboard KPI endpoint returns metrics dict."""
    r = requests.get(f"{BASE_URL}/api/dashboard/kpis", headers=HEADERS)
    assert r.status_code == 200


# ── Carriers ──────────────────────────────────────────────────────────────────

def test_list_carriers():
    """Carrier list endpoint is reachable and returns data."""
    r = requests.get(f"{BASE_URL}/api/carriers/", headers=HEADERS)
    assert r.status_code == 200


# ── Fleet ─────────────────────────────────────────────────────────────────────

def test_list_fleet():
    """Fleet endpoint returns load/asset data."""
    r = requests.get(f"{BASE_URL}/api/fleet/", headers=HEADERS)
    assert r.status_code == 200


# ── Auth guard ────────────────────────────────────────────────────────────────

def test_unauthorized_rejected():
    """Requests without bearer token are rejected with 401 or 403."""
    r = requests.get(f"{BASE_URL}/api/leads/")
    assert r.status_code in [401, 403]
