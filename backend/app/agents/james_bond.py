"""James Bond — IEBC Consultant (hermes-agent integration).

Role: Independent Enterprise Business Consultant embedded in the
3 Lakes Logistics AI command centre.

Persona:
  Name:   James Bond
  Firm:   IEBC (Intelligent Enterprise Business Consulting)
  Traits: Extremely Smart · Problem Solver · Direct · Technology Expert

Mission:
  Bond conducts rapid, no-nonsense technology and operational audits
  across the entire 28-agent workforce. He reads the org brain, surfaces
  what is broken or under-optimised, and delivers one crisp consulting
  report per run — zero filler, maximum signal.

Outputs (written to org memory for Commander and CC Gulley to consume):
  james_bond/last_audit     — full JSON audit report
  james_bond/tech_gaps      — prioritised technology gap list
  james_bond/directives     — ordered action items for Commander
  org/consultant_brief      — executive-level summary (1 paragraph)

API surface:
  POST /api/agents/james_bond/run
  Payload keys (all optional):
    scope        str   "full" | "tech" | "ops" | "leads"   default: "full"
    agent_focus  str   restrict audit to one named agent   default: None
    top_n        int   top-N gaps/actions to surface       default: 5
"""
from __future__ import annotations

import textwrap
from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from . import memory as mem

# ── Agent wakeup map: agent_name → callable that accepts a payload dict ───────
# Populated lazily on first use to avoid circular imports at module load.
_WAKEUP_MAP: dict[str, Any] = {}

_NAME = "james_bond"
_FIRM = "IEBC"

_KNOWN_AGENTS = [
    "alexander", "atlas", "audit", "beacon", "cc_gulley", "echo",
    "isabella", "katerina", "mark_odom", "naomi", "nova", "orbit",
    "penny", "pulse", "scout", "settler", "shield", "signal",
    "sofia", "sonny", "vance", "victoria", "winston",
]

_EXPECTED_MEMORY_KEYS: dict[str, list[str]] = {
    "naomi":     ["tier_a_targets", "tier_b_targets"],
    "vance":     ["call_outcomes"],
    "alexander": ["hot_states"],
    "shield":    ["last_scan"],
    "sofia":     ["ar_status"],
    "victoria":  ["growth_snapshot"],
    "winston":   ["at_risk_carriers"],
    "penny":     ["billing_health"],
    "atlas":     ["pipeline_state"],
    "beacon":    ["last_brief"],
}

_TECH_DOMAINS = [
    "LLM provider",
    "Memory / org brain",
    "External API integrations",
    "Agent coverage gaps",
    "Data pipeline health",
    "Error handling & fallbacks",
    "Security & credential hygiene",
]


def _gather_org_intelligence() -> dict[str, Any]:
    org_mems = mem.recall_org()
    by_agent: dict[str, list[dict]] = {}
    for agent in _KNOWN_AGENTS:
        agent_mems = mem.recall_all(agent)
        if agent_mems:
            by_agent[agent] = agent_mems
    return {"org": org_mems, "by_agent": by_agent}


def _agent_coverage_report(by_agent: dict[str, list[dict]]) -> dict[str, Any]:
    active = set(by_agent.keys())
    silent = [a for a in _KNOWN_AGENTS if a not in active]
    missing_keys: dict[str, list[str]] = {}
    for agent, expected in _EXPECTED_MEMORY_KEYS.items():
        written = {m["memory_key"] for m in by_agent.get(agent, [])}
        gaps = [k for k in expected if k not in written]
        if gaps:
            missing_keys[agent] = gaps
    return {
        "active_agent_count":  len(active),
        "silent_agent_count":  len(silent),
        "silent_agents":       sorted(silent),
        "missing_key_gaps":    missing_keys,
    }


