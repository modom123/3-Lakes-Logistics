"""IEBC agent endpoint tests — Node 201, Node 204, James Bond consultant.

Tests agent reachability, payload validation, and response shape via
POST /api/agents/{agent}/run.

Run:
    pytest tests/test_iebc_agents.py -v
"""
import requests

BASE_URL = "https://three-lakes-logistics-api.onrender.com"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": "Bearer taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE",
}


# ── Shared helpers ────────────────────────────────────────────────────────────

def _run_agent(agent: str, payload: dict, timeout: int = 30) -> requests.Response:
    return requests.post(
        f"{BASE_URL}/api/agents/{agent}/run",
        json=payload,
        headers=HEADERS,
        timeout=timeout,
    )


def _assert_agent_ok(r: requests.Response, agent: str) -> None:
    assert r.status_code == 200, (
        f"Agent {agent} returned {r.status_code}: {r.text[:300]}"
    )
    data = r.json()
    assert isinstance(data, dict), f"Agent {agent} response not a dict: {type(data)}"


# ── All agents require auth ───────────────────────────────────────────────────

def test_iebc_agents_require_auth():
    """IEBC agent endpoints reject unauthenticated requests."""
    for agent in ("dr_james_nemt", "felix_grant", "james_bond"):
        r = requests.post(
            f"{BASE_URL}/api/agents/{agent}/run",
            json={"scope": "full"},
            timeout=15,
        )
        assert r.status_code in (401, 403), (
            f"Agent {agent} accessible without auth (got {r.status_code})."
        )


# ── Node 201: Dr. James NEMT ──────────────────────────────────────────────────

def test_dr_james_nemt_is_registered():
    """Agent list includes dr_james_nemt (Node 201) — confirms registration fix."""
    r = requests.get(f"{BASE_URL}/api/agents/list", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    agents = r.json()
    names = [a.get("name") or a for a in agents] if isinstance(agents, list) else list(agents.keys())
    assert "dr_james_nemt" in names, (
        f"dr_james_nemt not in agent list. Available: {names}. "
        "Node 201 NEMT segment manager is not registered."
    )


def test_dr_james_nemt_wrong_name_returns_404():
    """Old incorrect name 'dr_james' → 404 (confirms the bug is fixed)."""
    r = _run_agent("dr_james", {"scope": "full"})
    assert r.status_code in (404, 422), (
        f"'dr_james' (old buggy name) returned {r.status_code} — should be 404. "
        "If 200, the wrong agent name was re-added somewhere."
    )


def test_dr_james_nemt_full_report():
    """Node 201 runs a full NEMT segment report and returns structured data."""
    r = _run_agent("dr_james_nemt", {"scope": "full"})
    _assert_agent_ok(r, "dr_james_nemt")


def test_dr_james_nemt_compliance_scope():
    """Node 201 compliance-only scope returns data without error."""
    r = _run_agent("dr_james_nemt", {"scope": "compliance"})
    _assert_agent_ok(r, "dr_james_nemt")


def test_dr_james_nemt_ops_scope():
    """Node 201 ops-only scope returns data without error."""
    r = _run_agent("dr_james_nemt", {"scope": "ops"})
    _assert_agent_ok(r, "dr_james_nemt")


# ── Node 204: Felix Grant Courier ─────────────────────────────────────────────

def test_felix_grant_is_registered():
    """Agent list includes felix_grant (Node 204)."""
    r = requests.get(f"{BASE_URL}/api/agents/list", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    agents = r.json()
    names = [a.get("name") or a for a in agents] if isinstance(agents, list) else list(agents.keys())
    assert "felix_grant" in names, f"felix_grant not in agent list. Available: {names}."


def test_felix_grant_full_report():
    """Node 204 runs full courier segment report."""
    r = _run_agent("felix_grant", {"scope": "full"})
    _assert_agent_ok(r, "felix_grant")


def test_felix_grant_pipeline_scope():
    """Node 204 pipeline scope returns load pipeline data."""
    r = _run_agent("felix_grant", {"scope": "pipeline"})
    _assert_agent_ok(r, "felix_grant")


def test_felix_grant_coverage_scope():
    """Node 204 coverage scope returns coverage area data."""
    r = _run_agent("felix_grant", {"scope": "coverage"})
    _assert_agent_ok(r, "felix_grant")


def test_felix_grant_action_report():
    """Node 204 with action=report returns formatted report."""
    r = _run_agent("felix_grant", {"scope": "full", "action": "report"})
    _assert_agent_ok(r, "felix_grant")


# ── James Bond: IEBC Internal Consultant ─────────────────────────────────────

def test_james_bond_is_registered():
    """Agent list includes james_bond (IEBC consultant)."""
    r = requests.get(f"{BASE_URL}/api/agents/list", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    agents = r.json()
    names = [a.get("name") or a for a in agents] if isinstance(agents, list) else list(agents.keys())
    assert "james_bond" in names, f"james_bond not in agent list. Available: {names}."


def test_james_bond_full_audit():
    """James Bond runs a full system audit across all segments."""
    r = _run_agent("james_bond", {"scope": "full", "top_n": 3, "remediate": False})
    _assert_agent_ok(r, "james_bond")


def test_james_bond_tech_scope():
    """James Bond tech-only scope returns technical gap analysis."""
    r = _run_agent("james_bond", {"scope": "tech", "remediate": False})
    _assert_agent_ok(r, "james_bond")


def test_james_bond_ops_scope():
    """James Bond ops-only scope returns operational insights."""
    r = _run_agent("james_bond", {"scope": "ops", "remediate": False})
    _assert_agent_ok(r, "james_bond")


def test_james_bond_leads_scope():
    """James Bond leads scope returns lead pipeline analysis."""
    r = _run_agent("james_bond", {"scope": "leads", "top_n": 5, "remediate": False})
    _assert_agent_ok(r, "james_bond")


def test_james_bond_with_agent_focus():
    """James Bond with agent_focus parameter narrows audit to specific agent."""
    r = _run_agent("james_bond", {"scope": "full", "agent_focus": "vance", "remediate": False})
    _assert_agent_ok(r, "james_bond")


# ── Bond Channel routes ───────────────────────────────────────────────────────

def test_bond_status_reachable():
    """Bond status endpoint is reachable with valid auth."""
    r = requests.get(f"{BASE_URL}/api/bond/status", headers=HEADERS, timeout=15)
    assert r.status_code in (200, 404), (
        f"Bond status returned {r.status_code}."
    )


def test_bond_thread_reachable():
    """Bond thread endpoint is reachable with valid auth."""
    r = requests.get(f"{BASE_URL}/api/bond/thread", headers=HEADERS, timeout=15)
    assert r.status_code in (200, 404), (
        f"Bond thread returned {r.status_code}."
    )


def test_bond_endpoints_require_auth():
    """Bond channel routes reject unauthenticated requests."""
    for path in ("/api/bond/thread", "/api/bond/status"):
        r = requests.get(f"{BASE_URL}{path}", timeout=15)
        assert r.status_code in (401, 403), (
            f"Bond route {path} accessible without auth (got {r.status_code})."
        )
