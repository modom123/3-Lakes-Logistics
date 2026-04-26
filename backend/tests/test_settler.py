"""Unit tests for settler.py pay calculation logic (no DB required)."""
from unittest.mock import MagicMock, patch

import pytest
import app.agents.settler as settler_mod


@pytest.fixture
def mock_loads():
    return [
        {"id": "l1", "load_number": "L001", "rate_total": 2500.00, "miles": 800,
         "origin_city": "Chicago", "dest_city": "Atlanta", "delivery_at": "2026-04-21T18:00:00Z"},
        {"id": "l2", "load_number": "L002", "rate_total": 1800.00, "miles": 550,
         "origin_city": "Atlanta", "dest_city": "Miami", "delivery_at": "2026-04-23T12:00:00Z"},
    ]


def _make_qb(data):
    qb = MagicMock()
    qb.execute.return_value = MagicMock(data=data)
    qb.select.return_value = qb
    qb.eq.return_value = qb
    qb.gte.return_value = qb
    qb.lte.return_value = qb
    qb.ilike.return_value = qb
    qb.order.return_value = qb
    qb.limit.return_value = qb
    return qb


def test_calc_driver_payout_gross(mock_loads):
    """Driver gross should be 72% of sum of rates."""
    sb = MagicMock()
    sb.table.return_value = _make_qb(mock_loads)

    with patch("app.agents.settler.get_supabase", return_value=sb):
        result = settler_mod.calc_driver_payout("driver-1", "2026-04-21", "2026-04-27")

    total_rate = 2500 + 1800  # 4300
    assert result["gross_rate"] == 4300.0
    assert result["driver_gross"] == round(4300 * 0.72, 2)
    assert result["loads_delivered"] == 2
    assert result["total_miles"] == 1350


def test_calc_driver_payout_escrow(mock_loads):
    """Escrow deduction is $50 when loads exist, $0 when no loads."""
    sb_with = MagicMock()
    sb_with.table.return_value = _make_qb(mock_loads)
    sb_empty = MagicMock()
    sb_empty.table.return_value = _make_qb([])

    with patch("app.agents.settler.get_supabase", return_value=sb_with):
        r_with = settler_mod.calc_driver_payout("driver-1", "2026-04-21", "2026-04-27")

    with patch("app.agents.settler.get_supabase", return_value=sb_empty):
        r_empty = settler_mod.calc_driver_payout("driver-1", "2026-04-21", "2026-04-27")

    assert r_with["escrow_deduction"] == 50.0
    assert r_empty["escrow_deduction"] == 0.0


def test_calc_driver_payout_net(mock_loads):
    """Net pay = driver_gross - fuel_advances - escrow + lumper + detention."""
    sb = MagicMock()
    sb.table.return_value = _make_qb(mock_loads)

    with patch("app.agents.settler.get_supabase", return_value=sb):
        result = settler_mod.calc_driver_payout("driver-1", "2026-04-21", "2026-04-27")

    expected_net = round(result["driver_gross"] - result["fuel_advances"] - result["escrow_deduction"]
                         + result["lumper_reimbursements"] + result["detention_pay"], 2)
    assert result["net_pay"] == expected_net


def test_dispatch_fee():
    """Dispatch fee should be 8% of gross rate."""
    sb = MagicMock()
    qb = _make_qb([{"rate_total": 1000, "miles": 300, "origin_city": "A", "dest_city": "B", "delivery_at": "2026-04-21"}])
    sb.table.return_value = qb

    with patch("app.agents.settler.get_supabase", return_value=sb):
        result = settler_mod.calc_driver_payout("driver-1", "2026-04-21", "2026-04-27")

    assert result["dispatch_fee"] == round(1000 * 0.08, 2)


def test_initiate_ach_skips_zero():
    """ACH should skip when amount is zero or negative."""
    with patch("app.agents.settler.get_settings") as mock_settings:
        mock_settings.return_value.stripe_secret_key = "sk_test_abc"
        result = settler_mod.initiate_ach(
            "carrier-1", "driver-1", 0.0,
            {"week": ["2026-04-21", "2026-04-27"], "loads_delivered": 0}
        )
    assert result["status"] == "skipped"
    assert result["reason"] == "zero_or_negative_amount"
