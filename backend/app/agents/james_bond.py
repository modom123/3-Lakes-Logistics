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

LLM strategy:
  Gap analysis & directives → Qwen via OpenRouter (~$0.00035/1K tokens)
  Executive brief           → Qwen first, Claude fallback if Qwen unavailable

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

import json
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
    "alexander", "atlas", "audit", "beacon", "cc_gulley", "chloe_sinclair",
    "echo", "isabella", "katerina", "lucas_sterling", "mark_odom", "naomi",
    "nova", "orbit", "penny", "pulse", "scout", "settler", "shield", "signal",
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
    "atlas":          ["pipeline_state"],
    "beacon":         ["last_brief"],
    "lucas_sterling": ["last_ui_audit", "ui_directives", "pending_fixes"],
    "chloe_sinclair": ["last_viewport_audit", "visual_anomalies", "qa_clearance"],
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

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_QWEN_GAP_SYSTEM = """You are James Bond, IEBC Consultant. You are analyzing a 28-agent AI logistics operation.
You have been given org memory data and a preliminary gap list from automated scans.

Your job: identify ADDITIONAL gaps, efficiency opportunities, and risks that the automated scan missed.

Respond ONLY with a JSON object — no markdown, no prose:
{
  "additional_gaps": [
    {"priority": "HIGH|MEDIUM|LOW", "domain": "<one of the tech domains>", "gap": "<specific finding>", "fix": "<exact action>"}
  ],
  "efficiency_opportunities": ["<1-2 sentence recommendation>"],
  "risk_summary": "<1 sentence overall risk posture>"
}

Tech domains: LLM provider, Memory / org brain, External API integrations, Agent coverage gaps,
Data pipeline health, Error handling & fallbacks, Security & credential hygiene.

Keep additional_gaps to at most 3 new findings not already covered by the preliminary scan.
Be specific and actionable — no filler."""

_QWEN_BRIEF_SYSTEM = """You are James Bond, IEBC Consultant writing an executive brief for the Commander
of a 28-agent AI trucking operation. This is a $0.00035/token model — make every token count.

Structure: one tight paragraph of findings, then one crisp directive sentence.
Tone: direct, intelligent, slightly dry. No bullet points. No filler.
End with exactly: BOND DIRECTIVE TO COMMANDER: [one sentence action].

You have full authority to flag critical issues and recommend immediate action."""


def _call_qwen(system: str, user: str, max_tokens: int = 600) -> str | None:
    """Call Qwen-2.5-72B via OpenRouter. Returns raw text or None on failure."""
    from ..settings import get_settings
    import httpx
    s = get_settings()
    if not s.openrouter_api_key:
        return None
    try:
        r = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {s.openrouter_api_key}",
                "HTTP-Referer": "https://3lakeslogistics.com",
                "X-Title": "3 Lakes Logistics — James Bond IEBC",
                "Content-Type": "application/json",
            },
            json={
                "model": s.openrouter_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                "temperature": 0.1,
                "max_tokens": max_tokens,
            },
            timeout=25,
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        pass
    return None


