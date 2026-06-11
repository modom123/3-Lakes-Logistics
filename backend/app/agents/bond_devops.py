"""Bond Office — DevOps / Q Branch.

Autonomous database-migration + Render-redeploy operative for the James Bond
office. Eliminates the two recurring manual chores in this system: trips to the
Supabase SQL editor and clicks in the Render dashboard.

What it does
------------
  * Discovers repo migration files (sql/*.sql and backend/sql/*.sql).
  * Applies the ones not yet in the schema_migrations_bond ledger, in order,
    via the Supabase exec_sql() RPC (idempotent migrations — safe to re-run).
  * Triggers a Render redeploy.
  * Writes a full report to org memory + the Bond channel, and escalates to
    Mark Odom + CC Gulley if anything fails.

Actions (payload['action']):
  sync       apply pending migrations, then redeploy, then report   (default)
  migrate    apply pending migrations only
  redeploy   trigger a Render redeploy only
  status     return ledger state + the last deploy-log entry
  baseline   mark every current repo migration as applied WITHOUT running it
             (used once to align the ledger with an already-live database)

Safety
------
  * The API surface never accepts raw SQL — only repo-tracked files are run.
  * SQL is applied over a direct Postgres connection (DATABASE_URL /
    SUPABASE_DB_URL secret) via psycopg2 — there is NO persistent arbitrary-SQL
    RPC left on the database.
  * Bootstrap dependency: backend/sql/023_bond_devops.sql (the ledger +
    deploy-log tables) must exist once. After that, this module is self-serve.
  * Requires DATABASE_URL (or SUPABASE_DB_URL) to be set; without it, migrate
    actions return a clear "credential not configured" message instead of guessing.

API surface:
  POST /api/agents/bond_devops/run   {action, redeploy?}
  POST /api/bond/deploy              (sync)   — Eagle Eye Bond Office tab
  POST /api/bond/migrate
  POST /api/bond/redeploy
  GET  /api/bond/deploy-status
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from . import memory as mem

_NAME = "bond_devops"

# Repo root = .../3-Lakes-Logistics ; this file is backend/app/agents/bond_devops.py
_REPO_ROOT = Path(__file__).resolve().parents[3]
_MIGRATION_DIRS = [
    _REPO_ROOT / "backend" / "sql",
    _REPO_ROOT / "sql",
]
_LEDGER = "schema_migrations_bond"


# ── Discovery ─────────────────────────────────────────────────────────────────

def _discover() -> list[dict[str, str]]:
    """Return repo migrations as [{key, path, sql, checksum}], ordered by name."""
    found: list[dict[str, str]] = []
    for d in _MIGRATION_DIRS:
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.sql")):
            try:
                sql = path.read_text(encoding="utf-8")
            except Exception:
                continue
            key = str(path.relative_to(_REPO_ROOT)).replace("\\", "/")
            found.append({
                "key":      key,
                "path":     str(path),
                "sql":      sql,
                "checksum": hashlib.sha256(sql.encode("utf-8")).hexdigest()[:16],
            })
    # Order by file basename (001_, 002_, ...) so dependencies apply first,
    # then by full key to keep both dirs deterministic.
    found.sort(key=lambda m: (Path(m["key"]).name, m["key"]))
    return found


def _ledger_state() -> dict[str, str]:
    """Return {filename: checksum} of migrations already recorded as applied."""
    try:
        rows = (
            get_supabase().table(_LEDGER)
            .select("filename,checksum,status")
            .execute().data or []
        )
        return {r["filename"]: r.get("checksum", "") for r in rows if r.get("status") == "applied"}
    except Exception:
        return {}


# ── SQL transport (direct Postgres via psycopg2) ──────────────────────────────

_NO_DB_URL = ("DATABASE_URL not configured — set DATABASE_URL (or SUPABASE_DB_URL) "
              "in Render env / GitHub secrets: Supabase → Project Settings → "
              "Database → Connection string (Session pooler / URI)")


def _db_url() -> str:
    s = get_settings()
    return (s.database_url or s.supabase_db_url or "").strip()


def _run_sql(sql_statement: str) -> tuple[bool, str]:
    """Apply a migration over a direct Postgres connection. (ok, message).

    Each file runs in its own transaction so one bad file doesn't poison the next.
    """
    url = _db_url()
    if not url:
        return False, _NO_DB_URL
    try:
        import psycopg2
    except Exception:
        return False, "psycopg2 not installed (add psycopg2-binary to requirements.txt)"
    try:
        conn = psycopg2.connect(url, connect_timeout=15, sslmode="require")
    except Exception as exc:
        return False, f"db connect failed: {str(exc)[:160]}"
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(sql_statement)
        conn.commit()
        return True, "executed via psycopg2"
    except Exception as exc:
        conn.rollback()
        return False, f"{str(exc)[:200]}"
    finally:
        conn.close()


def _record(filename: str, checksum: str, status: str, error: str = "") -> None:
    try:
        get_supabase().table(_LEDGER).upsert({
            "filename":   filename,
            "checksum":   checksum,
            "status":     status,
            "error":      error[:500] or None,
            "applied_by": _NAME,
            "applied_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as exc:
        log_agent(_NAME, "ledger_write_failed", error=str(exc)[:200])


# ── Core operations ───────────────────────────────────────────────────────────

def apply_migrations(mark_only: bool = False) -> dict[str, Any]:
    """Apply every repo migration not yet in the ledger.

    mark_only=True records them as applied WITHOUT executing (baseline mode).
    """
    applied: list[dict] = []
    failed: list[dict] = []
    skipped = 0

    state = _ledger_state()
    for m in _discover():
        if state.get(m["key"]) == m["checksum"]:
            skipped += 1
            continue

        if mark_only:
            _record(m["key"], m["checksum"], "applied")
            applied.append({"file": m["key"], "note": "baselined (not executed)"})
            continue

        ok, msg = _run_sql(m["sql"])
        if ok:
            _record(m["key"], m["checksum"], "applied")
            applied.append({"file": m["key"], "detail": msg})
        else:
            _record(m["key"], m["checksum"], "failed", msg)
            failed.append({"file": m["key"], "error": msg})
            # Hard stop only if the transport itself is unavailable.
            if msg == _NO_DB_URL or "db connect failed" in msg or "psycopg2 not installed" in msg:
                break

    return {
        "applied":      applied,
        "failed":       failed,
        "skipped":      skipped,
        "applied_count": len(applied),
        "failed_count":  len(failed),
    }


def redeploy() -> dict[str, Any]:
    """Trigger a Render redeploy of the API service."""
    s = get_settings()
    if not s.render_api_key:
        return {
            "triggered": False,
            "reason": "RENDER_API_KEY not set — add it in Render env vars, "
                      "or run the bond-deploy GitHub workflow which holds it as a secret.",
        }
    try:
        from .technical_team import _trigger_render_deploy
        ok, msg = _trigger_render_deploy(s.render_api_key)
        return {"triggered": ok, "detail": msg} if ok else {"triggered": False, "reason": msg}
    except Exception as exc:
        return {"triggered": False, "reason": str(exc)[:200]}


def _escalate(summary: str, detail: str) -> None:
    """Route a deploy failure to Outside Bond's escalation path."""
    try:
        from . import outside_bond as _ob
        _ob._escalate_to_command("render_env", {"detail": detail}, summary, None)
    except Exception:
        pass


