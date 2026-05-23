"""IEBC Technical Team — automated remediation system.

Three specialists analyze test-suite failures and produce fix artifacts:
  winston_cole     → diagnostic scripts, code-level fixes, endpoint debugging
  isabella_nash    → schema analysis, SQL migrations, database fixes
  alexander_kane   → API integration, environment config, credential setup

Bond coordinates the team and can escalate to External Bond via bond_courier.

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
from . import bond_courier
from . import memory as mem

_NAME = "technical_team"
_DAYTONA_ID = "2a50d3c2-f813-49c0-8dec-f9248581c5c6"


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
    "winston_cole": {
        "name":    "Winston Cole",
        "role":    "Lead Test Engineer",
        "handles": {"code_bug", "endpoint_error", "timeout", "response_shape"},
    },
    "isabella_nash": {
        "name":    "Isabella Nash",
        "role":    "Systems Analyst",
        "handles": {"schema_error", "missing_table", "data_shape", "database"},
    },
    "alexander_kane": {
        "name":    "Alexander Kane",
        "role":    "Integration Engineer",
        "handles": {"api_key", "auth", "config", "connection", "env_var"},
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
    if any(k in txt for k in ("401", "403", "unauthorized", "auth guard", "forbidden")):
        return "auth"
    if any(k in txt for k in ("422", "env", "environment", "render env", "not configured")):
        return "config"
    if any(k in txt for k in ("connection", "connect", "unreachable", "timeout")):
        return "connection"
    if any(k in txt for k in ("500", "internal server", "traceback", "exception", "error")):
        return "code_bug"
    if any(k in txt for k in ("shape", "count", "items", "expected", "missing key")):
        return "response_shape"
    return "code_bug"


def _assign(failure_type: str) -> str:
    for sid, info in SPECIALISTS.items():
        if failure_type in info["handles"]:
            return sid
    return "winston_cole"


# ── Winston Cole — diagnostic scripts & code fixes ────────────────────────────

def _winston_analyze(failures: list[dict]) -> dict[str, Any]:
    mine = [f for f in failures if f.get("specialist") == "winston_cole"]
    if not mine:
        return {"specialist": "winston_cole", "status": "no_assignment", "artifacts": []}

    # Build per-domain diagnostic checks
    check_blocks: list[str] = []
    for f in mine:
        domain = f["domain"]
        error  = f.get("error", "")
        endpoint_map = {
            "Health":        [
                ('GET',  '/api/health/ping',    None),
                ('GET',  '/api/health/full',    None),
            ],
            "Carriers":      [('GET', '/api/carriers/', None)],
            "Fleet":         [('GET', '/api/fleet/',    None)],
            "Leads":         [('GET', '/api/leads/',    None)],
            "Telemetry":     [
                ('GET',  '/api/telemetry/latest', None),
                ('POST', '/api/telemetry/ping',   {
                    "carrier_id": "test-001", "truck_id": "truck-001",
                    "eld_provider": "samsara", "lat": 34.05, "lng": -118.24,
                    "speed_mph": 55.0, "heading_deg": 270.0,
                }),
            ],
            "Dashboard":     [('GET', '/api/dashboard/kpis', None)],
            "Bond Channel":  [
                ('GET', '/api/bond/thread', None),
                ('GET', '/api/bond/status', None),
            ],
        }
        for method, path, body in endpoint_map.get(domain, []):
            if method == "GET":
                check_blocks.append(
                    f"r = requests.get(BASE + '{path}', headers=H)\n"
                    f"print(f'{domain} {path}: {{r.status_code}} {{r.text[:300]}}')"
                )
            else:
                check_blocks.append(
                    f"r = requests.post(BASE + '{path}', headers=H, json={body!r})\n"
                    f"print(f'{domain} {path}: {{r.status_code}} {{r.text[:300]}}')"
                )

    script = (
        '"""Winston Cole — IEBC Diagnostic Script.\n'
        'Run: python winston_diagnostic.py\n'
        'Replace TOKEN with your Eagle Eye bearer token.\n"""\n'
        "import requests\n\n"
        "BASE = 'https://three-lakes-logistics-api.onrender.com'\n"
        "H = {'Content-Type': 'application/json', 'Authorization': 'Bearer <YOUR_TOKEN>'}\n\n"
        + "\n\n".join(check_blocks)
        + "\n\nprint('\\n=== Winston diagnostic complete ===')\n"
    )

    diagnoses = []
    for f in mine:
        error = f.get("error", "")
        domain = f["domain"]
        if "500" in error or "server error" in error.lower():
            cause = f"Backend exception in {domain} — check Render logs for traceback"
            steps = [
                "Open Render dashboard → your service → Logs",
                "Search for 'ERROR' or 'Traceback' near the test run time",
                "Fix the failing import or route handler",
                "Redeploy and re-run the test suite",
            ]
        elif "shape" in error.lower() or "count" in error.lower():
            cause = f"{domain} returned wrong JSON shape — router may be returning raw list instead of {{count, items}}"
            steps = [
                f"Open backend/app/api/routes_{domain.lower()}.py",
                "Verify the list endpoint wraps results in {count: N, items: [...]}",
                "Fix and redeploy",
            ]
        else:
            cause = f"Unexpected {domain} response — run diagnostic script to trace"
            steps = [
                "Run winston_diagnostic.py and capture output",
                "Compare status code and body against expected contract",
                "Fix code or environment config accordingly",
            ]
        diagnoses.append({"domain": domain, "test": f["test_name"], "cause": cause, "steps": steps})

    # LLM enhancement: ask Claude to write actual code fixes
    llm_fix = _llm(
        system=(
            "You are Winston Cole, Lead Test Engineer for IEBC. "
            "You receive failing API test details and write precise, runnable Python code fixes or patches. "
            "Be concise. Return only code and brief comments — no prose."
        ),
        user=(
            f"These API tests are failing:\n{json.dumps(mine, indent=2)}\n\n"
            "For each failure: identify the most likely root cause, then write the minimal Python code change "
            "or shell command that fixes it. Format as:\n"
            "# [Domain] [Test]\n# Cause: ...\n<code fix or command>\n\n"
        ),
        model="claude-haiku-4-5-20251001",
        max_tokens=700,
    )
    if llm_fix:
        artifacts.append({
            "type":     "python",
            "title":    "Winston's AI-Generated Code Fix",
            "filename": "winston_ai_fix.py",
            "content":  llm_fix,
        })

    return {
        "specialist":       "winston_cole",
        "name":             "Winston Cole",
        "role":             "Lead Test Engineer",
        "assigned_count":   len(mine),
        "status":           "complete",
        "artifacts": [
            {
                "type":     "python",
                "title":    "Diagnostic Runner (run in terminal)",
                "filename": "winston_diagnostic.py",
                "content":  script,
            },
            {
                "type":     "diagnosis",
                "title":    "Root Cause Analysis",
                "content":  diagnoses,
            },
        ],
    }