def _qwen_enrich_gaps(
    coverage: dict[str, Any],
    pipeline: dict[str, Any],
    org_mems: list[dict],
    preliminary_gaps: list[dict],
) -> tuple[list[dict], list[str], str]:
    """Ask Qwen to find additional gaps beyond the rule-based scan.

    Returns (extra_gaps, opportunities, risk_summary).
    """
    context = (
        f"Active agents: {coverage['active_agent_count']}, "
        f"Silent: {coverage['silent_agent_count']} ({coverage['silent_agents'][:5]})\n"
        f"Missing memory keys: {coverage['missing_key_gaps']}\n"
        f"Lead pipeline: {pipeline['tier_a_leads']} Tier-A, {pipeline['tier_b_leads']} Tier-B, "
        f"connect rate: {pipeline['connect_rate']}\n"
        f"Org memory entries: {len(org_mems)}\n"
        f"Preliminary gaps already found:\n"
        + "\n".join(f"- [{g['priority']}] {g['gap']}" for g in preliminary_gaps[:5])
    )
    raw = _call_qwen(_QWEN_GAP_SYSTEM, f"Analyze this org state:\n{context}", max_tokens=700)
    if not raw:
        return [], [], ""
    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw)
        extra   = parsed.get("additional_gaps", [])
        opps    = parsed.get("efficiency_opportunities", [])
        risk    = parsed.get("risk_summary", "")
        # Validate structure
        extra = [g for g in extra if isinstance(g, dict) and "gap" in g and "fix" in g]
        return extra, opps, risk
    except Exception:
        return [], [], ""


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
    opportunities: list[str] | None = None,
    risk_summary: str = "",
) -> str | None:
    """Write the executive brief. Tries Qwen first (cheap), falls back to Claude Sonnet."""
    context = (
        f"Agent coverage: {coverage['active_agent_count']} active, {coverage['silent_agent_count']} silent\n"
        f"Silent agents: {coverage['silent_agents']}\n"
        f"Missing memory keys: {coverage['missing_key_gaps']}\n"
        f"Lead pipeline: {pipeline['tier_a_leads']} Tier A, {pipeline['tier_b_leads']} Tier B\n"
        f"Vance connect rate: {pipeline['connect_rate']}\n"
        f"Top gaps: {[g['gap'] for g in gaps[:3]]}\n"
        f"Directives: {directives[:3]}\n"
        + (f"Risk posture: {risk_summary}\n" if risk_summary else "")
        + (f"Opportunities: {opportunities[:2]}\n" if opportunities else "")
        + f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    prompt = f"Write my consulting brief from this data:\n{context}"

    # ── Qwen first (~8x cheaper than Claude Sonnet) ───────────────────────────
    result = _call_qwen(_QWEN_BRIEF_SYSTEM, prompt, max_tokens=500)
    if result:
        return result

    # ── Claude Sonnet fallback ────────────────────────────────────────────────
    from ..settings import get_settings
    import httpx as _httpx
    key = get_settings().anthropic_api_key
    if not key:
        return None
    try:
        r = _httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 500,
                "system": _QWEN_BRIEF_SYSTEM,
                "messages": [{"role": "user", "content": prompt}],
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
    opportunities: list[str] | None = None,
    risk_summary: str = "",
) -> str:
    # Try LLM-powered brief (Qwen → Claude fallback)
    llm = _llm_brief(coverage, pipeline, gaps, directives, opportunities, risk_summary)
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
    """Execute a James Bond consulting audit with auto-remediation.

    Special scope values:
      'airtable_leads' — pull all leads from the Airtable '3 Lakes Business Hub'
                         base, deduplicate against Supabase, score, and insert.
    """
    scope: str       = str(payload.get("scope", "full")).lower()

    # ── Airtable leads pull mission ──────────────────────────────────────────
    if scope == "airtable_leads":
        return _mission_pull_airtable_leads(payload)

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

    # ── Qwen enrichment: find gaps the rule-based scan missed ────────────────
    extra_gaps, opportunities, risk_summary = _qwen_enrich_gaps(
        coverage, pipeline, org_mems, gaps
    )
    if extra_gaps:
        # Merge and re-sort; cap total at top_n + 3 so Qwen adds signal, not noise
        _w = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        gaps = sorted(gaps + extra_gaps, key=lambda g: _w.get(g.get("priority", "LOW"), 3))
        gaps = gaps[:top_n + 3]

    directives = _build_directives(coverage, pipeline, gaps)
    brief = _executive_summary(coverage, pipeline, gaps, directives, opportunities, risk_summary)

    # ── Auto-remediation: wake silent agents ─────────────────────────────────
    wakeup_report: dict[str, str] = {}
    if remediate and coverage["silent_agents"]:
        wakeup_report = _attempt_agent_wakeup(coverage["silent_agents"])
        # Re-gather coverage after wakeup to reflect fixes
        intel2 = _gather_org_intelligence()
        coverage2 = _agent_coverage_report(intel2["by_agent"])
        wakeup_report["_after_wakeup_silent_count"] = str(coverage2["silent_agent_count"])

    # ── Route actionable external gaps to Outside Bond ────────────────────────
    outside_bond_report: dict[str, Any] = {}
    if remediate:
        try:
            from . import outside_bond as _ob
            for gap in gaps:
                fix = gap.get("fix", "").lower()
                if "bland" in fix or "allowlist" in fix or "ip allowlist" in fix:
                    outside_bond_report["bland_ai_allowlist"] = _ob.run({
                        "task": "bland_ai_allowlist",
                        "phase": scope,
                        "error_details": gap.get("gap", ""),
                    })
                    break
        except Exception:
            pass

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
        "directives":        directives,
        "executive_brief":   brief,
        "opportunities":     opportunities,
        "risk_summary":      risk_summary,
        "qwen_enriched":     bool(extra_gaps),
        "high_gap_count":    sum(1 for g in gaps if g.get("priority") == "HIGH"),
        "remediation":       wakeup_report,
        "outside_bond":      outside_bond_report,
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


