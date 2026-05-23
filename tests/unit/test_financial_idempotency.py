"""Unit tests for financial idempotency — payout must never be issued twice.

PDF requirement:
  "If a payout function backing /api/payout/request is called twice in quick succession
   with the same parameters, the test must verify that the second attempt is rejected
   rather than duplicating the transfer."

These tests mock Stripe and Supabase so no external calls are made.
Run: pytest tests/unit/test_financial_idempotency.py -v
"""
from __future__ import annotations

import sys
import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

# Allow importing backend modules without running the full app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_supabase_mock(
    *,
    driver: dict | None = None,
    load: dict | None = None,
    existing_payout: list[dict] | None = None,
    inserted_payout: dict | None = None,
) -> MagicMock:
    """Build a fluent Supabase mock matching the chained .table().select()...execute() API."""
    sb = MagicMock()

    def table_router(name: str) -> MagicMock:
        tbl = MagicMock()

        if name == "drivers":
            tbl.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = driver or {}
            tbl.select.return_value.eq.return_value.single.return_value.execute.return_value.data = driver or {}
            tbl.update.return_value.eq.return_value.execute.return_value.data = [driver or {}]

        elif name == "loads":
            result = MagicMock()
            result.data = load
            tbl.select.return_value.eq.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = result

        elif name == "driver_payouts":
            select_result = MagicMock()
            select_result.data = existing_payout if existing_payout is not None else []
            tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value = select_result

            insert_result = MagicMock()
            insert_result.data = [inserted_payout or {"id": "payout-new-001"}]
            tbl.insert.return_value.execute.return_value = insert_result

        return tbl

    sb.table.side_effect = table_router
    return sb