# ── Isabella Nash — schema analysis & SQL migrations ─────────────────────────

def _isabella_analyze(failures: list[dict]) -> dict[str, Any]:
    mine = [f for f in failures if f.get("specialist") == "isabella_nash"]
    if not mine:
        return {"specialist": "isabella_nash", "status": "no_assignment", "artifacts": []}

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    blocks: list[str] = [
        f"-- Isabella Nash — Schema Verification & Fix Script",
        f"-- Generated: {now}",
        f"-- Run in Supabase SQL Editor (Settings → SQL Editor)",
        "",
    ]

    domains = {f["domain"] for f in mine}

    if "Bond Channel" in domains or any("bond" in f.get("error","").lower() for f in mine):
        blocks += [
            "-- ── Bond Channel table ──────────────────────────────────────────",
            "SELECT EXISTS (",
            "  SELECT 1 FROM information_schema.tables",
            "  WHERE table_schema = 'public' AND table_name = 'bond_channel'",
            ") AS bond_channel_exists;",
            "",
            "-- Create if missing:",
            "CREATE TABLE IF NOT EXISTS bond_channel (",
            "  id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,",
            "  direction    TEXT        NOT NULL CHECK (direction IN ('internal_to_external','external_to_internal')),",
            "  from_label   TEXT        NOT NULL,",
            "  message_type TEXT        NOT NULL DEFAULT 'directive'",
            "               CHECK (message_type IN ('directive','report','feedback','suggestion','acknowledgment')),",
            "  content      TEXT        NOT NULL,",
            "  priority     TEXT        NOT NULL DEFAULT 'normal'",
            "               CHECK (priority IN ('critical','high','normal','low')),",
            "  status       TEXT        NOT NULL DEFAULT 'pending'",
            "               CHECK (status IN ('pending','delivered','read','actioned')),",
            "  metadata     JSONB       DEFAULT '{}',",
            "  created_at   TIMESTAMPTZ DEFAULT now(),",
            "  updated_at   TIMESTAMPTZ DEFAULT now()",
            ");",
            "CREATE INDEX IF NOT EXISTS bond_channel_direction_status",
            "  ON bond_channel (direction, status, created_at);",
            "",
        ]

    for domain in domains:
        if domain == "Health":
            blocks += [
                "-- ── Health / Supabase connectivity ─────────────────────────────",
                "SELECT now() AS supabase_time, current_database() AS db;",
                "SELECT COUNT(*) AS memory_rows FROM agent_memory;",
                "",
            ]
        elif domain == "Leads":
            blocks += [
                "-- ── Leads table ────────────────────────────────────────────────",
                "SELECT column_name, data_type, is_nullable",
                "FROM information_schema.columns WHERE table_name = 'leads'",
                "ORDER BY ordinal_position;",
                "SELECT COUNT(*) AS lead_count FROM leads;",
                "",
            ]
        elif domain == "Carriers":
            blocks += [
                "-- ── Carriers table ─────────────────────────────────────────────",
                "SELECT column_name, data_type FROM information_schema.columns",
                "WHERE table_name = 'carriers' ORDER BY ordinal_position;",
                "SELECT COUNT(*) FROM carriers;",
                "",
            ]
        elif domain == "Fleet":
            blocks += [
                "-- ── Fleet table ────────────────────────────────────────────────",
                "SELECT column_name, data_type FROM information_schema.columns",
                "WHERE table_name IN ('trucks','fleet','loads') ORDER BY table_name, ordinal_position;",
                "",
            ]
        elif domain == "Telemetry":
            blocks += [
                "-- ── Telemetry table ────────────────────────────────────────────",
                "SELECT table_name FROM information_schema.tables",
                "WHERE table_name ILIKE '%telemetry%';",
                "SELECT COUNT(*) FROM telemetry_pings;",
                "",
            ]

    # LLM enhancement: targeted SQL for the exact failures
    llm_sql = _llm(
        system=(
            "You are Isabella Nash, Systems Analyst for IEBC. "
            "You write precise, safe SQL for Supabase (PostgreSQL 15). "
            "Only use CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS, ALTER TABLE ADD COLUMN IF NOT EXISTS. "
            "No destructive statements. Return only SQL with brief comments."
        ),
        user=(
            f"These database-related test failures occurred:\n{json.dumps(mine, indent=2)}\n\n"
            "Write the exact SQL statements needed to fix each failure. "
            "Include a VERIFY SELECT after each fix."
        ),
        model="claude-haiku-4-5-20251001",
        max_tokens=700,
    )
    if llm_sql:
        artifacts.append({
            "type":     "sql",
            "title":    "Isabella's AI-Generated Schema Fix",
            "filename": "isabella_ai_fix.sql",
            "content":  llm_sql,
        })

    return {
        "specialist":     "isabella_nash",
        "name":           "Isabella Nash",
        "role":           "Systems Analyst",
        "assigned_count": len(mine),
        "status":         "complete",
        "artifacts": [
            {
                "type":     "sql",
                "title":    "Schema Verification & Migration (Supabase SQL Editor)",
                "filename": "isabella_schema_fix.sql",
                "content":  "\n".join(blocks),
            },
        ],
    }


