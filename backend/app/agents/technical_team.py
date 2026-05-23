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

from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from . import bond_courier
from . import memory as mem

_NAME = "technical_team"
_DAYTONA_ID = "2a50d3c2-f813-49c0-8dec-f9248581c5c6"

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

def _build_mission_directive(
    classified: list[dict],
    autofix: dict,
    bond_brief: str,
    iteration: int = 1,
) -> str:
    domains   = sorted({f["domain"] for f in classified})
    remaining = [
        f for f in classified
        if not any(
            fix.get("area", "").lower() in f.get("domain", "").lower()
            for fix in autofix.get("fixed", [])
        )
    ]

    lines = [
        f"╔══════════════════════════════════════════════════════════╗",
        f"║  DUAL-BOND AUTONOMOUS MISSION DIRECTIVE  ·  Iteration {iteration}  ║",
        f"╚══════════════════════════════════════════════════════════╝",
        f"",
        f"FROM:     James Bond · IEBC Internal · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"TO:       External Bond · Daytona {_DAYTONA_ID}",
        f"PRIORITY: {'CRITICAL' if len(remaining) >= 3 else 'HIGH'}",
        f"",
        f"STRATEGIC BRIEF:",
        bond_brief or "System health restoration required.",
        f"",
        f"TEST SUITE STATUS:",
        f"  Total failures : {len(classified)} across {len(domains)} domain(s): {', '.join(domains)}",
        f"  Internal fixes : {len(autofix.get('fixed', []))} applied automatically",
        f"  Still failing  : {len(remaining)} require External Bond action",
        f"",
    ]

    if autofix.get("fixed"):
        lines.append("ALREADY FIXED INTERNALLY:")
        for f in autofix["fixed"]:
            lines.append(f"  ✓ [{f.get('area','?')}] {f.get('action','')}")
        lines.append("")

    if remaining:
        lines.append("FAILURES REQUIRING YOUR ACTION:")
        for i, f in enumerate(remaining, 1):
            lines += [
                f"  {i}. Domain: {f['domain']}  ·  Test: {f['test_name']}",
                f"     Type: {f.get('failure_type','?')}  ·  Error: {f.get('error','')}",
            ]
        lines.append("")

    manual = autofix.get("needs_manual", [])
    if manual:
        lines.append("MANUAL ACTIONS STILL NEEDED (internal team cannot auto-apply):")
        for m in manual:
            lines += [
                f"  • [{m.get('area','?')}] {m.get('action','')}",
                f"    HOW: {m.get('how','')}",
            ]
        lines.append("")

    env = autofix.get("env_status", {})
    missing_env = [k for k, v in env.items() if not v]
    if missing_env:
        lines += [
            "MISSING ENVIRONMENT VARIABLES (detected from Render):",
            *[f"  ✗ {k}" for k in missing_env],
            "",
        ]

    lines += [
        "YOUR MISSION:",
        "  1. For each remaining failure — diagnose from Daytona sandbox",
        "  2. Write the fix: Python code patch / SQL migration / env var value",
        "  3. If code fix: push to modom123/3-lakes-logistics main branch",
        "  4. If SQL fix: provide the exact SQL statement",
        "  5. If env var: provide the exact variable name and instructions to obtain value",
        "  6. Reply to this directive via POST /api/bond/report with:",
        "     { 'fixes_applied': [...], 'sql_run': [...], 'env_vars_needed': [...], 'code_pushed': bool }",
        "",
        "  Verify Render API is reachable: curl https://three-lakes-logistics-api.onrender.com/api/health/ping",
        "",
        "BOND DIRECTIVE TO COMMANDER: External Bond has all context. Stand by for fix report.",
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

    # Phase 3 — compose External Bond directive
    directive = _build_mission_directive(classified, autofix, brief, iteration)

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
