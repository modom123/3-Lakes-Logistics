# ─────────────────────────────────────────────────────────────
# File:     tests/test_launch_business.py
# Created:  2026-09-29 22:31 UTC
# Purpose:  Unit tests for launch wiring — pricing, call list, checkout plan.
# ─────────────────────────────────────────────────────────────
"""Offline tests: no Supabase, Stripe, or network access needed."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import app.main  # noqa: E402,F401  — resolves the package's circular imports first
from app import pricing  # noqa: E402
from app.agents.naomi import _dot_age_days  # noqa: E402
from app.agents.penny import _price_for_plan  # noqa: E402
from app.prospecting import call_list  # noqa: E402

# Tuesday 2026-09-29 15:00 UTC = 10:00 Central, 08:00 Pacific
NOW = datetime(2026, 9, 29, 15, 0, tzinfo=timezone.utc)


# ── pricing ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("plan", ["founders", "pro", "standard", "enterprise", "Founders "])
def test_subscription_plans_pay_no_per_load_fee(plan):
    assert pricing.heavy_fee_pct(plan) == 0.0


@pytest.mark.parametrize("plan", ["pay_as_you_go", None, "", "discuss", "unknown"])
def test_non_subscribers_pay_payg_fee(plan):
    assert pricing.heavy_fee_pct(plan) == 0.08


def test_site_prices():
    assert (pricing.FOUNDERS_MONTHLY_USD, pricing.PRO_MONTHLY_USD) == (300, 500)
    assert pricing.LIGHT_FLEET_FEE_PCT == 0.15


class _S:
    stripe_price_founders = "price_f"
    stripe_price_pro = "price_p"


@pytest.mark.parametrize("plan,expected", [
    ("founders", "price_f"), (None, "price_f"), ("pro", "price_p"), ("standard", "price_p"),
    ("pay_as_you_go", ""), ("enterprise", ""), ("discuss", ""),
])
def test_checkout_uses_price_for_plan(plan, expected):
    assert _price_for_plan(plan, _S) == expected


def test_checkout_missing_pro_price_is_not_configured():
    class S(_S):
        stripe_price_pro = ""
    assert _price_for_plan("pro", S) is None


# ── lead age ─────────────────────────────────────────────────────────────────

def test_dot_age_days_formats():
    iso = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00.000")
    compact = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y%m%d")
    assert _dot_age_days(iso) in (29, 30)
    assert _dot_age_days(compact) in (29, 30)
    assert _dot_age_days(None) is None
    assert _dot_age_days("garbage") is None


# ── call list ────────────────────────────────────────────────────────────────

def _lead(**kw):
    base = {"id": kw.pop("id", "x"), "phone": "555-0100", "status": "New", "state": "TX", "score": 5}
    base.update(kw)
    return base


def test_call_list_filters_uncallable():
    rows = [
        _lead(id="ok"),
        _lead(id="nophone", phone=None),
        _lead(id="dnc", do_not_contact=True),
        _lead(id="won", status="Won"),
        _lead(id="lost", status="Lost"),
        _lead(id="later", next_touch_at=(NOW + timedelta(days=1)).isoformat()),
        _lead(id="due", next_touch_at=(NOW - timedelta(hours=1)).isoformat()),
        _lead(id="lower", status=None, stage="contacted"),
    ]
    ids = {r["id"] for r in call_list.build_call_list(rows, now_utc=NOW)}
    assert ids == {"ok", "due", "lower"}


def test_call_list_ranks_score_then_newest_authority():
    rows = [
        _lead(id="old", score=8, dot_age_days=300),
        _lead(id="new", score=8, dot_age_days=10),
        _lead(id="top", score=9),
        _lead(id="low", score=2, dot_age_days=1),
    ]
    assert [r["id"] for r in call_list.build_call_list(rows, now_utc=NOW)] == ["top", "new", "old", "low"]


def test_call_list_dial_now_respects_local_hours():
    rows = [_lead(id="tx", state="TX"), _lead(id="ca", state="CA"), _lead(id="none", state="")]
    ids = [r["id"] for r in call_list.build_call_list(rows, dial_now=True, now_utc=NOW)]
    assert ids == ["tx"]  # CA is 08:00 local — before 9am; blank state is never auto-dialable


def test_call_list_limit_and_csv():
    rows = [_lead(id=str(i), business_name=f"Co {i}") for i in range(5)]
    items = call_list.build_call_list(rows, limit=3, now_utc=NOW)
    assert len(items) == 3
    csv_text = call_list.to_csv(items)
    assert csv_text.splitlines()[0].endswith("outcome,notes")
    assert len(csv_text.strip().splitlines()) == 4


@pytest.mark.parametrize("outcome,status,dnc,has_next", [
    ("no_answer", "Contacted", False, True),
    ("interested", "Interested", False, True),
    ("signed", "Won", False, False),
    ("do_not_call", "Lost", True, False),
])
def test_outcome_patch(outcome, status, dnc, has_next):
    p = call_list.outcome_patch(outcome, now_utc=NOW)
    assert p["status"] == p["stage"] == status
    assert p["outreach_channel"] == "call"
    assert bool(p.get("do_not_contact")) is dnc
    assert (p["next_touch_at"] is not None) is has_next


def test_outcome_patch_rejects_unknown():
    with pytest.raises(KeyError):
        call_list.outcome_patch("maybe")


def test_pitch_quotes_current_prices():
    assert "8% per load" in call_list.PITCH and "$300/month" in call_list.PITCH


def test_falcon_fee_matches_portal_copy():
    # falcon.html tells IEBC-channel carriers "Platform Fee (15%)"
    assert pricing.IEBC_FALCON_FEE_PCT == 0.15
    assert "Platform Fee (15%)" in (Path(__file__).resolve().parents[1] / "falcon.html").read_text()


# ── 25 calls a day ───────────────────────────────────────────────────────────

def test_call_stats_counts_only_todays_calls():
    midnight = NOW.replace(hour=5)  # caller's local midnight in UTC
    rows = [
        {"outreach_channel": "call", "last_contact_at": (midnight + timedelta(hours=1)).isoformat(), "status": "Contacted"},
        {"outreach_channel": "call", "last_contact_at": (midnight + timedelta(hours=2)).isoformat(), "status": "Interested"},
        {"outreach_channel": "call", "last_contact_at": (midnight - timedelta(hours=1)).isoformat(), "status": "Contacted"},
        {"outreach_channel": "email", "last_contact_at": (midnight + timedelta(hours=1)).isoformat()},
    ]
    st = call_list.call_stats(rows, midnight, 25)
    assert (st["made"], st["remaining"], st["done"]) == (2, 23, False)
    assert st["by_status"] == {"Contacted": 1, "Interested": 1}


class _FakeSB:
    """Just enough of the Supabase client for ensure_supply."""
    def __init__(self, rows):
        self.rows = rows
    def table(self, _):
        return self
    def select(self, *_):
        return self
    def limit(self, _):
        return self
    def execute(self):
        return type("R", (), {"data": list(self.rows)})()


def test_ensure_supply_tops_up_until_buffer(monkeypatch):
    from app.agents import naomi
    sb = _FakeSB([_lead(id=f"x{i}") for i in range(10)])
    pulls = []

    def fake_pull(states, per_state=40):
        pulls.append(list(states))
        return [_lead(id=f"{s}{i}", dot_number=f"{s}{i}") for s in states for i in range(10)]

    def fake_persist(prospects):
        sb.rows.extend(prospects)
        return len(prospects)

    monkeypatch.setattr(naomi, "_pull_fmcsa_prospects", fake_pull)
    monkeypatch.setattr(naomi, "_persist_fmcsa_prospects", fake_persist)
    r = call_list.ensure_supply(25, 3, sb=sb)  # need 75, have 10 → one 4-state pull adds 40, second adds 40
    assert r["callable_before"] == 10 and r["callable_after"] == 90 and r["short"] == 0
    assert len(pulls) == 2


def test_ensure_supply_noop_when_full(monkeypatch):
    from app.agents import naomi
    monkeypatch.setattr(naomi, "_pull_fmcsa_prospects", lambda *a, **k: pytest.fail("should not pull"))
    sb = _FakeSB([_lead(id=f"x{i}") for i in range(80)])
    assert call_list.ensure_supply(25, 3, sb=sb)["added"] == 0