# ═══════════════════════════════════════════════════════════════════════════════
# AIRTABLE LEADS MISSION
# Bond pulls from "3 Lakes Business Hub" base, scores, deduplicates, inserts.
# ═══════════════════════════════════════════════════════════════════════════════

import logging as _logging
import urllib.request as _urllib_req
import urllib.error  as _urllib_err

_bond_log = _logging.getLogger("3ll.james_bond.airtable")

_AIRTABLE_API   = "https://api.airtable.com/v0"
_LEAD_STATUSES  = {"new lead", "new", "prospect", "interested", "contacted"}

# Known table names in "3 Lakes Business Hub" to try in order
_TABLE_CANDIDATES = [
    "Carrier Leads",
    "table 1",
    "Leads",
    "carrier leads",
    "Lead Pipeline",
]


def _airtable_get(url: str, api_key: str) -> dict:
    req = _urllib_req.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    with _urllib_req.urlopen(req, timeout=20) as resp:
        import json as _j
        return _j.loads(resp.read().decode())


def _fetch_airtable_table(base_id: str, api_key: str, table: str, offset: str | None = None) -> dict:
    import urllib.parse as _up
    encoded = _up.quote(table, safe="")
    url = f"{_AIRTABLE_API}/{base_id}/{encoded}?pageSize=100"
    if offset:
        url += f"&offset={offset}"
    return _airtable_get(url, api_key)


def _pull_all_records(base_id: str, api_key: str, table: str) -> list[dict]:
    """Paginate through all records in one Airtable table."""
    records: list[dict] = []
    offset = None
    while True:
        page = _fetch_airtable_table(base_id, api_key, table, offset)
        records.extend(page.get("records", []))
        offset = page.get("offset")
        if not offset:
            break
    return records


def _discover_table(base_id: str, api_key: str) -> tuple[str, list[dict]]:
    """Try each candidate table name; return (table_name, records) for the first that works."""
    for table in _TABLE_CANDIDATES:
        try:
            records = _pull_all_records(base_id, api_key, table)
            if records:
                _bond_log.info("airtable table found: '%s' (%d records)", table, len(records))
                return table, records
        except _urllib_err.HTTPError as e:
            if e.code in (404, 422):
                continue
            raise
    raise ValueError(
        f"No accessible table found in base {base_id}. "
        f"Tried: {_TABLE_CANDIDATES}. Check table names in '3 Lakes Business Hub'."
    )


def _map_record(fields: dict) -> dict:
    """Map Airtable field names → Supabase leads schema."""
    def _f(*keys):
        for k in keys:
            v = fields.get(k) or fields.get(k.lower()) or fields.get(k.title())
            if v:
                return str(v).strip()
        return None

    phone = _f("phone_number", "phone", "Phone", "Phone Number")
    # Normalize phone to digits-only for dedup
    phone_digits = "".join(c for c in (phone or "") if c.isdigit())

    status_raw = (_f("status", "Status", "stage", "Stage") or "New Lead").strip()
    status = status_raw if status_raw.lower() in _LEAD_STATUSES else "New Lead"

    return {
        "business_name":  _f("prospect_name", "company_name", "Company Name",
                              "business_name", "Business Name", "name", "Name") or "Unknown",
        "contact_name":   _f("contact_name", "Contact Name", "owner", "Owner"),
        "phone":          phone,
        "phone_digits":   phone_digits,  # used for dedup, stripped before insert
        "email":          _f("email", "Email"),
        "status":         status,
        "source":         "airtable_3lakes_hub",
        "notes":          _f("notes", "Notes"),
        "state":          _f("state", "State"),
        "location":       _f("location", "Location", "city", "City"),
        "truck_type":     _f("truck_type", "Truck Type", "equipment", "Equipment"),
        "website":        _f("website", "Website"),
        "lead_source":    _f("lead_source", "Lead Source", "source_channel"),
        "score":          0,  # will be set by scoring below
    }


def _score(lead: dict) -> int:
    """Simple lead scoring: phone=30, email=20, known truck=20, website=10, notes=10, state=10."""
    score = 0
    if lead.get("phone"):          score += 30
    if lead.get("email"):          score += 20
    tt = (lead.get("truck_type") or "").lower()
    if tt and tt not in ("unknown", "other", ""):  score += 20
    if lead.get("website"):        score += 10
    if lead.get("notes"):          score += 10
    if lead.get("state"):          score += 10
    return score


