"""IEBC Technical Team — automated remediation system.

Domain experts investigate test-suite failures using their live data access:
  winston_carmichael  → Carrier + Fleet failures (active_carriers, loads tables)
  isabella_cruz       → Leads failures (leads table, outreach pipeline)
  alexander_wright    → Bond Channel + external API failures (FMCSA/DOT APIs)
  katerina_rostova    → Health + Dashboard + Telemetry failures (SLA audit)

Atlas orchestrates state. Bond coordinates and escalates to External Bond.

Payload:
  action="remediate"   failures=[{domain, test_name, error}, ...]
  action="status"      returns last remediation run from memory
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from . import bond_courier
from . import memory as mem

_NAME = "technical_team"


def _daytona_id() -> str:
    return get_settings().daytona_sandbox_id


# ── LLM helper ────────────────────────────────────────────────────────────────

def _llm(
    system: str,
    user: str,
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 800,
) -> str | None:
    """Call Anthropic. Returns None gracefully if key absent or call fails."""
    from ..settings import get_settings
    key = get_settings().anthropic_api_key
    if not key:
        return None
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":           key,
                "anthropic-version":   "2023-06-01",
                "content-type":        "application/json",
            },
            json={
                "model":      model,
                "max_tokens": max_tokens,
                "system":     system,
                "messages":   [{"role": "user", "content": user}],
            },
            timeout=40,
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()
    except Exception as exc:
        log_agent(_NAME, "llm_error", error=str(exc))
        return None

SPECIALISTS: dict[str, dict] = {
    "winston_carmichael": {
        "name":    "Winston Carmichael",
        "role":    "VP Client Success",
        "domains": {"Carriers", "Fleet"},
    },
    "isabella_cruz": {
        "name":    "Isabella Cruz",
        "role":    "VP Omnichannel Outreach",
        "domains": {"Leads"},
    },
    "alexander_wright": {
        "name":    "Alexander Wright",
        "role":    "VP Market Intelligence",
        "domains": {"Bond Channel", "Integration"},
    },
    "katerina_rostova": {
        "name":    "Katerina Rostova",
        "role":    "Head of Process Automation",
        "domains": {"Health", "Dashboard", "Telemetry", "Triggers"},
    },
    "penny": {
        "name":    "Penny",
        "role":    "Stripe & Payments Specialist",
        "domains": {"Driver"},
    },
    "shield": {
        "name":    "Shield",
        "role":    "Security & Compliance Specialist",
        "domains": {"Security"},
    },
}


# ── Classification ────────────────────────────────────────────────────────────

def _classify(test_name: str, domain: str, error: str) -> str:
    txt = f"{test_name} {domain} {error}".lower()
    if any(k in txt for k in ("bond_channel", "bond channel", "missing table", "does not exist")):
        return "missing_table"
    if any(k in txt for k in ("supabase", "connection refused", "database")):
        return "database"
    if any(k in txt for k in ("bond_api_key", "x-bond-key", "api_key", "api key")):
        return "api_key"
    if any(k in txt for k in ("forgery", "forged", "signature", "webhook", "stripe-signature")):
        return "webhook_security"
    if any(k in txt for k in ("privilege", "escalation", "horizontal", "exec dashboard", "exec route")):
        return "privilege_escalation"
    if any(k in txt for k in ("idempotency", "double payout", "duplicate", "paid twice")):
        return "idempotency"
    if any(k in txt for k in ("brute force", "rate limit", "credential stuffing", "max attempts")):
        return "rate_limit"
    if any(k in txt for k in ("401", "403", "unauthorized", "auth guard", "forbidden")):
        return "auth"
    if any(k in txt for k in ("adobe", "twilio", "dat board", "email parse", "integration")):
        return "integration"
    if any(k in txt for k in ("422", "env", "environment", "render env", "not configured")):
        return "config"
    if any(k in txt for k in ("connection", "connect", "unreachable", "timeout")):
        return "connection"
    if any(k in txt for k in ("500", "internal server", "traceback", "exception", "error")):
        return "code_bug"
    if any(k in txt for k in ("shape", "count", "items", "expected", "missing key")):
        return "response_shape"
    return "code_bug"


def _assign(failure_type: str, domain: str = "") -> str:
    """Assign by domain first — routes failures to the agent who owns that data."""
    for sid, info in SPECIALISTS.items():
        if domain in info.get("domains", set()):
            return sid
    return "katerina_rostova"


# ── Winston Carmichael — Carrier & Fleet health ───────────────────────────────

def _run_winston(failures: list[dict]) -> dict[str, Any]:
    mine = [f for f in failures if f.get("specialist") == "winston_carmichael"]
    if not mine:
        return {"specialist": "winston_carmichael", "name": "Winston Carmichael",
                "role": "VP Client Success", "status": "no_assignment", "artifacts": []}

    # Call Winston's real carrier assessment from active_carriers + loads tables
    real_data: dict[str, Any] = {}
    real_data_error = ""
    try:
        from . import winston as winston_agent
        real_data = winston_agent.assess_carriers()
    except Exception as exc:
        real_data_error = str(exc)[:120]

    diagnoses = []
    for f in mine:
        domain = f["domain"]
        error  = f.get("error", "")
        if real_data:
            carriers_count = real_data.get("carriers_assessed", "?")
            healthy        = real_data.get("healthy_carriers", "?")
            at_risk        = real_data.get("at_risk_count", "?")
            if "500" in error or "server error" in error.lower():
                cause = (
                    f"Backend exception in {domain} — DB has {carriers_count} carriers "
                    f"({healthy} healthy, {at_risk} at-risk). Route handler is crashing."
                )
                steps = [
                    "Open Render dashboard → your service → Logs",
                    "Search for 'ERROR' or 'Traceback' near the test run time",
                    "Fix the failing import or route handler and redeploy",
                ]
            elif "shape" in error.lower() or "count" in error.lower():
                cause = (
                    f"{domain} returned wrong JSON shape — DB has {carriers_count} carriers "
                    "but route may be returning raw list instead of {count, items}"
                )
                steps = [
                    f"Open backend/app/api/routes_{domain.lower()}.py",
                    "Verify list endpoint wraps results: {count: N, items: [...]}",
                    "Fix and redeploy",
                ]
            else:
                cause = (
                    f"{domain} failure — Winston confirms {carriers_count} carriers in DB "
                    f"({at_risk} at-risk). Likely a route or auth issue, not missing data."
                )
                steps = [
                    f"Verify /api/{domain.lower()}/ in Render logs",
                    "Compare response against expected {count, items} contract",
                    "Check API_BEARER_TOKEN env var is set on Render",
                ]
        else:
            if "500" in error or "server error" in error.lower():
                cause = f"Backend exception in {domain} — check Render logs for traceback"
                steps = [
                    "Open Render dashboard → your service → Logs",
                    "Search for 'ERROR' or 'Traceback' near the test run time",
                    "Fix the failing import or route handler and redeploy",
                ]
            elif "shape" in error.lower() or "count" in error.lower():
                cause = f"{domain} returned wrong JSON shape — route returns raw list instead of {{count, items}}"
                steps = [
                    f"Open backend/app/api/routes_{domain.lower()}.py",
                    "Verify list endpoint wraps results in {count: N, items: [...]}",
                    "Fix and redeploy",
                ]
            else:
                cause = f"Unexpected {domain} response — diagnose the route"
                steps = [
                    "Check Render logs at the test run timestamp",
                    "Compare response against expected contract",
                    "Fix code or environment config accordingly",
                ]
        diagnoses.append({"domain": domain, "test": f["test_name"], "cause": cause, "steps": steps})

    artifacts: list[dict] = [
        {
            "type":    "diagnosis",
            "title":   (
                f"Winston's Carrier Health Analysis ({real_data.get('carriers_assessed','?')} assessed)"
                if real_data else "Root Cause Analysis"
            ),
            "content": diagnoses,
        }
    ]

    if real_data:
        summary_lines = [
            "# Winston Carmichael — Live Carrier Health Snapshot",
            f"# Run: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            "",
            f"carriers_assessed = {real_data.get('carriers_assessed', '?')}",
            f"healthy_carriers  = {real_data.get('healthy_carriers', '?')}",
            f"at_risk_count     = {real_data.get('at_risk_count', '?')}",
            f"never_loaded      = {real_data.get('never_loaded_count', '?')}",
            f"retention_pct     = {real_data.get('retention_rate_pct', '?')}%",
            "",
            f"# Recommended action: {real_data.get('recommended_action', '?')}",
        ]
        for c in real_data.get("at_risk_carriers", [])[:5]:
            summary_lines.append(
                f"#   [{c.get('priority','?').upper()}] {c.get('name','?')} — {c.get('risk_reason','?')}"
            )
        if real_data_error:
            summary_lines += ["", f"# Warning — DB unreachable: {real_data_error}"]
        artifacts.append({
            "type":    "python",
            "title":   "Live Carrier Health Snapshot",
            "content": "\n".join(summary_lines),
        })

    llm_fix = _llm(
        system=(
            "You are Winston Carmichael, VP Client Success at 3 Lakes Logistics. "
            "You have direct access to carrier and load data and pinpoint exactly "
            "why Carrier or Fleet API tests are failing. "
            "Be concise. Return only code and brief comments — no prose."
        ),
        user=(
            f"Failing API tests:\n{json.dumps(mine, indent=2)}\n\n"
            + (f"Live carrier health data:\n{json.dumps(real_data, indent=2)}\n\n" if real_data else "")
            + "For each failure: state the most likely root cause given the live data, "
            "then write the minimal Python code change or shell command that fixes it. "
            "Format as:\n# [Domain] [Test]\n# Cause: ...\n<code fix or command>\n\n"
        ),
        model="claude-haiku-4-5-20251001",
        max_tokens=700,
    )
    if llm_fix:
        artifacts.append({
            "type":    "python",
            "title":   "Winston's AI-Assisted Code Fix",
            "content": llm_fix,
        })

    return {
        "specialist":     "winston_carmichael",
        "name":           "Winston Carmichael",
        "role":           "VP Client Success",
        "assigned_count": len(mine),
        "status":         "complete",
        "artifacts":      artifacts,
    }


# ── Isabella Cruz — Leads pipeline & outreach ────────────────────────────────

def _run_isabella(failures: list[dict]) -> dict[str, Any]:
    mine = [f for f in failures if f.get("specialist") == "isabella_cruz"]
    if not mine:
        return {"specialist": "isabella_cruz", "name": "Isabella Cruz",
                "role": "VP Omnichannel Outreach", "status": "no_assignment", "artifacts": []}

    real_data: dict[str, Any] = {}
    try:
        from . import isabella as isabella_agent
        real_data = isabella_agent.build_campaign(segment="New", limit=20)
    except Exception:
        pass

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sql_blocks: list[str] = [
        "-- Isabella Cruz — Leads Pipeline Verification",
        f"-- Generated: {now}",
        "",
        "-- Check leads table exists and has data:",
        "SELECT COUNT(*) AS lead_count FROM leads;",
        "SELECT status, COUNT(*) FROM leads GROUP BY status ORDER BY COUNT(*) DESC;",
        "",
        "-- Verify columns match expected shape:",
        "SELECT id, business_name, status, score FROM leads ORDER BY score DESC LIMIT 5;",
        "",
    ]
    if real_data:
        sql_blocks += [
            f"-- Live: {real_data.get('total_leads_in_segment','?')} leads in 'New' segment "
            f"· avg score {real_data.get('avg_lead_score','?')}",
            "-- If test fails but data exists: check /api/leads/ response shape.",
        ]

    diagnoses = []
    for f in mine:
        domain = f["domain"]
        error  = f.get("error", "")
        if real_data and real_data.get("total_leads_in_segment", 0) > 0:
            total = real_data["total_leads_in_segment"]
            avg   = real_data["avg_lead_score"]
            cause = (
                f"Leads API failing but DB has {total} leads (avg score {avg}). "
                "Route handler or response envelope is the issue, not missing data."
            )
            steps = [
                "Check /api/leads/ returns {count: N, items: [...]}",
                "Verify API_BEARER_TOKEN in Render env vars",
                "Check Render logs for Python exceptions at the test run timestamp",
            ]
        elif "count" in error.lower() or "items" in error.lower():
            cause = "Leads endpoint not returning expected {count, items} envelope"
            steps = [
                "Open backend/app/api/routes_leads.py",
                "Wrap list return: return {count: len(data), items: data}",
                "Push fix and redeploy",
            ]
        else:
            cause = f"Leads API failure — {error[:80]}"
            steps = [
                "Check Render logs for exception",
                "Verify leads table: SELECT COUNT(*) FROM leads;",
                "Verify SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY on Render",
            ]
        diagnoses.append({"domain": domain, "test": f["test_name"], "cause": cause, "steps": steps})

    artifacts: list[dict] = [
        {
            "type":    "sql",
            "title":   "Leads Pipeline Verification (Supabase SQL Editor)",
            "content": "\n".join(sql_blocks),
        },
        {
            "type":    "diagnosis",
            "title":   (
                f"Isabella's Pipeline Analysis ({real_data.get('total_leads_in_segment','?')} leads live)"
                if real_data else "Pipeline Analysis"
            ),
            "content": diagnoses,
        },
    ]

    llm_sql = _llm(
        system=(
            "You are Isabella Cruz, VP Omnichannel Outreach at 3 Lakes Logistics. "
            "You understand the leads pipeline: leads table, outreach campaigns, Vance calls, Echo SMS. "
            "Write precise, safe SQL for Supabase (PostgreSQL 15). "
            "Only use SELECT and CREATE/ALTER IF NOT EXISTS. No destructive statements. "
            "Return only SQL with brief comments."
        ),
        user=(
            f"Failing lead API tests:\n{json.dumps(mine, indent=2)}\n\n"
            + (f"Live pipeline data:\n{json.dumps(real_data, indent=2)}\n\n" if real_data else "")
            + "Write the exact SQL to verify the leads schema and diagnose the failures. "
            "Include a final SELECT to confirm."
        ),
        model="claude-haiku-4-5-20251001",
        max_tokens=700,
    )
    if llm_sql:
        artifacts.append({
            "type":    "sql",
            "title":   "Isabella's AI-Generated Schema Fix",
            "content": llm_sql,
        })

    return {
        "specialist":     "isabella_cruz",
        "name":           "Isabella Cruz",
        "role":           "VP Omnichannel Outreach",
        "assigned_count": len(mine),
        "status":         "complete",
        "artifacts":      artifacts,
    }


# ── Alexander Wright — Bond Channel & external API integration ───────────────

def _run_alexander(failures: list[dict]) -> dict[str, Any]:
    mine = [f for f in failures if f.get("specialist") == "alexander_wright"]
    if not mine:
        return {"specialist": "alexander_wright", "name": "Alexander Wright",
                "role": "VP Market Intelligence", "status": "no_assignment", "artifacts": []}

    ext_api_ok   = False
    ext_api_note = ""
    try:
        from . import alexander as alexander_agent
        mkt = alexander_agent.analyze_market(limit=5)
        ext_api_ok   = mkt.get("records_fetched", 0) > 0
        ext_api_note = (
            f"FMCSA DOT API: {mkt.get('records_fetched', 0)} records — "
            + ("reachable" if ext_api_ok else "no data returned")
        )
    except Exception as exc:
        ext_api_note = f"FMCSA DOT API: unreachable ({str(exc)[:80]})"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env_lines = [
        "# Alexander Wright — Render Environment Variables",
        f"# Generated: {now}",
        "# Render Dashboard → your service → Environment → Add variables → Save Changes",
        "",
        "# ── Bond Channel ─────────────────────────────────────────────────────",
        "# Generate: python -c \"import secrets; print(secrets.token_hex(32))\"",
        "BOND_API_KEY=<32-byte-hex-secret>",
        "",
        f"# External API: {ext_api_note}",
        "# ── DOT/FMCSA (optional) ─────────────────────────────────────────────",
        "DOT_API_KEY=<socrata-app-token>   # free at data.transportation.gov",
        "",
        f"# ── Daytona sandbox ─────────────────────────────────────────────────",
        f"# Sandbox ID: {_daytona_id()}",
        "IEBC_API_URL=https://three-lakes-logistics-api.onrender.com",
        "BOND_API_KEY=<same-value-as-Render>",
        "",
        "# ── Verify Bond endpoint after setting BOND_API_KEY ──────────────────",
        "# curl -H 'X-Bond-Key: <your-key>'",
        "#      https://three-lakes-logistics-api.onrender.com/api/bond/inbox",
        "# Expected: 200 {messages: [...]}",
    ]

    checklist_items = [
        {
            "area":  "Bond API Key",
            "steps": [
                "Run: python -c \"import secrets; print(secrets.token_hex(32))\"",
                "Add BOND_API_KEY to Render Environment Variables",
                f"Set IEBC_API_URL + BOND_API_KEY on Daytona sandbox ({_daytona_id()})",
                "Test: curl -H 'X-Bond-Key: <key>' <render-url>/api/bond/inbox",
            ],
        },
        {
            "area":  "External API Status",
            "steps": [
                f"Alexander's FMCSA check: {ext_api_note}",
                "If outbound APIs unreachable: check Render outbound network / DOT_API_KEY",
                "Bond Channel failures are usually env config, not outbound connectivity",
            ],
        },
        {
            "area":  "Verify",
            "steps": [
                "After env vars set → Render auto-redeploys (~60s)",
                "Eagle Eye → Test Suite → Run All Domains",
                "Bond Channel domain should show PASS",
            ],
        },
    ]

    artifacts: list[dict] = [
        {
            "type":    "env",
            "title":   "Render Environment Variables Template",
            "content": "\n".join(env_lines),
        },
        {
            "type":    "checklist",
            "title":   f"Integration Setup Checklist (FMCSA {'✓' if ext_api_ok else '✗'})",
            "content": checklist_items,
        },
    ]

    llm_config = _llm(
        system=(
            "You are Alexander Wright, VP Market Intelligence at 3 Lakes Logistics. "
            "You are an expert in external API integrations: FMCSA DOT API, Bond Channel, Render env vars. "
            "Write exact, copy-paste-ready environment variable configs and API setup steps. "
            "Include exact Render dashboard path, exact curl verification commands, "
            "and how to generate any secrets. No filler."
        ),
        user=(
            f"Failing Bond Channel / integration tests:\n{json.dumps(mine, indent=2)}\n\n"
            f"External API connectivity: {ext_api_note}\n\n"
            "Write the exact steps to fix each: which env vars to set, how to generate them, "
            "how to set on Render, and the exact curl command to verify each fix."
        ),
        model="claude-haiku-4-5-20251001",
        max_tokens=700,
    )
    if llm_config:
        artifacts.append({
            "type":    "env",
            "title":   "Alexander's AI-Generated Integration Fix",
            "content": llm_config,
        })

    return {
        "specialist":     "alexander_wright",
        "name":           "Alexander Wright",
        "role":           "VP Market Intelligence",
        "assigned_count": len(mine),
        "status":         "complete",
        "artifacts":      artifacts,
    }


# ── Katerina Rostova — Health, Dashboard & Telemetry (SLA audit) ─────────────

def _run_katerina(failures: list[dict]) -> dict[str, Any]:
    mine = [f for f in failures if f.get("specialist") == "katerina_rostova"]
    if not mine:
        return {"specialist": "katerina_rostova", "name": "Katerina Rostova",
                "role": "Head of Process Automation", "status": "no_assignment", "artifacts": []}

    real_data: dict[str, Any] = {}
    try:
        from . import katerina as katerina_agent
        real_data = katerina_agent.audit_sla()
    except Exception:
        pass

    diagnoses = []
    for f in mine:
        domain = f["domain"]
        error  = f.get("error", "")
        if real_data:
            loads_scanned  = real_data.get("loads_scanned", "?")
            sla_violations = real_data.get("sla_violations", "?")
            critical       = real_data.get("critical_violations", "?")
            if domain == "Health":
                cause = (
                    f"Backend health endpoint failing — Katerina's SLA audit scanned "
                    f"{loads_scanned} loads, found {sla_violations} violations. "
                    "Likely a Supabase connectivity or env var issue."
                )
                steps = [
                    "Verify SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in Render",
                    "Check /api/health/full — if supabase='error', fix DB credentials",
                    "Check /api/health/full — if stripe='error', set STRIPE_SECRET_KEY",
                ]
            elif domain == "Dashboard":
                cause = (
                    f"Dashboard KPIs failing — Katerina found {sla_violations} SLA violations "
                    f"({critical} critical). Load pipeline may be stalled, breaking KPI queries."
                )
                steps = [
                    "Check Render logs for exceptions in /api/dashboard/kpis",
                    f"Top SLA violations: {real_data.get('top_violations', [{}])[:1]}",
                    "Verify loads table is accessible: SELECT COUNT(*) FROM loads;",
                ]
            elif domain == "Telemetry":
                cause = (
                    f"Telemetry endpoint failing — Katerina audited {loads_scanned} loads. "
                    "Telemetry ping table may be missing or schema out of date."
                )
                steps = [
                    "Run: SELECT table_name FROM information_schema.tables WHERE table_name ILIKE '%telemetry%';",
                    "If missing: run sql/driver_schema_additions.sql in Supabase",
                    "Check Render logs for import errors in telemetry route",
                ]
            else:
                cause = f"Process failure in {domain} — {error[:80]}"
                steps = ["Check Render logs", "Verify Supabase connectivity", "Re-run after fix"]
        else:
            cause = f"Could not reach DB for {domain} audit — env config likely broken"
            steps = [
                "Verify SUPABASE_URL is correct in Render environment",
                "Verify SUPABASE_SERVICE_ROLE_KEY is the service_role key (not anon)",
                "Check Render logs for connection refused errors",
            ]
        diagnoses.append({"domain": domain, "test": f["test_name"], "cause": cause, "steps": steps})

    checklist_items = [
        {
            "area":  "Supabase Connectivity",
            "steps": [
                "Supabase → Project Settings → API → copy service_role secret",
                "Add SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to Render",
                "Run: curl <render-url>/api/health/full → expect {ok: true}",
            ],
        },
        {
            "area":  "Load Pipeline & SLA",
            "steps": (
                [
                    f"Katerina SLA audit: {real_data.get('loads_scanned','?')} loads, "
                    f"{real_data.get('sla_violations','?')} violations, "
                    f"{real_data.get('critical_violations','?')} critical",
                ]
                if real_data else ["SLA data unavailable — DB unreachable"]
            ) + [
                "Critical violations mean load statuses are stalled — check automation triggers",
                "Run Katerina agent via Eagle Eye → IEBC Executive Command to see violations",
            ],
        },
        {
            "area":  "Telemetry Schema",
            "steps": [
                "Supabase SQL Editor: SELECT COUNT(*) FROM telemetry_pings;",
                "If table missing: run sql/driver_schema_additions.sql",
                "Set ELD_API_KEY env var if using live ELD data",
            ],
        },
    ]

    artifacts: list[dict] = [
        {
            "type":    "diagnosis",
            "title":   (
                f"Katerina's Process & SLA Analysis ({real_data.get('loads_scanned','?')} loads)"
                if real_data else "Process Analysis"
            ),
            "content": diagnoses,
        },
        {
            "type":    "checklist",
            "title":   "Infrastructure & SLA Remediation Checklist",
            "content": checklist_items,
        },
    ]

    llm_plan = _llm(
        system=(
            "You are Katerina Rostova, Head of Process Automation at 3 Lakes Logistics. "
            "Your job is auditing load SLA violations and mapping failures to corrective automation steps. "
            "Write precise, numbered remediation steps for infrastructure failures. "
            "Include exact SQL, exact env var names, and exact Render dashboard paths."
        ),
        user=(
            f"Failing Health/Dashboard/Telemetry tests:\n{json.dumps(mine, indent=2)}\n\n"
            + (f"Live SLA audit data:\n{json.dumps(real_data, indent=2)}\n\n" if real_data else "")
            + "Write the exact remediation steps for each failure. "
            "Prioritize by impact. Include SQL verification after each step."
        ),
        model="claude-haiku-4-5-20251001",
        max_tokens=700,
    )
    if llm_plan:
        artifacts.append({
            "type":    "checklist",
            "title":   "Katerina's AI-Generated Remediation Plan",
            "content": [{"area": "AI Analysis", "steps": llm_plan.split("\n")}],
        })

    return {
        "specialist":     "katerina_rostova",
        "name":           "Katerina Rostova",
        "role":           "Head of Process Automation",
        "assigned_count": len(mine),
        "status":         "complete",
        "artifacts":      artifacts,
    }


# ── Penny — Driver, Payout & Stripe integrity ────────────────────────────────

def _run_penny(failures: list[dict]) -> dict[str, Any]:
    mine = [f for f in failures if f.get("specialist") == "penny"]
    if not mine:
        return {"specialist": "penny", "name": "Penny", "role": "Stripe & Payments Specialist",
                "status": "no_assignment", "artifacts": []}

    stripe_ok   = False
    stripe_note = ""
    try:
        from . import penny as penny_agent
        # Verify Stripe key is configured by attempting the run entrypoint
        penny_agent.run({})
        stripe_ok   = True
        stripe_note = "Stripe agent reachable — key configured"
    except Exception as exc:
        stripe_note = f"Stripe agent error: {str(exc)[:100]}"

    diagnoses = []
    for f in mine:
        domain = f["domain"]
        error  = f.get("error", "")
        ftype  = f.get("failure_type", "")
        if ftype == "idempotency":
            cause = (
                "Payout idempotency guard missing — /api/payout/request can be submitted twice "
                "for the same load_id, causing duplicate driver payments."
            )
            steps = [
                "Open backend/app/api/routes_payout.py — find request_payout()",
                "Add idempotency key check: query payout_history for existing load_id before processing",
                "Return 409 Conflict if same load_id+driver_id already paid",
                "Add a unique index: CREATE UNIQUE INDEX IF NOT EXISTS ux_payout_load "
                "ON payout_history(load_id, driver_id);",
                "Test: POST same load_id twice — second must return 409",
            ]
        elif ftype == "rate_limit":
            cause = (
                "Driver auth endpoint has no rate limiting — brute force login is possible. "
                "Blueprint requires max 5 attempts before lockout."
            )
            steps = [
                "Add slowapi or fastapi-limiter to requirements.txt",
                "Decorate /api/driver-auth/login with @limiter.limit('5/minute')",
                "Return 429 Too Many Requests after threshold",
                "Test: 6 rapid bad PINs — 6th must return 429",
            ]
        elif ftype == "auth":
            cause = (
                f"Driver auth guard failing in {domain} domain — "
                f"either token validation broken or test using wrong token format."
            )
            steps = [
                "Verify require_driver_token() in routes_driver_auth.py reads Authorization header",
                "Confirm test token format: 'Bearer <token>'",
                "Check active_drivers table has the test driver row",
                "Run: GET /api/driver-auth/me with a known-good token",
            ]
        else:
            cause = f"Driver/{domain} failure: {error[:100]}"
            steps = [
                "Check Render logs for driver/payout route errors",
                f"Verify {domain.lower()} route handler in backend/app/api/",
                "Confirm Stripe env vars: STRIPE_SECRET_KEY set on Render",
            ]
        diagnoses.append({"domain": domain, "test": f["test_name"], "cause": cause, "steps": steps})

    artifacts: list[dict] = [
        {
            "type":    "diagnosis",
            "title":   f"Penny's Driver & Payment Analysis ({stripe_note})",
            "content": diagnoses,
        },
        {
            "type":    "checklist",
            "title":   "Payment & Driver Auth Remediation",
            "content": [
                {
                    "area":  "Payout Idempotency",
                    "steps": [
                        "Add unique constraint on payout_history(load_id, driver_id)",
                        "Check for existing payout before processing: SELECT id FROM payout_history WHERE load_id=$1 AND driver_id=$2",
                        "Return 409 Conflict on duplicate — never process twice",
                    ],
                },
                {
                    "area":  "Driver Auth Rate Limiting",
                    "steps": [
                        "Install slowapi: pip install slowapi",
                        "Add @limiter.limit('5/minute') to /api/driver-auth/login",
                        "Verify STRIPE_SECRET_KEY is in Render env vars",
                    ],
                },
            ],
        },
    ]

    llm_plan = _llm(
        system=(
            "You are Penny, Stripe & Payments Specialist at 3 Lakes Logistics. "
            "You own driver authentication, payout processing, and Stripe subscription lifecycle. "
            "Write precise remediation steps for driver auth and financial logic failures. "
            "Focus on: idempotency, rate limiting, Stripe key configuration, payout math."
        ),
        user=(
            f"Failing Driver/Security tests:\n{json.dumps(mine, indent=2)}\n\n"
            f"Stripe status: {stripe_note}\n\n"
            "Write numbered remediation steps. Include exact code changes and SQL."
        ),
        model="claude-haiku-4-5-20251001",
        max_tokens=700,
    )
    if llm_plan:
        artifacts.append({
            "type":    "checklist",
            "title":   "Penny's AI-Generated Remediation Plan",
            "content": [{"area": "AI Analysis", "steps": llm_plan.split("\n")}],
        })

    return {
        "specialist":     "penny",
        "name":           "Penny",
        "role":           "Stripe & Payments Specialist",
        "assigned_count": len(mine),
        "status":         "complete",
        "artifacts":      artifacts,
    }


# ── Shield — Security, Webhooks & CDL compliance ─────────────────────────────

def _run_shield(failures: list[dict]) -> dict[str, Any]:
    mine = [f for f in failures if f.get("specialist") == "shield"]
    if not mine:
        return {"specialist": "shield", "name": "Shield", "role": "Security & Compliance Specialist",
                "status": "no_assignment", "artifacts": []}

    cdl_data: dict[str, Any] = {}
    cdl_note = ""
    try:
        from . import shield as shield_agent
        cdl_data = shield_agent.run_cdl_sweep()
        checked  = cdl_data.get("carriers_checked", 0)
        alerts   = len(cdl_data.get("cdl_alerts", []))
        cdl_note = f"CDL sweep: {checked} carriers, {alerts} expiry alert(s)"
    except Exception as exc:
        cdl_note = f"CDL sweep unavailable: {str(exc)[:80]}"

    diagnoses = []
    for f in mine:
        domain = f["domain"]
        error  = f.get("error", "")
        ftype  = f.get("failure_type", "")
        if ftype == "webhook_security":
            cause = (
                "Webhook signature verification missing or broken — "
                "forged Stripe/Vapi/Motive requests are not rejected. "
                "An attacker can manipulate financial ledgers without a valid signature."
            )
            steps = [
                "Open backend/app/api/routes_webhooks.py",
                "Verify stripe: penny.verify_and_parse(payload, sig) — raises ValueError on bad sig → returns 400",
                "Add STRIPE_WEBHOOK_SECRET to Render env vars (get from Stripe Dashboard → Webhooks)",
                "For Vapi/Motive: add X-Vapi-Signature or shared-secret header validation",
                "Test: POST /api/webhooks/stripe with no Stripe-Signature → must return 400",
            ]
        elif ftype == "privilege_escalation":
            cause = (
                "Horizontal privilege escalation possible — driver tokens accepted on executive routes. "
                "Blueprint requires executive routes to verify IEBC API token, not driver tokens."
            )
            steps = [
                "Open backend/app/api/routes_executives.py",
                "Verify all routes use require_bearer (IEBC API token) not require_driver_token",
                "Confirm require_bearer checks against settings.api_bearer_token",
                "Test: GET /api/executives/dashboard with fake driver token → must return 401/403",
            ]
        elif ftype == "auth":
            cause = f"Security auth test failing in {domain}: {error[:100]}"
            steps = [
                f"Check {domain.lower()} route auth dependency in backend/app/api/",
                "Verify require_bearer or equivalent is applied to the route",
                "Confirm no route is accidentally left without auth guard",
            ]
        else:
            cause = f"Security/Integration failure in {domain}: {error[:100]}"
            steps = [
                "Review security middleware in backend/app/",
                "Check webhook handler error responses (must be 4xx not 5xx)",
                "Verify external service graceful degradation paths",
            ]
        diagnoses.append({"domain": domain, "test": f["test_name"], "cause": cause, "steps": steps})

    artifacts: list[dict] = [
        {
            "type":    "diagnosis",
            "title":   f"Shield's Security Analysis ({cdl_note})",
            "content": diagnoses,
        },
        {
            "type":    "checklist",
            "title":   "Security Hardening Checklist",
            "content": [
                {
                    "area":  "Webhook Signature Verification",
                    "steps": [
                        "Set STRIPE_WEBHOOK_SECRET in Render env vars",
                        "Verify penny.verify_and_parse raises ValueError on missing/bad sig",
                        "Add similar signature check to Vapi and Motive webhook handlers",
                        "All forged webhook tests must return 400, never 200",
                    ],
                },
                {
                    "area":  "Privilege Escalation Prevention",
                    "steps": [
                        "Audit routes_executives.py — all routes must use require_bearer",
                        "Audit routes_agents.py — all routes must use require_bearer",
                        "Driver tokens (require_driver_token) must NOT access executive routes",
                        "Run privilege escalation tests after fix to confirm 401/403",
                    ],
                },
                {
                    "area":  "CDL & Compliance Status",
                    "steps": [cdl_note] + [
                        f"Alert: {a.get('driver_id','?')} CDL expires {a.get('expiry','?')}"
                        for a in (cdl_data.get("cdl_alerts") or [])[:3]
                    ],
                },
            ],
        },
    ]

    llm_plan = _llm(
        system=(
            "You are Shield, Security & Compliance Specialist at 3 Lakes Logistics. "
            "You own webhook signature verification, FMCSA safety checks, CDL monitoring, "
            "and preventing privilege escalation. "
            "Write precise, numbered security remediation steps. "
            "Include exact code locations, env var names, and verification commands."
        ),
        user=(
            f"Failing Security/Integration tests:\n{json.dumps(mine, indent=2)}\n\n"
            f"CDL sweep: {cdl_note}\n\n"
            "Write remediation steps for each security failure. "
            "Prioritize: webhook forgery prevention first, then privilege escalation."
        ),
        model="claude-haiku-4-5-20251001",
        max_tokens=700,
    )
    if llm_plan:
        artifacts.append({
            "type":    "checklist",
            "title":   "Shield's AI-Generated Security Plan",
            "content": [{"area": "AI Analysis", "steps": llm_plan.split("\n")}],
        })

    return {
        "specialist":     "shield",
        "name":           "Shield",
        "role":           "Security & Compliance Specialist",
        "assigned_count": len(mine),
        "status":         "complete",
        "artifacts":      artifacts,
    }


# ── Bond coordination ─────────────────────────────────────────────────────────

def _bond_coordinate(classified: list[dict], results: list[dict]) -> dict[str, Any]:
    domains = sorted({f["domain"] for f in classified})
    active  = [r for r in results if r.get("status") == "complete"]
    priority = "high" if len(classified) >= 3 else "normal"

    lines = [
        "IEBC TECHNICAL TEAM REMEDIATION REPORT",
        "Coordinator: James Bond, IEBC Consultant",
        f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Failures: {len(classified)} across {len(domains)} domain(s): {', '.join(domains)}",
        "",
        "TEAM ASSIGNMENTS COMPLETE:",
    ]
    for r in active:
        lines.append(
            f"  {r['name']} ({r['role']}): {r['assigned_count']} failure(s) — artifacts ready"
        )

    lines += [
        "",
        "PRIORITY FIX ORDER:",
        "  1. Shield's security audit — webhook signature verification + privilege escalation blocks",
        "  2. Katerina's checklist — verify Supabase connectivity, SLA pipeline, triggers",
        "  3. Isabella's SQL — verify/create leads table and check schema",
        "  4. Alexander's env vars — set BOND_API_KEY on Render + Daytona; verify integration endpoints",
        "  5. Winston's health snapshot — confirm carrier data accessible",
        "  6. Penny's payment audit — payout idempotency + driver auth rate limiting",
        "  7. Re-run Test Suite — all 11 domains should pass",
        "",
        "EXTERNAL BOND DIRECTIVE:",
        f"  Daytona sandbox {_daytona_id()}:",
        "  · Verify IEBC_API_URL points to the Render API",
        "  · Verify BOND_API_KEY matches the Render env var",
        "  · Run: curl $IEBC_API_URL/api/health/ping",
        "  · Verify STRIPE_WEBHOOK_SECRET is set on Render (Shield priority)",
        "  · Report connectivity status back to IEBC Internal",
        "",
        "BOND TO COMMANDER: Shield's security hardening first, then Katerina's infrastructure, then re-test.",
    ]

    escalate = any(
        f.get("failure_type") in ("connection", "api_key", "auth", "missing_table")
        for f in classified
    )

    return {
        "coordinator":         "James Bond",
        "directive":           "\n".join(lines),
        "escalate_to_external": escalate,
        "priority":            priority,
        "domains_affected":    domains,
    }


# ── Self-healing engine ───────────────────────────────────────────────────────

_BOND_CHANNEL_DDL = """
CREATE TABLE IF NOT EXISTS bond_channel (
    id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    direction    TEXT        NOT NULL CHECK (direction IN ('internal_to_external','external_to_internal')),
    from_label   TEXT        NOT NULL,
    message_type TEXT        NOT NULL DEFAULT 'directive'
                 CHECK (message_type IN ('directive','report','feedback','suggestion','acknowledgment')),
    content      TEXT        NOT NULL,
    priority     TEXT        NOT NULL DEFAULT 'normal'
                 CHECK (priority IN ('critical','high','normal','low')),
    status       TEXT        NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','delivered','read','actioned')),
    metadata     JSONB       DEFAULT '{}',
    created_at   TIMESTAMPTZ DEFAULT now(),
    updated_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS bond_channel_direction_status
    ON bond_channel (direction, status, created_at);
""".strip()


def _env_status() -> dict[str, bool]:
    from ..settings import get_settings
    import os
    s = get_settings()
    return {
        "SUPABASE_URL":              bool(s.supabase_url),
        "SUPABASE_SERVICE_ROLE_KEY": bool(s.supabase_service_role_key),
        "SUPABASE_ANON_KEY":         bool(s.supabase_anon_key),
        "API_BEARER_TOKEN":          bool(s.api_bearer_token),
        "BOND_API_KEY":              bool(os.getenv("BOND_API_KEY")),
        "ANTHROPIC_API_KEY":         bool(s.anthropic_api_key),
        "STRIPE_SECRET_KEY":         bool(s.stripe_secret_key),
        "RENDER_API_KEY":            bool(s.render_api_key),
    }


def _table_exists(table_name: str) -> bool:
    try:
        get_supabase().table(table_name).select("*").limit(0).execute()
        return True
    except Exception:
        return False


def _exec_sql_via_rpc(ddl: str) -> tuple[bool, str]:
    """Attempt DDL via Supabase RPC exec_sql function, then httpx fallback."""
    from ..settings import get_settings
    import httpx, os

    # Try via supabase-py RPC
    try:
        get_supabase().rpc("exec_sql", {"sql_statement": ddl}).execute()
        return True, "executed via RPC"
    except Exception:
        pass

    # Fallback: httpx direct to Supabase REST with service role
    s = get_settings()
    key = s.supabase_service_role_key or s.supabase_anon_key
    if not s.supabase_url or not key:
        return False, "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set"
    try:
        r = httpx.post(
            f"{s.supabase_url}/rest/v1/rpc/exec_sql",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={"sql_statement": ddl},
            timeout=15,
        )
        if r.is_success:
            return True, "executed via REST RPC"
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as exc:
        return False, f"httpx error: {exc}"


def _trigger_render_deploy(render_api_key: str, service_name: str = "three-lakes-logistics-api") -> tuple[bool, str]:
    """List Render services and trigger a manual deploy on the matching one."""
    import httpx
    try:
        headers = {"Authorization": f"Bearer {render_api_key}", "Accept": "application/json"}
        # List services to find the service ID
        r = httpx.get("https://api.render.com/v1/services?limit=20", headers=headers, timeout=15)
        if not r.is_success:
            return False, f"Could not list Render services: {r.status_code}"
        services = r.json()
        service_id = None
        for svc in services:
            name = (svc.get("service", {}) or svc).get("name", "")
            if service_name.lower() in name.lower():
                service_id = (svc.get("service", {}) or svc).get("id")
                break
        if not service_id:
            return False, f"Service '{service_name}' not found in Render account"
        dr = httpx.post(
            f"https://api.render.com/v1/services/{service_id}/deploys",
            headers={**headers, "Content-Type": "application/json"},
            json={"clearCache": "do_not_clear"},
            timeout=15,
        )
        if dr.is_success:
            return True, f"Deploy triggered (service={service_id})"
        return False, f"Deploy failed: {dr.status_code} {dr.text[:200]}"
    except Exception as exc:
        return False, f"Render API error: {exc}"


def _autofix(classified: list[dict]) -> dict[str, Any]:
    """Attempt automated repairs. Returns {fixed, needs_manual, env_status, table_status}."""
    from ..settings import get_settings
    s = get_settings()

    env  = _env_status()
    fixed: list[dict]        = []
    needs_manual: list[dict] = []
    attempted: list[dict]    = []

    # ── 1. Table existence checks ─────────────────────────────────────────────
    critical_tables = ["bond_channel", "agent_memory", "leads", "carriers"]
    table_status = {t: _table_exists(t) for t in critical_tables}

    # Auto-create bond_channel if missing
    if not table_status.get("bond_channel"):
        ok, msg = _exec_sql_via_rpc(_BOND_CHANNEL_DDL)
        if ok:
            table_status["bond_channel"] = True
            fixed.append({"area": "Schema", "action": "Created bond_channel table", "detail": msg})
        else:
            needs_manual.append({
                "area":   "Schema",
                "action": "Create bond_channel table",
                "how":    "Open Supabase SQL Editor → run sql/bond_channel.sql from the repo",
                "reason": msg,
            })

    # ── 2. Env var audit ──────────────────────────────────────────────────────
    required_core = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "API_BEARER_TOKEN"]
    missing_core  = [k for k in required_core if not env.get(k)]
    if missing_core:
        needs_manual.append({
            "area":   "Config",
            "action": "Set missing environment variables",
            "how":    f"Render Dashboard → Environment → add: {', '.join(missing_core)}",
            "reason": "Core env vars absent — all endpoints will fail",
        })
    else:
        fixed.append({"area": "Config", "action": "Core env vars verified present"})

    if not env.get("BOND_API_KEY"):
        needs_manual.append({
            "area":   "Config",
            "action": "Set BOND_API_KEY",
            "how":    "Generate: python -c \"import secrets; print(secrets.token_hex(32))\" then add to Render + Daytona",
            "reason": "Bond Channel external auth will reject all requests",
        })

    # ── 3. Failure-specific repairs ───────────────────────────────────────────
    for f in classified:
        ftype  = f.get("failure_type", "")
        domain = f.get("domain", "")

        if ftype == "code_bug":
            needs_manual.append({
                "area":   "Code",
                "action": f"Fix endpoint in {domain}",
                "how":    "Open Render → Logs → find Traceback → fix code → push to main",
                "reason": "Backend exception — requires code change and deploy",
            })

        if ftype == "connection" and env.get("SUPABASE_URL") and env.get("SUPABASE_SERVICE_ROLE_KEY"):
            # Try a live Supabase ping
            try:
                get_supabase().table("agent_memory").select("*").limit(0).execute()
                fixed.append({"area": "Connection", "action": "Supabase connectivity verified"})
            except Exception as exc:
                needs_manual.append({
                    "area":   "Connection",
                    "action": "Supabase connection failed",
                    "how":    "Verify SUPABASE_URL is correct and SUPABASE_SERVICE_ROLE_KEY is the service_role key (not anon)",
                    "reason": str(exc)[:120],
                })

    # ── 4. Trigger Render redeploy if fixes were applied ─────────────────────
    if fixed and s.render_api_key:
        ok, msg = _trigger_render_deploy(s.render_api_key)
        if ok:
            fixed.append({"area": "Deploy", "action": "Render redeploy triggered", "detail": msg})
        else:
            attempted.append({"area": "Deploy", "action": "Render redeploy", "result": msg})
    elif fixed and not s.render_api_key:
        needs_manual.append({
            "area":   "Deploy",
            "action": "Manually redeploy on Render",
            "how":    "Render Dashboard → Manual Deploy → Deploy latest commit (or set RENDER_API_KEY for auto-deploy)",
            "reason": "RENDER_API_KEY not set — cannot trigger programmatic deploy",
        })

    return {
        "fixed":        fixed,
        "needs_manual": needs_manual,
        "attempted":    attempted,
        "env_status":   env,
        "table_status": table_status,
        "auto_fixed_count": len(fixed),
        "manual_count":     len(needs_manual),
    }


# ── Dual-Bond autonomous mission ─────────────────────────────────────────────

_API_BASE = "https://three-lakes-logistics-api.onrender.com"
_REPO     = "modom123/3-lakes-logistics"

# Maps failure type → exact executable fix block
def _executable_fix(f: dict, fix_num: int) -> str:
    ftype  = f.get("failure_type", "code_bug")
    domain = f.get("domain", "?")
    error  = f.get("error",  "unknown error")
    test   = f.get("test_name", "?")

    sep = "─" * 58

    if ftype == "missing_table" or ("bond" in domain.lower() and ftype == "schema_error"):
        return f"""{sep}
FIX {fix_num} [SQL — EXECUTE NOW]: Create bond_channel table
{sep}
OPEN: https://app.supabase.com → your project → SQL Editor → New Query
PASTE AND RUN:

{_BOND_CHANNEL_DDL}

VERIFY (run immediately after):
  SELECT COUNT(*) FROM bond_channel;
  -- Expected: returns a row with count = 0

DONE? Report: fixes_applied = ["bond_channel table created"]
"""

    if ftype in ("api_key", "auth") and "bond" in domain.lower():
        return f"""{sep}
FIX {fix_num} [ENV VAR — EXECUTE NOW]: Set BOND_API_KEY on both sides
{sep}
STEP 1 — Generate the key (run this command):
  python -c "import secrets; print(secrets.token_hex(32))"
  -- Copy the output. This is your BOND_API_KEY.

STEP 2 — Set on Render:
  Go to: https://dashboard.render.com → 3-lakes-logistics-api → Environment
  Add:   BOND_API_KEY = <your-generated-key>
  Click: Save Changes  (auto-redeploys in ~60s)

STEP 3 — Set on Daytona sandbox (your side):
  export BOND_API_KEY=<same-key>
  export IEBC_API_URL={_API_BASE}

VERIFY (after Render redeploy completes):
  curl -H "X-Bond-Key: <your-key>" {_API_BASE}/api/bond/inbox
  -- Expected: HTTP 200  {{"messages": []}}

DONE? Report: fixes_applied = ["BOND_API_KEY configured on Render + Daytona"]
"""

    if ftype in ("connection", "database"):
        return f"""{sep}
FIX {fix_num} [ENV VAR — EXECUTE NOW]: Fix Supabase connection
{sep}
STEP 1 — Get credentials:
  Go to: https://app.supabase.com → your project → Settings → API
  Copy:  Project URL  (looks like https://xxxx.supabase.co)
  Copy:  service_role secret  (NOT the anon key — use service_role)

STEP 2 — Set on Render:
  SUPABASE_URL             = https://<project-ref>.supabase.co
  SUPABASE_SERVICE_ROLE_KEY = <service-role-secret>

STEP 3 — Trigger redeploy:
  Render Dashboard → Manual Deploy → Deploy latest commit
  Wait ~60s for deploy to complete.

VERIFY:
  curl {_API_BASE}/api/health/full
  -- Expected: {{"ok": true, "services": {{"supabase": "ok"}}}}

DONE? Report: fixes_applied = ["Supabase env vars set, health/full passes"]
"""

    if ftype in ("code_bug", "endpoint_error"):
        route_map = {
            "Carriers":     "backend/app/api/routes_carriers.py",
            "Fleet":        "backend/app/api/routes_fleet.py",
            "Leads":        "backend/app/api/routes_leads.py",
            "Telemetry":    "backend/app/api/routes_telemetry.py",
            "Dashboard":    "backend/app/api/routes_dashboard.py",
            "Bond Channel": "backend/app/api/routes_bond.py",
            "Health":       "backend/app/api/health.py",
        }
        route_file = route_map.get(domain, f"backend/app/api/routes_{domain.lower().replace(' ','_')}.py")
        return f"""{sep}
FIX {fix_num} [CODE FIX — EXECUTE NOW]: Fix {domain} endpoint
{sep}
FAILURE: {test}
ERROR:   {error}

STEP 1 — Diagnose:
  curl -H "Authorization: Bearer taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE" \\
       {_API_BASE}/api/{domain.lower().replace(' ','-')}/
  -- If HTTP 500: check Render Logs for traceback
  -- If wrong shape: route returns raw list instead of {{count, items}}

STEP 2 — Clone repo and check route file:
  git clone https://github.com/{_REPO}.git
  cd 3-lakes-logistics
  cat {route_file}

STEP 3 — Common fix (wrong response shape):
  Find the list endpoint returning a raw list and wrap it:
  BEFORE:  return res.data
  AFTER:   return {{"count": len(res.data), "items": res.data}}

STEP 4 — Push fix:
  git add {route_file}
  git commit -m "fix: {domain.lower()} list endpoint response shape"
  git push origin main
  -- Render auto-deploys on push to main (~90s)

VERIFY (after deploy):
  curl -H "Authorization: Bearer taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE" \\
       {_API_BASE}/api/{domain.lower().replace(' ','-')}/
  -- Expected: {{"count": N, "items": [...]}}

DONE? Report: fixes_applied = ["{domain} route fixed"], code_pushed = true
"""

    if ftype == "response_shape":
        return f"""{sep}
FIX {fix_num} [CODE FIX — EXECUTE NOW]: Fix {domain} response shape
{sep}
FAILURE: {test}
ERROR:   {error}

The endpoint is not returning the expected {{count, items}} envelope.

STEP 1 — Pull repo:
  git clone https://github.com/{_REPO}.git && cd 3-lakes-logistics

STEP 2 — Search for the broken return:
  grep -n "return res.data\\|return items\\|return data" backend/app/api/

STEP 3 — Wrap the response:
  Change any bare list return to:
  return {{"count": len(items), "items": items}}

STEP 4 — Push:
  git add -A && git commit -m "fix: {domain.lower()} response envelope" && git push origin main

DONE? Report: fixes_applied = ["{domain} shape fixed + pushed"]
"""

    # Default
    return f"""{sep}
FIX {fix_num} [DIAGNOSE + FIX]: {domain} — {test}
{sep}
ERROR: {error}

STEP 1: curl -H "Authorization: Bearer taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE" \\
             {_API_BASE}/api/{domain.lower().replace(' ','-')}/

STEP 2: Check Render Logs for exceptions at that timestamp.

STEP 3: Identify fix (missing env var / bad query / import error).

STEP 4: Apply fix and either:
  - Set env var in Render dashboard, OR
  - Push code fix: git push origin main

DONE? Report: fixes_applied = ["describe what you did"]
"""


def _build_mission_directive(
    classified: list[dict],
    autofix: dict,
    bond_brief: str,
    iteration: int = 1,
) -> str:
    env     = autofix.get("env_status", {})
    fixed   = autofix.get("fixed", [])
    manual  = autofix.get("needs_manual", [])
    ts      = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Only send remaining failures (those not already fixed internally)
    fixed_areas = {f.get("area","").lower() for f in fixed}
    remaining = [
        f for f in classified
        if not any(a in f.get("domain","").lower() for a in fixed_areas)
    ]
    priority = "CRITICAL" if len(remaining) >= 3 else "HIGH"

    lines = [
        f"╔══════════════════════════════════════════════════════════════╗",
        f"║  BOND-TO-BOND EXECUTABLE FIX DIRECTIVE  ·  Iteration {iteration:<6}║",
        f"╚══════════════════════════════════════════════════════════════╝",
        f"",
        f"FROM:     James Bond · IEBC Internal · {ts}",
        f"TO:       External Bond · Daytona {_daytona_id()}",
        f"PRIORITY: {priority}",
        f"API:      {_API_BASE}",
        f"REPO:     https://github.com/{_REPO}",
        f"",
        f"━━ SITUATION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Test suite: {len(classified)} failure(s) across {len({f['domain'] for f in classified})} domain(s)",
        f"Internal team fixed: {len(fixed)} item(s) automatically",
        f"Remaining for you:   {len(remaining)} fix instruction(s) below",
        f"",
    ]

    if fixed:
        lines.append("━━ ALREADY DONE (internal team) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        for f in fixed:
            lines.append(f"  ✓ [{f.get('area','?')}] {f.get('action','')}")
        lines.append("")

    if not remaining:
        lines += [
            "━━ NO REMAINING FAILURES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "Internal team resolved all failures. Run the test suite to confirm.",
            "",
        ]
    else:
        lines += [
            f"━━ YOUR {len(remaining)} FIX INSTRUCTION(S) — EXECUTE IN ORDER ━━━━━━━━━━",
            "Do not investigate. Execute each step. Verify. Report completion.",
            "",
        ]
        seen = set()
        fix_num = 1
        for f in remaining:
            key = (f.get("failure_type"), f.get("domain"))
            if key in seen:
                continue
            seen.add(key)
            lines.append(_executable_fix(f, fix_num))
            fix_num += 1

    lines += [
        "━━ WHEN ALL FIXES ARE DONE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"POST {_API_BASE}/api/bond/report",
        f"Header: X-Bond-Key: <BOND_API_KEY>",
        f"Body (JSON):",
        f'  {{',
        f'    "message_type": "report",',
        f'    "content": "FIXES COMPLETE — [describe each fix applied]",',
        f'    "metadata": {{',
        f'      "fixes_applied": ["fix 1 description", "fix 2 description"],',
        f'      "code_pushed":   true,',
        f'      "sql_executed":  true,',
        f'      "env_vars_set":  ["BOND_API_KEY"],',
        f'      "ready_to_test": true',
        f'    }}',
        f'  }}',
        f"",
        f"BOND DIRECTIVE: Execute fixes now. Do not wait. Report when each step completes.",
    ]

    return "\n".join(lines)


def run_autonomous_mission(failures: list[dict], iteration: int = 1) -> dict[str, Any]:
    """Full dual-bond mission: autofix internally, brief External Bond, return mission state."""
    from . import james_bond as jb

    # Classify
    classified = []
    for f in failures:
        ftype = _classify(f.get("test_name",""), f.get("domain",""), f.get("error",""))
        sid   = _assign(ftype, f.get("domain",""))
        classified.append({**f, "failure_type": ftype, "specialist": sid})

    # Phase 1 — internal autofix
    autofix = _autofix(classified)

    # Phase 2 — James Bond strategic brief
    try:
        bond_report = jb.run({"scope": "tech", "top_n": 3})
        brief = bond_report.get("executive_brief", "")
    except Exception:
        brief = "Tech audit unavailable — proceeding with test data only."

    # Phase 3 — compose External Bond directive (LLM if available, template fallback)
    env_status    = autofix.get("env_status", {})
    fixed_summary = [f.get("action","") for f in autofix.get("fixed", [])]
    manual_items  = [m.get("action","") for m in autofix.get("needs_manual", [])]
    missing_env   = [k for k,v in env_status.items() if not v]

    llm_directive = _llm(
        system=(
            "You are James Bond, IEBC Internal Consultant. "
            "You write bond-to-bond directives: short, numbered, executable fix instructions "
            "for a field operative (External Bond) who will run commands, push code, and execute SQL immediately. "
            "Each FIX block must contain: exact command or SQL, exact verification step, and what to report back. "
            "No investigation language. No 'consider' or 'check'. Use 'RUN', 'EXECUTE', 'PUSH', 'SET'."
        ),
        user=(
            f"Iteration: {iteration}\n"
            f"Test failures remaining:\n{json.dumps(classified, indent=2)}\n\n"
            f"Already fixed internally: {fixed_summary}\n"
            f"Still needs human/External Bond: {manual_items}\n"
            f"Missing env vars on Render: {missing_env}\n"
            f"Render API: https://three-lakes-logistics-api.onrender.com\n"
            f"Repo: modom123/3-lakes-logistics (push to main)\n"
            f"Daytona sandbox: {_daytona_id()}\n\n"
            "Write numbered FIX instructions. Each fix must be immediately executable by External Bond. "
            "End with: POST /api/bond/report when all done."
        ),
        model="claude-sonnet-4-6",
        max_tokens=1800,
    )
    directive = llm_directive if llm_directive else _build_mission_directive(classified, autofix, brief, iteration)

    # Phase 4 — send to External Bond
    ext_sent = False
    ext_msg_id = None
    try:
        result = bond_courier.send_directive(
            content=directive,
            priority="critical" if len(classified) >= 3 else "high",
            metadata={
                "source":          "dual_bond_autonomous",
                "iteration":       iteration,
                "failure_count":   len(classified),
                "internal_fixed":  len(autofix.get("fixed", [])),
                "sandbox_id":      _daytona_id(),
            },
        )
        ext_sent   = True
        ext_msg_id = result.get("message", {}).get("id")
    except Exception as exc:
        log_agent(_NAME, "send_directive", result=f"failed: {exc}")

    mem.remember(
        _NAME, "autonomous_mission",
        {
            "iteration":      iteration,
            "timestamp":      datetime.now(timezone.utc).isoformat(),
            "failure_count":  len(classified),
            "internal_fixed": len(autofix.get("fixed", [])),
            "external_sent":  ext_sent,
            "ext_msg_id":     ext_msg_id,
        },
        confidence=0.9,
        summary=f"Dual-Bond mission iteration {iteration}: {len(classified)} failures, {len(autofix.get('fixed',[]))} fixed internally, External Bond {'alerted' if ext_sent else 'unreachable'}",
    )

    log_agent(_NAME, "autonomous_mission",
              payload={"iteration": iteration, "failures": len(classified)},
              result=f"internal_fixed={len(autofix.get('fixed',[]))} ext_sent={ext_sent}")

    return {
        "agent":        _NAME,
        "action":       "autonomous",
        "iteration":    iteration,
        "classified":   classified,
        "autofix":      autofix,
        "bond_brief":   brief,
        "directive":    directive,
        "external_bond": {
            "sent":       ext_sent,
            "message_id": ext_msg_id,
            "sandbox_id": _daytona_id(),
        },
        "timestamp":    datetime.now(timezone.utc).isoformat(),
    }


# ── Main run ──────────────────────────────────────────────────────────────────

def run(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action", "remediate")).lower()

    if action == "status":
        last = mem.recall(_NAME, "last_remediation")
        return {"agent": _NAME, "action": "status", "last_remediation": last}

    if action == "autofix":
        raw = payload.get("failures", [])
        classified = []
        for f in raw:
            ftype = _classify(f.get("test_name",""), f.get("domain",""), f.get("error",""))
            sid   = _assign(ftype, f.get("domain",""))
            classified.append({**f, "failure_type": ftype, "specialist": sid})
        result = _autofix(classified)
        mem.remember(
            _NAME, "last_autofix",
            {"timestamp": datetime.now(timezone.utc).isoformat(), **result},
            confidence=0.85,
            summary=f"Autofix: {result['auto_fixed_count']} fixed, {result['manual_count']} need manual",
        )
        log_agent(_NAME, "autofix",
                  payload={"failure_count": len(classified)},
                  result=f"fixed={result['auto_fixed_count']} manual={result['manual_count']}")
        return {"agent": _NAME, "action": "autofix", **result}

    if action == "env_check":
        return {"agent": _NAME, "action": "env_check", "env_status": _env_status()}

    if action == "autonomous":
        raw = payload.get("failures", [])
        if not raw:
            return {"agent": _NAME, "error": "failures required for autonomous mission"}
        return run_autonomous_mission(raw, int(payload.get("iteration", 1)))

    if action != "remediate":
        return {"agent": _NAME, "error": f"unknown action: {action}"}

    raw = payload.get("failures", [])
    if not raw:
        return {"agent": _NAME, "error": "failures list is required"}

    # Classify + assign by domain (real agents own their domain data)
    classified = []
    for f in raw:
        ftype = _classify(f.get("test_name",""), f.get("domain",""), f.get("error",""))
        sid   = _assign(ftype, f.get("domain",""))
        classified.append({**f, "failure_type": ftype, "specialist": sid})

    # Deploy real domain experts
    winston   = _run_winston(classified)
    isabella  = _run_isabella(classified)
    alexander = _run_alexander(classified)
    katerina  = _run_katerina(classified)
    penny     = _run_penny(classified)
    shield    = _run_shield(classified)
    results   = [winston, isabella, alexander, katerina, penny, shield]

    coordination = _bond_coordinate(classified, results)

    # Escalate to External Bond if needed
    if coordination["escalate_to_external"]:
        try:
            bond_courier.send_directive(
                content=coordination["directive"],
                priority=coordination["priority"],
                metadata={"source": "technical_team", "failure_count": len(classified)},
            )
        except Exception as exc:
            log_agent(_NAME, "escalate_external", result=f"failed: {exc}")

    mem.remember(
        _NAME, "last_remediation",
        {
            "timestamp":      datetime.now(timezone.utc).isoformat(),
            "failure_count":  len(classified),
            "domains":        coordination["domains_affected"],
            "escalated":      coordination["escalate_to_external"],
        },
        confidence=0.85,
        summary=f"Remediation run: {len(classified)} failures, escalated={coordination['escalate_to_external']}",
    )

    log_agent(
        _NAME, "remediate",
        payload={"failure_count": len(classified)},
        result=(
            f"domains={len(coordination['domains_affected'])} "
            f"escalated={coordination['escalate_to_external']}"
        ),
    )

    return {
        "agent":         _NAME,
        "action":        "remediate",
        "failure_count": len(classified),
        "failures":      classified,
        "specialists": {
            "winston_carmichael": winston,
            "isabella_cruz":      isabella,
            "alexander_wright":   alexander,
            "katerina_rostova":   katerina,
            "penny":              penny,
            "shield":             shield,
        },
        "coordination": coordination,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
    }