def _assess_lead_pipeline(by_agent: dict[str, list[dict]]) -> dict[str, Any]:
    naomi_tier_a = None
    naomi_tier_b = None
    hot_states: list[str] = []
    vance_outcomes: dict = {}

    for m in by_agent.get("naomi", []):
        if m["memory_key"] == "tier_a_targets":
            naomi_tier_a = m.get("memory_value", {})
        if m["memory_key"] == "tier_b_targets":
            naomi_tier_b = m.get("memory_value", {})

    for m in by_agent.get("alexander", []):
        if m["memory_key"] == "hot_states":
            hot_states = list((m.get("memory_value") or {}).keys())[:5]

    for m in by_agent.get("vance", []):
        if m["memory_key"] == "call_outcomes":
            vance_outcomes = m.get("memory_value") or {}

    tier_a_count = (naomi_tier_a or {}).get("count", 0)
    tier_b_count = (naomi_tier_b or {}).get("count", 0)
    tier_a_calls = int(vance_outcomes.get("tier_a_calls", 0))
    tier_a_connected = int(vance_outcomes.get("tier_a_connected", 0))
    connect_rate = round(tier_a_connected / tier_a_calls, 2) if tier_a_calls else None

    return {
        "tier_a_leads":       tier_a_count,
        "tier_b_leads":       tier_b_count,
        "hot_states":         hot_states,
        "vance_calls_placed": tier_a_calls,
        "connect_rate":       connect_rate,
        "pipeline_healthy":   bool(naomi_tier_a and tier_a_count > 0),
    }


