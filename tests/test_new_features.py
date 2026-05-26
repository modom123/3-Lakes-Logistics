"""Tests for features added since initial launch.

Covers:
  - Dashboard loads CRUD (POST, PATCH, GET list) — used by Dispatch Board
  - Dashboard invoices CRUD (POST, PATCH, DELETE)
  - Dispatch Board: driver assignment via PATCH loads/{id}
  - Driver Management: admin create / list / delete drivers
  - Fleet Management: add truck, delete truck, public loads, public stats

Configuration:
  TEST_API_BASE_URL  — override base URL (default: http://localhost:8080)
  TEST_API_TOKEN     — override bearer token

Run against local backend:
    uvicorn app.main:app --reload --port 8080  # in backend/
    pytest tests/test_new_features.py -v

Run against live API (if accessible from your network):
    TEST_API_BASE_URL=https://three-lakes-logistics-api.onrender.com \
    pytest tests/test_new_features.py -v
"""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("TEST_API_BASE_URL", "http://localhost:8080")
API_TOKEN = os.environ.get("TEST_API_TOKEN", "taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE")
HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {API_TOKEN}"}

# Unique suffix so parallel runs don't collide
_RUN = uuid.uuid4().hex[:8]


# ── Module-level availability guard ──────────────────────────────────────────

def _api_alive() -> bool:
    try:
        r = requests.get(f"{BASE_URL}/api/health/ping", timeout=5)
        return r.status_code < 500
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _api_alive(),
    reason=f"API at {BASE_URL} not reachable — start backend or set TEST_API_BASE_URL",
)


# ── Dashboard: Loads ──────────────────────────────────────────────────────────

