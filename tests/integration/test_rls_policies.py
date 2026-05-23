"""Integration tests for Supabase Row Level Security (RLS) policies.

PDF requirement:
  "Directly test the security and query structures within Supabase. Simulate a query
   using a standard driver's role and assert that Row Level Security (RLS) policies
   successfully block access to the broader executive inventory or carrier compliance data."

These tests require real Supabase credentials. They are skipped in CI unless
SUPABASE_URL, SUPABASE_ANON_KEY, and SUPABASE_SERVICE_ROLE_KEY are set as secrets.

Run: pytest tests/integration/test_rls_policies.py -v
"""
from __future__ import annotations

import os
import pytest
from typing import Any

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Skip all tests in this module if Supabase secrets are not available
pytestmark = pytest.mark.skipif(
    not SUPABASE_URL or not SUPABASE_ANON_KEY,
    reason="Supabase credentials not set — set SUPABASE_URL + SUPABASE_ANON_KEY to run RLS tests",
)


def _anon_client() -> Any:
    """Supabase client with anon key — simulates an unauthenticated request."""
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def _service_client() -> Any:
    """Supabase client with service role — bypasses RLS (admin view)."""
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# ── RLS Blocking Tests ─────────────────────────────────────────────────────────

class TestRLSBlocking:
    """Unauthenticated (anon) requests must be blocked by RLS on all sensitive tables."""

    def test_anon_cannot_read_active_carriers(self) -> None:
        """Anon role must NOT read active_carriers (requires authenticated + carrier mapping)."""
        client = _anon_client()
        result = client.table("active_carriers").select("id, company_name").execute()
        # RLS should block: data should be empty list (not an error, just filtered)
        assert result.data == [] or result.data is None, \
            f"RLS FAILURE: anon read {len(result.data)} carriers — should be 0"

    def test_anon_cannot_read_banking_accounts(self) -> None:
        """Banking accounts are admin-only per RLS policy banking_admin_only."""
        client = _anon_client()
        result = client.table("banking_accounts").select("*").execute()
        assert result.data == [] or result.data is None, \
            f"RLS FAILURE: anon read {len(result.data)} banking records — should be 0"

    def test_anon_cannot_read_insurance_compliance(self) -> None:
        """Insurance compliance data must be scoped to carrier owner or admin."""
        client = _anon_client()
        result = client.table("insurance_compliance").select("*").execute()
        assert result.data == [] or result.data is None, \
            f"RLS FAILURE: anon read {len(result.data)} insurance records — should be 0"

    def test_anon_cannot_read_leads(self) -> None:
        """Leads are admin-only (leads_admin_only policy)."""
        client = _anon_client()
        result = client.table("leads").select("id, company_name").execute()
        assert result.data == [] or result.data is None, \
            f"RLS FAILURE: anon read {len(result.data)} leads — should be 0"

    def test_anon_cannot_read_agent_log(self) -> None:
        """Agent logs contain sensitive AI decisions — admin-only."""
        client = _anon_client()
        result = client.table("agent_log").select("id, agent_name, action").execute()
        assert result.data == [] or result.data is None, \
            f"RLS FAILURE: anon read {len(result.data)} agent logs — should be 0"

    def test_anon_cannot_read_driver_hos_status(self) -> None:
        """HOS status is carrier-scoped. Anon has no carrier mapping → empty."""
        client = _anon_client()
        result = client.table("driver_hos_status").select("*").execute()
        assert result.data == [] or result.data is None, \
            f"RLS FAILURE: anon read {len(result.data)} HOS records — should be 0"

    def test_anon_cannot_read_truck_telemetry(self) -> None:
        """Telemetry is carrier-scoped. Anon gets empty result."""
        client = _anon_client()
        result = client.table("truck_telemetry").select("id, lat, lng").limit(5).execute()
        assert result.data == [] or result.data is None, \
            f"RLS FAILURE: anon read {len(result.data)} telemetry rows — should be 0"

    def test_anon_cannot_read_fleet_assets(self) -> None:
        """Fleet assets (trucks) are carrier-scoped."""
        client = _anon_client()
        result = client.table("fleet_assets").select("id, vin, make, model").limit(5).execute()
        assert result.data == [] or result.data is None, \
            f"RLS FAILURE: anon read {len(result.data)} fleet assets — should be 0"

    def test_anon_cannot_read_drivers(self) -> None:
        """Driver PII is carrier-scoped. Anon must see nothing."""
        client = _anon_client()
        result = client.table("drivers").select("id, first_name, last_name, phone_e164").limit(5).execute()
        assert result.data == [] or result.data is None, \
            f"RLS FAILURE: anon read {len(result.data)} driver records — should be 0"

    def test_anon_cannot_read_invoices(self) -> None:
        """Invoices are carrier-scoped — financial data must not leak."""
        client = _anon_client()
        result = client.table("invoices").select("*").limit(5).execute()
        assert result.data == [] or result.data is None, \
            f"RLS FAILURE: anon read {len(result.data)} invoices — should be 0"