# ── Alexander Kane — environment config & API integration ─────────────────────

def _alexander_analyze(failures: list[dict]) -> dict[str, Any]:
    mine = [f for f in failures if f.get("specialist") == "alexander_kane"]
    if not mine:
        return {"specialist": "alexander_kane", "status": "no_assignment", "artifacts": []}

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    domains = {f["domain"] for f in mine}

    env_lines = [
        f"# Alexander Kane — Render Environment Variables",
        f"# Generated: {now}",
        "# ── How to apply ─────────────────────────────────────────────────────",
        "# Render Dashboard → your service → Environment → Add each variable → Save Changes",
        "# Render auto-redeploys after saving.",
        "",
        "# ── Core (required by all domains) ──────────────────────────────────",
        "SUPABASE_URL=https://<project-ref>.supabase.co",
        "SUPABASE_KEY=<service-role-key>   # Settings → API → service_role (NOT anon)",
        "API_TOKEN=<your-eagle-eye-bearer-token>",
        "",
    ]

    if "Bond Channel" in domains or any(
        f.get("failure_type") in ("api_key", "auth", "connection") for f in mine
    ):
        env_lines += [
            "# ── Bond Channel ─────────────────────────────────────────────────",
            "# Generate: python -c \"import secrets; print(secrets.token_hex(32))\"",
            "BOND_API_KEY=<32-byte-hex-secret>",
            "",
            "# ── Daytona sandbox (set on Daytona, not Render) ─────────────────",
            f"# Sandbox ID: {_DAYTONA_ID}",
            "IEBC_API_URL=https://three-lakes-logistics-api.onrender.com",
            "BOND_API_KEY=<same-value-as-above>",
            "",
        ]

    if "Health" in domains:
        env_lines += [
            "# ── Stripe (needed for /api/health/full) ────────────────────────",
            "STRIPE_SECRET_KEY=sk_live_<your-key>",
            "STRIPE_WEBHOOK_SECRET=whsec_<your-secret>",
            "",
        ]

    if "Telemetry" in domains:
        env_lines += [
            "# ── ELD / Telemetry ──────────────────────────────────────────────",
            "ELD_API_KEY=<samsara-or-motive-api-key>",
            "",
        ]

    env_lines += [
        "# ── Verify bond endpoint after setting BOND_API_KEY ─────────────────",
        "# curl -H 'X-Bond-Key: <your-key>'",
        "#      https://three-lakes-logistics-api.onrender.com/api/bond/inbox",
        "# Expected: 200 {messages: [...]}",
    ]

    checklist_items = [
        {
            "area": "Supabase",
            "steps": [
                "Supabase → Project Settings → API → copy service_role secret",
                "Add SUPABASE_URL and SUPABASE_KEY to Render Environment",
                "Run Isabella's SQL script to verify/create tables",
            ],
        },
        {
            "area": "Bond Channel",
            "steps": [
                "Run: python -c \"import secrets; print(secrets.token_hex(32))\"",
                "Add BOND_API_KEY to Render Environment Variables",
                f"Set IEBC_API_URL + BOND_API_KEY on Daytona sandbox ({_DAYTONA_ID})",
                "Test: curl -H 'X-Bond-Key: <key>' <render-url>/api/bond/inbox",
            ],
        },
        {
            "area": "Verify",
            "steps": [
                "After all env vars set → Render auto-redeploys",
                "Wait ~60s for deploy to complete",
                "Go to Eagle Eye → Test Suite → Run All Domains",
                "All 7 domains should show PASS",
            ],
        },
    ]

    # LLM enhancement: precise integration steps for exact failures
    llm_config = _llm(
        system=(
            "You are Alexander Kane, Integration Engineer for IEBC. "
            "You write exact, copy-paste-ready environment variable configs and API setup steps. "
            "Be precise. Include the exact Render dashboard path, exact curl verification commands, "
            "and how to generate any secrets. No filler."
        ),
        user=(
            f"These API/auth/config test failures occurred:\n{json.dumps(mine, indent=2)}\n\n"
            "Write the exact steps to fix each: which env vars to set, how to generate them, "
            "how to set them on Render, and the exact curl command to verify each fix."
        ),
        model="claude-haiku-4-5-20251001",
        max_tokens=700,
    )
    if llm_config:
        artifacts.append({
            "type":     "env",
            "title":    "Alexander's AI-Generated Integration Fix",
            "filename": "alexander_ai_fix.sh",
            "content":  llm_config,
        })

    return {
        "specialist":     "alexander_kane",
        "name":           "Alexander Kane",
        "role":           "Integration Engineer",
        "assigned_count": len(mine),
        "status":         "complete",
        "artifacts": [
            {
                "type":     "env",
                "title":    "Render Environment Variables Template",
                "filename": ".env.render.template",
                "content":  "\n".join(env_lines),
            },
            {
                "type":     "checklist",
                "title":    "Integration Setup Checklist",
                "content":  checklist_items,
            },
        ],
    }