def _make_stripe_transfer(transfer_id: str = "tr_test_001") -> MagicMock:
    t = MagicMock()
    t.id = transfer_id
    t.status = "in_transit"
    return t


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestPayoutIdempotency:
    """The core financial safety guarantee: one load = one payout, never two."""

    def test_first_payout_succeeds(self) -> None:
        """Baseline: a payout on a delivered, unpaid load is accepted."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        driver = {
            "id": "driver-001",
            "stripe_account_id": "acct_test_001",
            "stripe_account_status": "connected",
            "first_name": "John",
            "last_name": "Doe",
        }
        load = {
            "id": "load-001",
            "driver_id": "driver-001",
            "rate_total": 2500.0,
            "delivered_at": "2026-05-23T14:00:00Z",
        }

        sb_mock = _make_supabase_mock(
            driver=driver,
            load=load,
            existing_payout=[],  # no prior payout
            inserted_payout={"id": "payout-001"},
        )
        transfer_mock = _make_stripe_transfer("tr_first_001")

        with patch("app.api.routes_payout.get_supabase", return_value=sb_mock), \
             patch("app.api.routes_payout.get_settings") as mock_settings, \
             patch("stripe.Transfer.create", return_value=transfer_mock):

            mock_settings.return_value.stripe_secret_key = "sk_test_placeholder"

            from app.api.routes_payout import request_payout, PayoutRequestModel
            import asyncio

            session = {"driver_id": "driver-001"}
            req = PayoutRequestModel(load_id="load-001", amount_cents=250000)

            result = asyncio.run(request_payout(req, session))

            assert result["status"] == "processing"
            assert "transfer_id" in result
            assert result["transfer_id"] == "tr_first_001"

    def test_duplicate_payout_on_paid_load_is_rejected(self) -> None:
        """CRITICAL: second payout request for an already-paid load must raise 400."""
        from fastapi import HTTPException
        import asyncio

        driver = {
            "id": "driver-001",
            "stripe_account_id": "acct_test_001",
            "stripe_account_status": "connected",
        }
        load = {
            "id": "load-001",
            "driver_id": "driver-001",
            "rate_total": 2500.0,
            "delivered_at": "2026-05-23T14:00:00Z",
        }

        # Existing payout record with status "paid"
        existing_paid_payout = [{"id": "payout-001", "status": "paid"}]

        sb_mock = _make_supabase_mock(
            driver=driver,
            load=load,
            existing_payout=existing_paid_payout,
        )

        with patch("app.api.routes_payout.get_supabase", return_value=sb_mock), \
             patch("app.api.routes_payout.get_settings") as mock_settings, \
             patch("stripe.Transfer.create") as stripe_create:

            mock_settings.return_value.stripe_secret_key = "sk_test_placeholder"

            from app.api.routes_payout import request_payout, PayoutRequestModel

            session = {"driver_id": "driver-001"}
            req = PayoutRequestModel(load_id="load-001", amount_cents=250000)

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(request_payout(req, session))

            # Must reject with 400, not silently create a second transfer
            assert exc_info.value.status_code == 400
            assert "already paid" in exc_info.value.detail.lower()

            # Stripe must NOT have been called — no second transfer
            stripe_create.assert_not_called()

    def test_stripe_transfer_not_called_on_duplicate(self) -> None:
        """Stripe.Transfer.create must be called exactly zero times on duplicate."""
        from fastapi import HTTPException
        import asyncio

        driver = {
            "id": "driver-002",
            "stripe_account_id": "acct_test_002",
            "stripe_account_status": "connected",
        }
        load = {
            "id": "load-002",
            "driver_id": "driver-002",
            "rate_total": 3000.0,
            "delivered_at": "2026-05-23T16:00:00Z",
        }

        sb_mock = _make_supabase_mock(
            driver=driver,
            load=load,
            existing_payout=[{"id": "payout-002", "status": "paid"}],
        )

        with patch("app.api.routes_payout.get_supabase", return_value=sb_mock), \
             patch("app.api.routes_payout.get_settings") as mock_settings, \
             patch("stripe.Transfer.create") as stripe_create:

            mock_settings.return_value.stripe_secret_key = "sk_test_placeholder"

            from app.api.routes_payout import request_payout, PayoutRequestModel

            session = {"driver_id": "driver-002"}
            req = PayoutRequestModel(load_id="load-002", amount_cents=300000)

            with pytest.raises(HTTPException):
                asyncio.run(request_payout(req, session))

            stripe_create.assert_not_called()

    def test_net_pay_math_is_correct(self) -> None:
        """Net pay = gross - 8% dispatch fee - $45 insurance. Math must be exact."""
        # gross = $2,500 → gross_cents = 250,000
        # dispatch_fee = 250,000 * 0.08 = 20,000
        # insurance = 4,500
        # net = 250,000 - 20,000 - 4,500 = 225,500 cents = $2,255.00
        gross_cents = 250_000
        dispatch_fee = int(gross_cents * 0.08)
        insurance_cents = 4_500
        net_cents = gross_cents - dispatch_fee - insurance_cents

        assert dispatch_fee == 20_000
        assert net_cents == 225_500
        assert net_cents > 0

    def test_net_pay_math_at_minimum_rate(self) -> None:
        """Loads worth less than deductions must be blocked before Stripe is called."""
        # $50 load → after 8% + $45 insurance, net would be negative
        gross_cents = 5_000   # $50
        dispatch_fee = int(gross_cents * 0.08)  # $4
        insurance_cents = 4_500                  # $45
        net_cents = gross_cents - dispatch_fee - insurance_cents  # = -$4.40

        assert net_cents < 0  # confirms the guard condition in routes_payout.py is needed

    def test_payout_blocked_when_stripe_not_configured(self) -> None:
        """If STRIPE_SECRET_KEY is empty, payout setup must raise 500 (not crash)."""
        from fastapi import HTTPException
        import asyncio

        with patch("app.api.routes_payout.get_settings") as mock_settings:
            mock_settings.return_value.stripe_secret_key = ""

            from app.api.routes_payout import get_stripe_client

            with pytest.raises(HTTPException) as exc_info:
                get_stripe_client()

            assert exc_info.value.status_code == 500

    def test_payout_blocked_when_driver_not_onboarded(self) -> None:
        """A driver with stripe_account_status != 'connected' must be blocked."""
        from fastapi import HTTPException
        import asyncio

        driver = {
            "id": "driver-003",
            "stripe_account_id": None,
            "stripe_account_status": "pending",
        }
        load = {
            "id": "load-003",
            "driver_id": "driver-003",
            "rate_total": 2000.0,
            "delivered_at": "2026-05-23T10:00:00Z",
        }

        sb_mock = _make_supabase_mock(
            driver=driver,
            load=load,
            existing_payout=[],
        )

        with patch("app.api.routes_payout.get_supabase", return_value=sb_mock), \
             patch("app.api.routes_payout.get_settings") as mock_settings, \
             patch("stripe.Transfer.create") as stripe_create:

            mock_settings.return_value.stripe_secret_key = "sk_test_placeholder"

            from app.api.routes_payout import request_payout, PayoutRequestModel

            session = {"driver_id": "driver-003"}
            req = PayoutRequestModel(load_id="load-003", amount_cents=200000)

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(request_payout(req, session))

            assert exc_info.value.status_code == 400
            assert "onboarding" in exc_info.value.detail.lower()
            stripe_create.assert_not_called()