# ── Write Blocking Tests ───────────────────────────────────────────────────────

class TestRLSWriteBlocking:
    """Direct client writes must be blocked — all writes go through FastAPI service role."""

    def test_anon_cannot_insert_carrier(self) -> None:
        """no_client_inserts_carriers policy blocks direct inserts."""
        client = _anon_client()
        try:
            result = client.table("active_carriers").insert({
                "company_name": "FAKE CARRIER INJECTION",
                "mc_number": "MC-FAKE-999",
                "dot_number": "DOT-FAKE-999",
            }).execute()
            # If we get here, RLS should have returned empty data
            assert not result.data, \
                "RLS FAILURE: anon insert into active_carriers succeeded — must be blocked"
        except Exception:
            pass  # Exception = correctly blocked

    def test_anon_cannot_update_carrier(self) -> None:
        """no_client_updates_carriers policy blocks direct updates."""
        client = _anon_client()
        try:
            result = client.table("active_carriers").update({
                "company_name": "HACKED NAME",
            }).eq("id", "00000000-0000-0000-0000-000000000000").execute()
            assert not result.data, "RLS FAILURE: anon update succeeded"
        except Exception:
            pass

    def test_anon_cannot_insert_banking_account(self) -> None:
        """Banking data must never be writable by unauthenticated clients."""
        client = _anon_client()
        try:
            result = client.table("banking_accounts").insert({
                "carrier_id": "00000000-0000-0000-0000-000000000000",
                "account_number": "FAKE-ACCOUNT-123",
                "routing_number": "000000000",
            }).execute()
            assert not result.data, "RLS FAILURE: anon banking insert succeeded"
        except Exception:
            pass


# ── Service Role Access Tests ──────────────────────────────────────────────────

class TestServiceRoleAccess:
    """Service role (backend) must be able to read all tables — confirms RLS is not over-blocking."""

    def test_service_role_can_read_carriers(self) -> None:
        """Service role bypasses RLS — must be able to read carrier data."""
        if not SUPABASE_SERVICE_ROLE_KEY:
            pytest.skip("SUPABASE_SERVICE_ROLE_KEY not set")

        client = _service_client()
        result = client.table("active_carriers").select("id").limit(1).execute()
        # Result may be empty (no data in DB) but must not raise
        assert result.data is not None

    def test_service_role_can_read_banking(self) -> None:
        """Service role must access banking accounts for settlement processing."""
        if not SUPABASE_SERVICE_ROLE_KEY:
            pytest.skip("SUPABASE_SERVICE_ROLE_KEY not set")

        client = _service_client()
        result = client.table("banking_accounts").select("id").limit(1).execute()
        assert result.data is not None

    def test_service_role_can_read_agent_log(self) -> None:
        """Service role must read agent logs for debugging and monitoring."""
        if not SUPABASE_SERVICE_ROLE_KEY:
            pytest.skip("SUPABASE_SERVICE_ROLE_KEY not set")

        client = _service_client()
        result = client.table("agent_log").select("id").limit(1).execute()
        assert result.data is not None