def _identify_tech_gaps(
    coverage: dict[str, Any],
    org_mems: list[dict],
    top_n: int = 5,
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []

    for agent in coverage["silent_agents"]:
        gaps.append({
            "priority": "HIGH",
            "domain":   "Agent coverage gaps",
            "gap":      f"Agent '{agent}' has never written to org memory — may be unconfigured or failing silently.",
            "fix":      f"Verify {agent}.run() is reachable via /api/agents/{agent}/run and has no import errors.",
        })

    for agent, missing in coverage["missing_key_gaps"].items():
        gaps.append({
            "priority": "MEDIUM",
            "domain":   "Memory / org brain",
            "gap":      f"Agent '{agent}' is missing expected memory keys: {missing}.",
            "fix":      f"Trigger {agent}.run() to populate missing keys, then verify in agent_memory table.",
        })

    if len(org_mems) < 3:
        gaps.append({
            "priority": "HIGH",
            "domain":   "Memory / org brain",
            "gap":      f"Org-level memory has only {len(org_mems)} entries — agents are not sharing cross-agent intelligence.",
            "fix":      "Run victoria, alexander, and naomi to seed org brain with market + lead intelligence.",
        })

    has_fmcsa = any(
        (m.get("memory_value") or {}).get("fmcsa_found", 0) > 0
        for m in org_mems
        if m.get("memory_key") == "lead_intelligence"
    )
    if not has_fmcsa:
        gaps.append({
            "priority": "MEDIUM",
            "domain":   "External API integrations",
            "gap":      "No FMCSA census prospecting activity detected — free DOT dataset not being harvested.",
            "fix":      "Set DOT_API_KEY and trigger naomi.run({'include_fmcsa': true}) to activate FMCSA pipeline.",
        })

    _w = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    gaps.sort(key=lambda g: _w.get(g["priority"], 3))
    return gaps[:top_n]


def _build_directives(
    coverage: dict[str, Any],
    pipeline: dict[str, Any],
    gaps: list[dict[str, Any]],
) -> list[str]:
    directives: list[str] = []
    idx = 1

    if coverage["silent_agents"]:
        directives.append(
            f"{idx}. IMMEDIATE: Investigate {len(coverage['silent_agents'])} silent agent(s): "
            f"{', '.join(coverage['silent_agents'][:3])}{'...' if len(coverage['silent_agents']) > 3 else ''}. "
            "Confirm API routes are live and returning 200."
        )
        idx += 1

    if not pipeline["pipeline_healthy"]:
        directives.append(
            f"{idx}. HIGH: Lead pipeline is not seeded — run Naomi immediately "
            "to score existing leads and feed Vance's call list."
        )
        idx += 1
    elif pipeline["connect_rate"] is not None and pipeline["connect_rate"] < 0.35:
        directives.append(
            f"{idx}. HIGH: Vance connect rate is {pipeline['connect_rate']:.0%} — "
            "below 35% threshold. Instruct Isabella to warm leads with email/SMS "
            "before Vance calls."
        )
        idx += 1

    for gap in gaps:
        if gap["priority"] == "HIGH" and idx <= 5:
            directives.append(
                f"{idx}. {gap['priority']}: {gap['fix']}"
            )
            idx += 1

    if not directives:
        directives.append(
            "1. MAINTAIN: All key systems nominal. "
            "Run Beacon daily brief and monitor Winston for churn signals."
        )

    return directives


def _llm_brief(
    coverage: dict[str, Any],
    pipeline: dict[str, Any],
    gaps: list[dict[str, Any]],
    directives: list[str],
) -> str | None:
    """Call Claude Sonnet to write a sharper consultant brief. Returns None on failure."""
    from ..settings import get_settings
    import httpx as _httpx
    key = get_settings().anthropic_api_key
    if not key:
        return None
    context = (
        f"Agent coverage: {coverage['active_agent_count']} active, {coverage['silent_agent_count']} silent\n"
        f"Silent agents: {coverage['silent_agents']}\n"
        f"Missing memory keys: {coverage['missing_key_gaps']}\n"
        f"Lead pipeline: {pipeline['tier_a_leads']} Tier A, {pipeline['tier_b_leads']} Tier B\n"
        f"Vance connect rate: {pipeline['connect_rate']}\n"
        f"Top gaps: {[g['gap'] for g in gaps[:3]]}\n"
        f"Directives: {directives[:3]}\n"
        f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    try:
        r = _httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model":      "claude-sonnet-4-6",
                "max_tokens": 500,
                "system": (
                    "You are James Bond, IEBC Consultant. You write sharp, no-filler executive briefs "
                    "for the Commander of a 28-agent AI trucking operation. "
                    "Structure: one paragraph of findings, one crisp directive. "
                    "Tone: direct, intelligent, slightly dry. Never use bullet points. "
                    "End every brief with: BOND DIRECTIVE TO COMMANDER: [one sentence action]."
                ),
                "messages": [{"role": "user", "content": f"Write my consulting brief from this data:\n{context}"}],
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()
    except Exception:
        return None


def _executive_summary(
    coverage: dict[str, Any],
    pipeline: dict[str, Any],
    gaps: list[dict[str, Any]],
    directives: list[str],
) -> str:
    # Try LLM-powered brief first
    llm = _llm_brief(coverage, pipeline, gaps, directives)
    if llm:
        return llm

    # Fallback: template
    high_gaps = sum(1 for g in gaps if g["priority"] == "HIGH")
    silent    = coverage["silent_agent_count"]
    tier_a    = pipeline["tier_a_leads"]
    tier_b    = pipeline["tier_b_leads"]
    rate      = pipeline["connect_rate"]
    rate_str  = f"{rate:.0%}" if rate is not None else "not yet measured"

    return textwrap.dedent(f"""\
        IEBC CONSULTING BRIEF — James Bond — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
        {high_gaps} high-priority technology gap(s) identified across the 28-agent workforce.
        {silent} agent(s) are silent (no memory writes); coverage report flags \
{len(coverage['missing_key_gaps'])} agents with missing expected memory keys.
        Lead pipeline: {tier_a} Tier A leads · {tier_b} Tier B leads · Vance connect rate {rate_str}.
        Top directive: {directives[0] if directives else 'All clear — maintain cadence.'}
        CONSULTANT RECOMMENDATION: {directives[0].split(':', 1)[-1].strip() if directives else 'Continue standard operations.'}
    """).strip()


def _load_wakeup_map() -> None:
    """Lazily populate _WAKEUP_MAP on first remediation attempt."""
    if _WAKEUP_MAP:
        return
    candidates = {
        "alexander": ("alexander",),
        "beacon":    ("beacon",),
        "isabella":  ("isabella",),
        "katerina":  ("katerina",),
        "naomi":     ("naomi",),
        "penny":     ("penny",),
        "scout":     ("scout",),
        "shield":    ("shield",),
        "victoria":  ("victoria",),
        "vance":     ("vance",),
        "winston":   ("winston",),
    }
    for name, (mod_name,) in candidates.items():
        try:
            import importlib
            mod = importlib.import_module(f"..{mod_name}", package=__package__)
            if hasattr(mod, "run"):
                _WAKEUP_MAP[name] = mod.run
        except Exception:
            pass


def _attempt_agent_wakeup(silent_agents: list[str]) -> dict[str, Any]:
    """Call run({}) on each silent agent to populate their memory.

    Returns a remediation report: {agent: 'woken'|'failed'|'skipped'}.
    """
    _load_wakeup_map()
    results: dict[str, str] = {}
    for agent in silent_agents[:5]:  # max 5 at once to avoid overload
        runner = _WAKEUP_MAP.get(agent)
        if runner is None:
            results[agent] = "skipped — no runner registered"
            continue
        try:
            runner({})
            results[agent] = "woken"
        except Exception as exc:
            results[agent] = f"failed — {str(exc)[:80]}"
    return results


def run(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute a James Bond consulting audit with auto-remediation."""
    scope: str       = str(payload.get("scope", "full")).lower()
    agent_focus: str | None = payload.get("agent_focus")
    top_n: int       = int(payload.get("top_n", 5))
    remediate: bool  = bool(payload.get("remediate", True))

    intel = _gather_org_intelligence()
    by_agent = intel["by_agent"]
    org_mems = intel["org"]

    if agent_focus and agent_focus in _KNOWN_AGENTS:
        by_agent = {agent_focus: by_agent.get(agent_focus, [])}

    coverage = _agent_coverage_report(by_agent)
    pipeline = _assess_lead_pipeline(intel["by_agent"])
    gaps     = _identify_tech_gaps(coverage, org_mems, top_n=top_n)
    directives = _build_directives(coverage, pipeline, gaps)
    brief    = _executive_summary(coverage, pipeline, gaps, directives)

    # ── Auto-remediation: wake silent agents ─────────────────────────────────
    wakeup_report: dict[str, str] = {}
    if remediate and coverage["silent_agents"]:
        wakeup_report = _attempt_agent_wakeup(coverage["silent_agents"])
        # Re-gather coverage after wakeup to reflect fixes
        intel2 = _gather_org_intelligence()
        coverage2 = _agent_coverage_report(intel2["by_agent"])
        wakeup_report["_after_wakeup_silent_count"] = str(coverage2["silent_agent_count"])

    report = {
        "consultant":    "James Bond",
        "firm":          _FIRM,
        "role":          "IEBC Consultant",
        "scope":         scope,
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "agent_focus":   agent_focus,
        "coverage":      coverage,
        "lead_pipeline": pipeline,
        "tech_gaps":     gaps,
        "directives":    directives,
        "executive_brief": brief,
        "remediation":   wakeup_report,
    }

    mem.remember(
        _NAME, "last_audit", report, confidence=0.9,
        summary=(
            f"Bond audit {datetime.now(timezone.utc).strftime('%Y-%m-%d')}: "
            f"{len(gaps)} gaps · {len(directives)} directives · "
            f"{coverage['silent_agent_count']} silent agents"
        ),
    )
    mem.remember(
        _NAME, "tech_gaps",
        {"gaps": gaps, "count": len(gaps)},
        confidence=0.85,
        summary=f"{sum(1 for g in gaps if g['priority'] == 'HIGH')} HIGH · "
                f"{sum(1 for g in gaps if g['priority'] == 'MEDIUM')} MEDIUM gaps",
    )
    mem.remember(
        _NAME, "directives",
        {"directives": directives},
        confidence=0.9,
        summary=directives[0] if directives else "All clear",
    )
    mem.remember(
        "org", "consultant_brief",
        {"brief": brief, "consultant": "james_bond", "high_gap_count": sum(1 for g in gaps if g["priority"] == "HIGH")},
        confidence=0.9, source_agent=_NAME,
        summary=f"IEBC Bond brief — {sum(1 for g in gaps if g['priority'] == 'HIGH')} HIGH gaps identified",
    )

    mem.log_interaction(
        _NAME, "mark_odom", "consult_report",
        payload={"scope": scope, "top_n": top_n},
        result={"gap_count": len(gaps), "directive_count": len(directives)},
        outcome="success",
        outcome_notes=f"{coverage['silent_agent_count']} silent agents · top gap: {gaps[0]['gap'][:80] if gaps else 'none'}",
    )
    mem.log_interaction(
        _NAME, "cc_gulley", "strategic_handoff",
        payload={"directives": directives[:3]},
        result={"status": "directives_written_to_memory"},
        outcome="success",
        outcome_notes="Bond directives available in james_bond/directives for CC Gulley's 30/60/90 roadmap",
    )

    log_agent(
        _NAME, "consulting_audit",
        payload={"scope": scope, "top_n": top_n},
        result=(
            f"gaps={len(gaps)} high={sum(1 for g in gaps if g['priority'] == 'HIGH')} "
            f"silent={coverage['silent_agent_count']} "
            f"tier_a={pipeline['tier_a_leads']} connect_rate={pipeline['connect_rate']}"
        ),
    )

    return {"agent": _NAME, **report}
