"""Tests for penny.py agent — Stripe lifecycle + margin calculations."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_sb(fuel_rows=None, load_row=None, pay_rows=None, inv_rows=None, load_rows=None):
    sb = MagicMock()
    qb = MagicMock()
    qb.select.return_value = qb
    qb.eq.return_value = qb
    qb.gte.return_value = qb
    qb.maybe_single.return_value = qb
    qb.execute.return_value = MagicMock(data=None)

    def _fuel_exec():
        return MagicMock(data=fuel_rows or [])

    def _load_exec():
        return MagicMock(data=load_row)

    def _table(name):
        tbl = MagicMock()
        t = MagicMock()
        t.select.return_value = t
        t.eq.return_value = t
        t.gte.return_value = t
        t.maybe_single.return_value = t
        t.update.return_value = t
        if name == "fuel_card_transactions":
            t.execute.return_value = MagicMock(data=fuel_rows or [])
        elif name == "loads":
            t.execute.return_value = MagicMock(data=load_row)
        elif name == "driver_settlements":
            t.execute.return_value = MagicMock(data=pay_rows or [])
        elif name == "invoices":
            t.execute.return_value = MagicMock(data=inv_rows or [])
        else:
            t.execute.return_value = MagicMock(data=load_rows or [])
        return t

    sb.table.side_effect = _table
    return sb


@patch("app.agents.penny.get_supabase")
@patch("app.agents.penny.log_agent")
def test_margin_preview(mock_log, mock_sb):
    from app.agents.penny import run
    result = run({"action": "margin_preview", "rate_total": 2000, "miles": 500})
    assert result["ok"] is True
    assert result["gross"] == 2000.0
    assert result["driver_pay"] == pytest.approx(1440.0)
    assert result["fuel_est"] == pytest.approx(275.0)
    assert result["margin"] == pytest.approx(285.0)
    assert result["margin_pct"] == pytest.approx(0.1425)


@patch("app.agents.penny.get_supabase")
@patch("app.agents.penny.log_agent")
def test_fuel_cost_track(mock_log, mock_sb):
    mock_sb.return_value = _make_sb(fuel_rows=[{"amount": "120.50"}, {"amount": "80.00"}])
    from app.agents.penny import run
    result = run({"action": "fuel_cost_track", "load_id": "ld-1", "carrier_id": "c-1"})
    assert result["ok"] is True
    assert result["total_fuel"] == pytest.approx(200.50)


@patch("app.agents.penny.get_supabase")
@patch("app.agents.penny.log_agent")
def test_load_margin(mock_log, mock_sb):
    from app.agents.penny import run
    with patch("app.agents.penny.get_supabase") as gsb:
        sb = MagicMock()
        loads_tbl = MagicMock()
        loads_tbl.select.return_value = loads_tbl
        loads_tbl.eq.return_value = loads_tbl
        loads_tbl.maybe_single.return_value = loads_tbl
        loads_tbl.execute.return_value = MagicMock(data={"rate_total": "2000", "miles": "500"})

        settle_tbl = MagicMock()
        settle_tbl.select.return_value = settle_tbl
        settle_tbl.eq.return_value = settle_tbl
        settle_tbl.execute.return_value = MagicMock(data=[{"driver_pay": "1400"}])

        fuel_tbl = MagicMock()
        fuel_tbl.select.return_value = fuel_tbl
        fuel_tbl.eq.return_value = fuel_tbl
        fuel_tbl.execute.return_value = MagicMock(data=[{"amount": "200"}])

        def _table(name):
            if name == "loads":
                return loads_tbl
            if name == "driver_settlements":
                return settle_tbl
            return fuel_tbl

        sb.table.side_effect = _table
        gsb.return_value = sb

        result = run({"action": "load_margin", "load_id": "ld-1",
                       "carrier_id": "c-1", "dispatch_pct": 5})
        assert result["ok"] is True
        assert result["gross"] == pytest.approx(2000.0)
        assert result["driver_pay"] == pytest.approx(1400.0)
        assert result["fuel_cost"] == pytest.approx(200.0)
        assert result["dispatch_fee"] == pytest.approx(100.0)
        assert result["margin"] == pytest.approx(300.0)


@patch("app.agents.penny.get_supabase")
@patch("app.agents.penny.log_agent")
def test_checkout_no_stripe(mock_log, mock_sb):
    """When Stripe is not configured, checkout returns ok=False."""
    from app.agents.penny import run
    cfg = MagicMock()
    cfg.stripe_secret_key = ""
    cfg.stripe_price_founders = ""
    with patch("app.agents.penny.get_settings", return_value=cfg):
        result = run({"action": "checkout", "carrier_id": "c-1",
                      "plan": "standard_5pct", "email": "test@example.com"})
    assert result["action"] == "checkout"
    assert result["checkout_url"] is None
    assert result["ok"] is False


@patch("app.agents.penny.get_supabase")
@patch("app.agents.penny.log_agent")
def test_unknown_action(mock_log, mock_sb):
    from app.agents.penny import run
    result = run({"action": "bogus_action"})
    assert result["ok"] is False
    assert "unknown action" in result["note"]