class TestDashboardLoads:
    """CRUD operations on /api/dashboard/loads."""

    created_load_id: str | None = None

    def test_create_load(self):
        """POST /api/dashboard/loads — creates a new load and returns it."""
        r = requests.post(
            f"{BASE_URL}/api/dashboard/loads",
            json={
                "load_number": f"TEST-{_RUN}",
                "origin_city": "Chicago",
                "origin_state": "IL",
                "dest_city": "Detroit",
                "dest_state": "MI",
                "rate_total": 1500.00,
                "status": "open",
                "broker_name": f"Test Broker {_RUN}",
            },
            headers=HEADERS,
            timeout=20,
        )
        assert r.status_code == 200, f"Create load failed: {r.status_code} {r.text}"
        body = r.json()
        assert body.get("ok") is True, f"Expected ok=true: {body}"
        item = body.get("item", {})
        assert "id" in item, f"No id in response: {item}"
        TestDashboardLoads.created_load_id = item["id"]

    def test_get_loads_list(self):
        """GET /api/dashboard/loads — returns list of loads."""
        r = requests.get(f"{BASE_URL}/api/dashboard/loads", headers=HEADERS, timeout=15)
        assert r.status_code == 200, f"List loads failed: {r.status_code}"
        body = r.json()
        assert isinstance(body, (list, dict)), f"Unexpected shape: {type(body)}"

    def test_patch_load_status(self):
        """PATCH /api/dashboard/loads/{id} — updates status field."""
        if not TestDashboardLoads.created_load_id:
            pytest.skip("No load id from create test")
        r = requests.patch(
            f"{BASE_URL}/api/dashboard/loads/{TestDashboardLoads.created_load_id}",
            json={"status": "booked"},
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 200, f"PATCH load status failed: {r.status_code} {r.text}"
        assert r.json().get("ok") is True

    def test_patch_load_driver_assignment(self):
        """PATCH /api/dashboard/loads/{id} — assigns driver (Dispatch Board assign modal)."""
        if not TestDashboardLoads.created_load_id:
            pytest.skip("No load id from create test")
        r = requests.patch(
            f"{BASE_URL}/api/dashboard/loads/{TestDashboardLoads.created_load_id}",
            json={"driver_name": f"Test Driver {_RUN}", "status": "en_route"},
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 200, f"Driver assignment failed: {r.status_code} {r.text}"
        assert r.json().get("ok") is True

    def test_patch_load_nonexistent_returns_ok(self):
        """PATCH /api/dashboard/loads/{bogus_id} — gracefully handles missing id."""
        fake_id = str(uuid.uuid4())
        r = requests.patch(
            f"{BASE_URL}/api/dashboard/loads/{fake_id}",
            json={"status": "open"},
            headers=HEADERS,
            timeout=15,
        )
        # Supabase update on missing row returns 0 rows but no error
        assert r.status_code < 500, f"Unexpected 5xx on missing load: {r.status_code}"

    def test_patch_load_requires_auth(self):
        """PATCH /api/dashboard/loads/{id} — blocked without bearer token."""
        fake_id = str(uuid.uuid4())
        r = requests.patch(
            f"{BASE_URL}/api/dashboard/loads/{fake_id}",
            json={"status": "open"},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"

    def test_create_load_requires_auth(self):
        """POST /api/dashboard/loads — blocked without bearer token."""
        r = requests.post(
            f"{BASE_URL}/api/dashboard/loads",
            json={"load_number": "NOAUTH"},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"


# ── Dashboard: Invoices ───────────────────────────────────────────────────────

class TestDashboardInvoices:
    """CRUD operations on /api/dashboard/invoices."""

    created_invoice_id: str | None = None

    def test_create_invoice(self):
        """POST /api/dashboard/invoices — creates invoice and returns it."""
        r = requests.post(
            f"{BASE_URL}/api/dashboard/invoices",
            json={
                "invoice_number": f"INV-{_RUN}",
                "amount_due": 2000.00,
                "status": "pending",
                "broker_name": f"Test Broker {_RUN}",
            },
            headers=HEADERS,
            timeout=20,
        )
        assert r.status_code == 200, f"Create invoice failed: {r.status_code} {r.text}"
        body = r.json()
        assert body.get("ok") is True
        item = body.get("item", {})
        assert "id" in item, f"No id in response: {item}"
        TestDashboardInvoices.created_invoice_id = item["id"]

    def test_get_invoices_list(self):
        """GET /api/dashboard/invoices — returns list."""
        r = requests.get(f"{BASE_URL}/api/dashboard/invoices", headers=HEADERS, timeout=15)
        assert r.status_code == 200, f"List invoices failed: {r.status_code}"

    def test_patch_invoice(self):
        """PATCH /api/dashboard/invoices/{id} — updates invoice status."""
        if not TestDashboardInvoices.created_invoice_id:
            pytest.skip("No invoice id from create test")
        r = requests.patch(
            f"{BASE_URL}/api/dashboard/invoices/{TestDashboardInvoices.created_invoice_id}",
            json={"status": "sent"},
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 200, f"PATCH invoice failed: {r.status_code} {r.text}"
        assert r.json().get("ok") is True

    def test_delete_invoice(self):
        """DELETE /api/dashboard/invoices/{id} — removes invoice."""
        if not TestDashboardInvoices.created_invoice_id:
            pytest.skip("No invoice id from create test")
        r = requests.delete(
            f"{BASE_URL}/api/dashboard/invoices/{TestDashboardInvoices.created_invoice_id}",
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 200, f"DELETE invoice failed: {r.status_code} {r.text}"
        assert r.json().get("ok") is True

    def test_delete_invoice_requires_auth(self):
        """DELETE /api/dashboard/invoices/{id} — blocked without bearer token."""
        fake_id = str(uuid.uuid4())
        r = requests.delete(
            f"{BASE_URL}/api/dashboard/invoices/{fake_id}",
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"


# ── Driver Management ─────────────────────────────────────────────────────────

class TestDriverManagement:
    """Admin create / list / delete driver endpoints."""

    created_driver_id: str | None = None
    _carrier_id = "test-carrier-000"

    def test_list_drivers_returns_ok(self):
        """GET /api/driver-auth/list — returns count and items."""
        r = requests.get(f"{BASE_URL}/api/driver-auth/list", headers=HEADERS, timeout=15)
        assert r.status_code == 200, f"List drivers failed: {r.status_code}"
        body = r.json()
        assert "count" in body and "items" in body, f"Unexpected shape: {body}"
        assert isinstance(body["items"], list)

    def test_list_drivers_filter_by_carrier(self):
        """GET /api/driver-auth/list?carrier_id=X — filtered result doesn't crash."""
        r = requests.get(
            f"{BASE_URL}/api/driver-auth/list",
            params={"carrier_id": "nonexistent-carrier-zzz"},
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 200, f"Filtered list failed: {r.status_code}"
        body = r.json()
        assert body["count"] == 0 or isinstance(body["items"], list)

    def test_create_driver_invalid_pin_rejected(self):
        """POST /api/driver-auth/create — PIN != 4 digits returns 400."""
        r = requests.post(
            f"{BASE_URL}/api/driver-auth/create",
            json={
                "carrier_id": self._carrier_id,
                "first_name": "Test",
                "last_name": "Driver",
                "phone": "5550001234",
                "pin": "12",  # too short
            },
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 400, f"Expected 400 for bad PIN, got {r.status_code}"

    def test_create_driver_invalid_phone_rejected(self):
        """POST /api/driver-auth/create — non-numeric phone returns 400."""
        r = requests.post(
            f"{BASE_URL}/api/driver-auth/create",
            json={
                "carrier_id": self._carrier_id,
                "first_name": "Test",
                "last_name": "Driver",
                "phone": "not-a-phone",
                "pin": "1234",
            },
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 400, f"Expected 400 for bad phone, got {r.status_code}"

    def test_create_driver_success(self):
        """POST /api/driver-auth/create — creates driver with valid payload."""
        unique_phone = f"555{_RUN[:7]}"
        r = requests.post(
            f"{BASE_URL}/api/driver-auth/create",
            json={
                "carrier_id": self._carrier_id,
                "first_name": "Test",
                "last_name": f"Driver{_RUN}",
                "phone": unique_phone,
                "pin": "7777",
                "driver_code": f"TST-{_RUN}",
            },
            headers=HEADERS,
            timeout=20,
        )
        assert r.status_code == 200, f"Create driver failed: {r.status_code} {r.text}"
        body = r.json()
        assert body.get("ok") is True
        assert "driver_id" in body
        TestDriverManagement.created_driver_id = body["driver_id"]

    def test_create_driver_duplicate_phone_rejected(self):
        """POST /api/driver-auth/create — duplicate phone returns 409."""
        if not TestDriverManagement.created_driver_id:
            pytest.skip("Depends on successful create")
        unique_phone = f"555{_RUN[:7]}"
        r = requests.post(
            f"{BASE_URL}/api/driver-auth/create",
            json={
                "carrier_id": self._carrier_id,
                "first_name": "Dup",
                "last_name": "Driver",
                "phone": unique_phone,
                "pin": "8888",
            },
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 409, f"Expected 409 for duplicate, got {r.status_code}"

    def test_deactivate_driver(self):
        """DELETE /api/driver-auth/{id} — sets driver status=inactive."""
        if not TestDriverManagement.created_driver_id:
            pytest.skip("No driver id from create test")
        r = requests.delete(
            f"{BASE_URL}/api/driver-auth/{TestDriverManagement.created_driver_id}",
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 200, f"Delete driver failed: {r.status_code} {r.text}"
        assert r.json().get("ok") is True

    def test_list_drivers_requires_auth(self):
        """GET /api/driver-auth/list — blocked without bearer."""
        r = requests.get(
            f"{BASE_URL}/api/driver-auth/list",
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"

    def test_create_driver_requires_auth(self):
        """POST /api/driver-auth/create — blocked without bearer."""
        r = requests.post(
            f"{BASE_URL}/api/driver-auth/create",
            json={
                "carrier_id": "x",
                "first_name": "x",
                "last_name": "x",
                "phone": "5550000001",
                "pin": "1234",
            },
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"


# ── Fleet Management ──────────────────────────────────────────────────────────

class TestFleetManagement:
    """Add / delete fleet assets and public read endpoints."""

    created_fleet_id: str | None = None
    _carrier_id = "test-carrier-fleet-000"
    _truck_id = f"UNIT-{_RUN}"

    def test_public_loads_no_auth_required(self):
        """GET /api/fleet/public/loads — accessible without auth."""
        r = requests.get(f"{BASE_URL}/api/fleet/public/loads", timeout=15)
        assert r.status_code == 200, f"Public loads failed: {r.status_code}"
        body = r.json()
        assert "loads" in body and "count" in body, f"Unexpected shape: {body}"
        assert isinstance(body["loads"], list)

    def test_public_stats_no_auth_required(self):
        """GET /api/fleet/public/stats — accessible without auth, returns counts."""
        r = requests.get(f"{BASE_URL}/api/fleet/public/stats", timeout=15)
        assert r.status_code == 200, f"Public stats failed: {r.status_code}"
        assert isinstance(r.json(), dict)

    def test_add_fleet_asset_missing_carrier_rejected(self):
        """POST /api/fleet/ — missing carrier_id returns 400."""
        r = requests.post(
            f"{BASE_URL}/api/fleet/",
            json={"truck_id": "UNIT-001"},
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"

    def test_add_fleet_asset_missing_truck_id_rejected(self):
        """POST /api/fleet/ — missing truck_id returns 400."""
        r = requests.post(
            f"{BASE_URL}/api/fleet/",
            json={"carrier_id": self._carrier_id},
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"

    def test_add_fleet_asset_success(self):
        """POST /api/fleet/ — adds truck, returns fleet asset with id."""
        r = requests.post(
            f"{BASE_URL}/api/fleet/",
            json={
                "carrier_id": self._carrier_id,
                "truck_id": self._truck_id,
                "trailer_type": "dry_van",
                "year": 2022,
                "make": "Freightliner",
                "model": "Cascadia",
            },
            headers=HEADERS,
            timeout=20,
        )
        assert r.status_code == 200, f"Add fleet asset failed: {r.status_code} {r.text}"
        body = r.json()
        assert body.get("ok") is True
        item = body.get("item", {})
        assert "id" in item, f"No id in response: {item}"
        TestFleetManagement.created_fleet_id = item["id"]

    def test_add_fleet_asset_duplicate_rejected(self):
        """POST /api/fleet/ — duplicate truck_id+carrier returns 409."""
        if not TestFleetManagement.created_fleet_id:
            pytest.skip("Depends on successful add")
        r = requests.post(
            f"{BASE_URL}/api/fleet/",
            json={"carrier_id": self._carrier_id, "truck_id": self._truck_id},
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 409, f"Expected 409 for duplicate, got {r.status_code}"

    def test_update_fleet_status_valid(self):
        """PATCH /api/fleet/{id}/status — valid status update succeeds."""
        if not TestFleetManagement.created_fleet_id:
            pytest.skip("No fleet id from add test")
        r = requests.patch(
            f"{BASE_URL}/api/fleet/{TestFleetManagement.created_fleet_id}/status",
            params={"new_status": "on_load"},
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 200, f"Update fleet status failed: {r.status_code} {r.text}"
        assert r.json().get("ok") is True

    def test_update_fleet_status_invalid_rejected(self):
        """PATCH /api/fleet/{id}/status — invalid status returns 400."""
        if not TestFleetManagement.created_fleet_id:
            pytest.skip("No fleet id from add test")
        r = requests.patch(
            f"{BASE_URL}/api/fleet/{TestFleetManagement.created_fleet_id}/status",
            params={"new_status": "flying"},
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 400, f"Expected 400 for invalid status, got {r.status_code}"

    def test_delete_fleet_asset(self):
        """DELETE /api/fleet/{id} — removes the truck."""
        if not TestFleetManagement.created_fleet_id:
            pytest.skip("No fleet id from add test")
        r = requests.delete(
            f"{BASE_URL}/api/fleet/{TestFleetManagement.created_fleet_id}",
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 200, f"Delete fleet asset failed: {r.status_code} {r.text}"
        assert r.json().get("ok") is True


# ── Dispatch Board: Integration flow ─────────────────────────────────────────

class TestDispatchBoardFlow:
    """End-to-end Dispatch Board: create load → assign driver → advance status."""

    _load_id: str | None = None

    def test_dispatch_create_open_load(self):
        """Create an open load to simulate dispatch board entry."""
        r = requests.post(
            f"{BASE_URL}/api/dashboard/loads",
            json={
                "load_number": f"DISP-{_RUN}",
                "origin_city": "Milwaukee",
                "origin_state": "WI",
                "dest_city": "Indianapolis",
                "dest_state": "IN",
                "rate_total": 1800.00,
                "miles": 310,
                "status": "open",
                "equipment_type": "dry_van",
            },
            headers=HEADERS,
            timeout=20,
        )
        assert r.status_code == 200, f"Create dispatch load failed: {r.status_code} {r.text}"
        item = r.json().get("item", {})
        assert "id" in item
        TestDispatchBoardFlow._load_id = item["id"]

    def test_dispatch_assign_driver(self):
        """PATCH load → assign carrier/driver (Dispatch Board assign modal)."""
        if not TestDispatchBoardFlow._load_id:
            pytest.skip("No load from create test")
        r = requests.patch(
            f"{BASE_URL}/api/dashboard/loads/{TestDispatchBoardFlow._load_id}",
            json={"driver_name": "ABC Trucking LLC", "status": "booked"},
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 200, f"Driver assignment failed: {r.status_code} {r.text}"
        assert r.json().get("ok") is True

    def test_dispatch_advance_to_en_route(self):
        """PATCH load → advance status to en_route (Next button flow)."""
        if not TestDispatchBoardFlow._load_id:
            pytest.skip("No load from create test")
        r = requests.patch(
            f"{BASE_URL}/api/dashboard/loads/{TestDispatchBoardFlow._load_id}",
            json={"status": "en_route"},
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 200, f"Status advance failed: {r.status_code} {r.text}"

    def test_dispatch_advance_to_delivered(self):
        """PATCH load → mark delivered (final status)."""
        if not TestDispatchBoardFlow._load_id:
            pytest.skip("No load from create test")
        r = requests.patch(
            f"{BASE_URL}/api/dashboard/loads/{TestDispatchBoardFlow._load_id}",
            json={"status": "delivered"},
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 200, f"Delivered status failed: {r.status_code} {r.text}"
        assert r.json().get("ok") is True