def _log_deploy(action: str, migrate: dict, deploy: dict | None, ok: bool, summary: str) -> None:
    try:
        get_supabase().table("bond_deploy_log").insert({
            "action":   action,
            "applied":  migrate.get("applied", []),
            "failed":   migrate.get("failed", []),
            "redeploy": deploy,
            "ok":       ok,
            "summary":  summary,
        }).execute()
    except Exception:
        pass


# ── Entry point ───────────────────────────────────────────────────────────────

def run(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action", "sync")).lower()
    do_redeploy = bool(payload.get("redeploy", True))

    if action == "status":
        try:
            ledger = get_supabase().table(_LEDGER).select("*").order("applied_at", desc=True).execute().data or []
        except Exception as exc:
            ledger = [{"error": str(exc)[:200]}]
        try:
            last = (get_supabase().table("bond_deploy_log")
                    .select("*").order("created_at", desc=True).limit(1).execute().data or [])
        except Exception:
            last = []
        pending = [m["key"] for m in _discover() if _ledger_state().get(m["key"]) != m["checksum"]]
        return {"agent": _NAME, "action": "status", "ledger_count": len(ledger),
                "pending": pending, "pending_count": len(pending),
                "last_deploy": last[0] if last else None}

    if action == "baseline":
        migrate = apply_migrations(mark_only=True)
        _log_deploy("baseline", migrate, None, True, f"baselined {migrate['applied_count']} migrations")
        return {"agent": _NAME, "action": "baseline", **migrate}

    if action == "redeploy":
        deploy = redeploy()
        ok = bool(deploy.get("triggered"))
        _log_deploy("redeploy", {"applied": [], "failed": []}, deploy, ok,
                    deploy.get("detail") or deploy.get("reason", ""))
        if not ok:
            _escalate("Bond redeploy failed", deploy.get("reason", ""))
        return {"agent": _NAME, "action": "redeploy", "redeploy": deploy}

    # ── sync / migrate ────────────────────────────────────────────────────────
    migrate = apply_migrations()
    deploy: dict | None = None
    if action == "sync" and do_redeploy and not migrate["failed"]:
        deploy = redeploy()
    elif action == "sync" and migrate["failed"]:
        deploy = {"triggered": False, "reason": "skipped — migrations failed; not redeploying a broken schema"}

    ok = not migrate["failed"] and (deploy is None or deploy.get("triggered", True))
    summary = (
        f"Bond DevOps {action}: applied {migrate['applied_count']}, "
        f"failed {migrate['failed_count']}, skipped {migrate['skipped']}"
        + (f"; redeploy={'ok' if deploy and deploy.get('triggered') else 'no'}" if deploy else "")
    )

    _log_deploy(action, migrate, deploy, ok, summary)
    mem.remember(
        _NAME, "last_deploy",
        {"action": action, "migrate": migrate, "redeploy": deploy,
         "ok": ok, "timestamp": datetime.now(timezone.utc).isoformat()},
        confidence=0.95, summary=summary,
    )

    # Report into the Bond channel so it surfaces in the office thread.
    try:
        from . import bond_courier
        bond_courier.send_directive(
            f"[Bond DevOps] {summary}", priority="high" if not ok else "normal",
            metadata={"applied": migrate["applied"], "failed": migrate["failed"]},
        )
    except Exception:
        pass

    if migrate["failed"]:
        _escalate("Bond DevOps migration failure",
                  "; ".join(f"{f['file']}: {f['error']}" for f in migrate["failed"])[:400])

    log_agent(_NAME, action, result=summary)
    return {"agent": _NAME, "action": action, "ok": ok, "summary": summary,
            **migrate, "redeploy": deploy}