# ── Bond coordination ─────────────────────────────────────────────────────────

def _bond_coordinate(classified: list[dict], results: list[dict]) -> dict[str, Any]:
    domains = sorted({f["domain"] for f in classified})
    active  = [r for r in results if r.get("status") == "complete"]
    priority = "high" if len(classified) >= 3 else "normal"

    lines = [
        "IEBC TECHNICAL TEAM REMEDIATION REPORT",
        f"Coordinator: James Bond, IEBC Consultant",
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
        "  1. Run Isabella's SQL script in Supabase to verify/create tables",
        "  2. Apply Alexander's env vars to Render Environment",
        "  3. Run Winston's diagnostic script to confirm endpoints respond",
        "  4. Re-run Test Suite — all 7 domains should pass",
        "",
        "EXTERNAL BOND DIRECTIVE:",
        f"  Daytona sandbox {_DAYTONA_ID}:",
        "  · Verify IEBC_API_URL points to the Render API",
        "  · Verify BOND_API_KEY matches the Render env var",
        "  · Run: curl $IEBC_API_URL/api/health/ping",
        "  · Report connectivity status back to IEBC Internal",
        "",
        "BOND TO COMMANDER: Isabella's SQL first, then Alexander's env vars, then re-test.",
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
        f"TO:       External Bond · Daytona {_DAYTONA_ID}",
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
        sid   = _assign(ftype)
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
            f"Daytona sandbox: {_DAYTONA_ID}\n\n"
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
                "sandbox_id":      _DAYTONA_ID,
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
            "sandbox_id": _DAYTONA_ID,
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
            sid   = _assign(ftype)
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

    # Classify + assign
    classified = []
    for f in raw:
        ftype    = _classify(f.get("test_name",""), f.get("domain",""), f.get("error",""))
        sid      = _assign(ftype)
        classified.append({**f, "failure_type": ftype, "specialist": sid})

    # Run specialists in parallel (sequential here — no async needed)
    winston   = _winston_analyze(classified)
    isabella  = _isabella_analyze(classified)
    alexander = _alexander_analyze(classified)
    results   = [winston, isabella, alexander]

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
        "agent":       _NAME,
        "action":      "remediate",
        "failure_count": len(classified),
        "failures":    classified,
        "specialists": {
            "winston_cole":   winston,
            "isabella_nash":  isabella,
            "alexander_kane": alexander,
        },
        "coordination": coordination,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
    }
