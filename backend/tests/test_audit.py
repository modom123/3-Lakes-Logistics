"""Unit tests for audit.py fuel advance decision logic."""
from unittest.mock import MagicMock, patch

import app.agents.audit as audit_mod


def _sb_with_load(has_load=True, outstanding=0):
    sb = MagicMock()

    def table_side(name):
        qb = MagicMock()
        if name == "loads":
            qb.execute.return_value = MagicMock(
                data=[{"id": "l1"}] if has_load else []
            )
        elif name == "agent_log" and outstanding > 0:
            qb.execute.return_value = MagicMock(data=[{"id": str(i)} for i in range(outstanding)])
        else:
            qb.execute.return_value = MagicMock(data=[])
        qb.select.return_value = qb
        qb.eq.return_value = qb
        qb.in_.return_value = qb
        qb.limit.return_value = qb
        return qb

    sb.table.side_effect = table_side
    return sb


def test_no_active_load_denied():
    with patch("app.agents.audit.get_supabase", return_value=_sb_with_load(has_load=False)):
        result = audit_mod.decide_advance("driver-1", 500, 2000)
    assert result["approved"] is False
    assert "no_active_load" in result["reason"]


def test_within_cap_approved():
    with patch("app.agents.audit.get_supabase", return_value=_sb_with_load(has_load=True)):
        result = audit_mod.decide_advance("driver-1", 500, 2000)  # 500 <= 40% of 2000 = 800
    assert result["approved"] is True


def test_exceeds_cap_denied():
    with patch("app.agents.audit.get_supabase", return_value=_sb_with_load(has_load=True)):
        result = audit_mod.decide_advance("driver-1", 900, 2000)  # 900 > 800 cap
    assert result["approved"] is False
    assert "40%" in result["reason"]


def test_floor_500():
    with patch("app.agents.audit.get_supabase", return_value=_sb_with_load(has_load=True)):
        result = audit_mod.decide_advance("driver-1", 499, 500)  # cap = max(200, 500) = 500
    assert result["approved"] is True