def _existing_phones(sb) -> set[str]:
    """Fetch all digit-normalized phone numbers already in leads table."""
    rows = sb.table("leads").select("phone").execute().data or []
    result = set()
    for r in rows:
        p = r.get("phone") or ""
        digits = "".join(c for c in p if c.isdigit())
        if digits:
            result.add(digits)
    return result


def _mission_pull_airtable_leads(payload: dict) -> dict:
    """Bond's Airtable leads pull mission.

    Connects to '3 Lakes Business Hub', discovers the carrier leads table,
    maps records to the Supabase leads schema, deduplicates by phone,
    scores each lead, and bulk-inserts.
    """
    from ..settings import get_settings
    from ..supabase_client import get_supabase

    s       = get_settings()
    api_key = payload.get("airtable_api_key") or s.airtable_api_key
    base_id = payload.get("airtable_base_id") or s.airtable_base_id or "appyRkym1i9mXEnzP"

    if not api_key:
        return {
            "agent":   _NAME,
            "mission": "airtable_leads_pull",
            "status":  "BLOCKED",
            "reason":  "AIRTABLE_API_KEY not set. Add it to Render env vars or pass in payload.",
            "action":  "Set AIRTABLE_API_KEY in Render dashboard → Environment → Add variable",
        }

    _bond_log.info("Bond: pulling Airtable leads base=%s", base_id)

    # 1. Discover table + pull all records
    try:
        table_name, raw_records = _discover_table(base_id, api_key)
    except Exception as exc:
        return {
            "agent":   _NAME,
            "mission": "airtable_leads_pull",
            "status":  "ERROR",
            "reason":  str(exc),
        }

    # 2. Map records
    mapped: list[dict] = []
    for rec in raw_records:
        try:
            lead = _map_record(rec.get("fields", {}))
            lead["score"] = _score(lead)
            mapped.append(lead)
        except Exception as exc:
            _bond_log.warning("skipped record %s: %s", rec.get("id"), exc)

    # 3. Deduplicate against existing leads (by phone digits)
    sb = get_supabase()
    existing = _existing_phones(sb)
    dupes, to_insert = 0, []
    for lead in mapped:
        digits = lead.pop("phone_digits", "")
        if digits and digits in existing:
            dupes += 1
        else:
            if digits:
                existing.add(digits)  # prevent intra-batch dupes
            # Strip None values before insert
            clean = {k: v for k, v in lead.items() if v is not None}
            to_insert.append(clean)

    # 4. Bulk insert in batches of 50
    inserted, failed = 0, 0
    BATCH = 50
    for i in range(0, len(to_insert), BATCH):
        batch = to_insert[i:i + BATCH]
        try:
            sb.table("leads").insert(batch).execute()
            inserted += len(batch)
        except Exception as exc:
            _bond_log.error("batch insert failed i=%d: %s", i, exc)
            # Fall back to one-by-one to maximize success
            for lead in batch:
                try:
                    sb.table("leads").insert(lead).execute()
                    inserted += 1
                except Exception:
                    failed += 1

    # 5. Write mission result to Bond memory
    mem.remember(
        _NAME, "airtable_leads_pull",
        {
            "table":     table_name,
            "base_id":   base_id,
            "pulled":    len(raw_records),
            "inserted":  inserted,
            "dupes":     dupes,
            "failed":    failed,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        confidence=1.0, source_agent=_NAME,
        summary=f"Pulled {len(raw_records)} from Airtable → inserted {inserted}, skipped {dupes} dupes",
    )
    log_agent(
        _NAME, "airtable_leads_pull",
        payload={"base_id": base_id, "table": table_name},
        result=f"pulled={len(raw_records)} inserted={inserted} dupes={dupes} failed={failed}",
    )

    return {
        "agent":         _NAME,
        "mission":       "airtable_leads_pull",
        "status":        "SUCCESS" if inserted > 0 else "PARTIAL",
        "airtable_base": base_id,
        "table_used":    table_name,
        "records_pulled": len(raw_records),
        "inserted":      inserted,
        "duplicates_skipped": dupes,
        "failed":        failed,
        "directive":     (
            f"BOND DIRECTIVE: {inserted} leads inserted from '3 Lakes Business Hub'. "
            f"Vance can now begin outbound on {inserted} new prospects. "
            f"{dupes} duplicate{'s' if dupes != 1 else ''} skipped."
        ),
    }
