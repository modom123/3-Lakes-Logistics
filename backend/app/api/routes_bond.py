"""Bond Office API — bidirectional channel between IEBC Internal
James Bond and the External James Bond on Daytona.

Internal endpoints (bearer auth) — called by Eagle Eye Bond Office tab:
  GET  /bond/thread              full conversation thread
  POST /bond/directive           IEBC sends directive to External Bond
  GET  /bond/status              channel health + message counts
  PATCH /bond/message/{id}       mark a message actioned

External endpoints (X-Bond-Key auth) — called by External Bond on Daytona:
  GET  /bond/inbox               poll for pending IEBC directives
  POST /bond/report              post report / feedback / suggestion back

Set BOND_API_KEY in Render environment variables. External Bond must pass the same
value in the X-Bond-Key request header.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel

from ..agents import bond_courier
from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from .deps import require_bearer


def _require_bond_key(x_bond_key: str | None = Header(default=None)) -> None:
    if not x_bond_key:
        raise HTTPException(401, "X-Bond-Key header required")
    expected = get_settings().bond_api_key
    if not expected or x_bond_key != expected:
        raise HTTPException(403, "Invalid Bond API key")


class DirectiveIn(BaseModel):
    content: str
    priority: str = "normal"
    metadata: dict | None = None


class ReportIn(BaseModel):
    content: str
    message_type: str = "report"
    priority: str = "normal"
    daytona_id: str | None = None
    metadata: dict | None = None


class StatusPatch(BaseModel):
    status: str


_internal = APIRouter(dependencies=[Depends(require_bearer)])


@_internal.get("/thread")
def get_thread(limit: int = 50, direction: str = "all") -> dict:
    msgs = bond_courier.thread(limit=limit, direction=direction)
    return {"messages": msgs, "count": len(msgs)}


@_internal.post("/directive")
def send_directive(body: DirectiveIn, background_tasks: BackgroundTasks) -> dict:
    result = bond_courier.send_directive(body.content, body.priority, body.metadata)
    directive_id = (result.get("message") or {}).get("id", "")
    background_tasks.add_task(_auto_remediate, body.content, directive_id)
    return result


def _auto_remediate(directive_content: str, directive_id: str) -> None:
    """Read the directive, run Outside Bond on each issue, post resolution to channel
    and write a completion todo to Mark Odom's office state."""
    from ..agents import outside_bond, memory as mem

    sb = get_supabase()

    # ── 1. Pull Jamie Park's latest platform_health report ───────────────────
    jamie_row = (
        sb.table("agent_memory")
        .select("value")
        .eq("agent", "jamie_park")
        .eq("key", "platform_health")
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
        .data or []
    )
    report = (jamie_row[0].get("value") or {}) if jamie_row else {}

    api_down      = report.get("api_down") or []
    missing_vars  = (report.get("env_coverage") or {}).get("missing_vars") or []
    overall       = report.get("overall_status", "unknown")
    criticals     = report.get("critical_count", 0)

    fixes_applied: list[str] = []
    fixes_failed:  list[str] = []

    # ── 2. Run Outside Bond on each detected issue ────────────────────────────
    for svc in api_down:
        svc_name = svc.get("service") if isinstance(svc, dict) else str(svc)
        error_detail = f"Service {svc_name} is down/unreachable (Jamie Park platform health report)"
        try:
            res = outside_bond.run({
                "task":         "auto",
                "phase":        "bond_directive",
                "error_details": error_detail,
                "context":      {"service": svc_name},
            })
            if res.get("automated"):
                fixes_applied.append(f"{svc_name}: {res.get('action','fixed')}")
            else:
                fixes_failed.append(f"{svc_name}: {res.get('reason','could not automate')}")
        except Exception as exc:
            fixes_failed.append(f"{svc_name}: exception — {str(exc)[:120]}")

    for mv in missing_vars:
        var_name = mv.get("var") if isinstance(mv, dict) else str(mv)
        try:
            res = outside_bond.run({
                "task":         "render_env",
                "phase":        "bond_directive",
                "error_details": f"Missing environment variable: {var_name}",
                "context":      {"key": var_name},
            })
            if res.get("automated"):
                fixes_applied.append(f"env/{var_name}: {res.get('action','configured')}")
            else:
                fixes_failed.append(f"env/{var_name}: {res.get('reason','needs manual set')}")
        except Exception as exc:
            fixes_failed.append(f"env/{var_name}: exception — {str(exc)[:120]}")

    # If no specific issues extracted, run a general api_probe + tech audit
    if not api_down and not missing_vars:
        try:
            probe = outside_bond.run({"task": "api_probe", "phase": "bond_directive", "context": {}})
            if probe.get("automated"):
                fixes_applied.append(f"api_probe: {probe.get('action','health check complete')}")
        except Exception:
            pass

    # ── 3. Post resolution report back to bond_channel ───────────────────────
    total   = len(fixes_applied) + len(fixes_failed)
    success = len(fixes_applied)
    ts      = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if fixes_applied:
        status_line = f"✅ {success}/{total} issue(s) remediated automatically."
    elif total == 0:
        status_line = "🔍 No specific API/env issues found in Jamie Park's report. Platform status: " + overall.upper()
    else:
        status_line = f"⚠ {success}/{total} fixes applied — {len(fixes_failed)} require manual action."

    report_lines = [
        f"BOND RESOLUTION REPORT — {ts}",
        f"Directive ref: {directive_id or 'N/A'}",
        "",
        f"Platform status (Jamie Park): {overall.upper()} | Criticals: {criticals}",
        "",
        status_line,
    ]
    if fixes_applied:
        report_lines += ["", "AUTOMATED FIXES APPLIED:"] + [f"  ✓ {f}" for f in fixes_applied]
    if fixes_failed:
        report_lines += ["", "REQUIRES MANUAL ACTION:"] + [f"  ✗ {f}" for f in fixes_failed]
    report_lines += ["", "Bond signing off. Issues resolved or escalated per protocol."]

    report_content = "\n".join(report_lines)

    try:
        sb.table("bond_channel").insert({
            "direction":    "external_to_internal",
            "from_label":   "James Bond — IEBC (Auto-Remediation)",
            "message_type": "report",
            "content":      report_content,
            "priority":     "critical" if fixes_failed else "normal",
            "status":       "pending",
            "metadata":     {
                "directive_id":    directive_id,
                "fixes_applied":   fixes_applied,
                "fixes_failed":    fixes_failed,
                "auto_remediated": True,
            },
        }).execute()
    except Exception as exc:
        log_agent("bond_auto_remediate", "report_post_failed", result=str(exc)[:200])

    # ── 4. Write resolution todo to Mark Odom's office state ─────────────────
    try:
        existing_row = (
            sb.table("office_state")
            .select("value")
            .eq("key", "mo_todos")
            .limit(1)
            .execute()
            .data or []
        )
        existing = existing_row[0].get("value", []) if existing_row else []
        if not isinstance(existing, list):
            existing = []

        resolution_task = {
            "id":      f"bond_resolution_{int(datetime.now(timezone.utc).timestamp())}",
            "title":   f"🕵️ Bond Report: {status_line[:80]}",
            "desc":    report_content[:400],
            "due":     "",
            "pri":     "high" if fixes_failed else "med",
            "cat":     "operations",
            "done":    False,
            "created": datetime.now(timezone.utc).isoformat(),
            "_from_bond": True,
        }

        # Replace any prior bond dispatched placeholder
        updated = [t for t in existing if not str(t.get("id", "")).startswith("bond_escalation_")]
        updated = [resolution_task] + updated

        sb.table("office_state").upsert(
            {"key": "mo_todos", "value": updated},
            on_conflict="key"
        ).execute()
    except Exception as exc:
        log_agent("bond_auto_remediate", "todo_write_failed", result=str(exc)[:200])

    log_agent(
        "bond_auto_remediate", "complete",
        payload={"directive_id": directive_id, "issues_found": total},
        result=f"applied={success} failed={len(fixes_failed)}",
    )


@_internal.get("/status")
def channel_status() -> dict:
    try:
        return bond_courier.run({"action": "status"})
    except Exception as exc:
        raise HTTPException(500, f"bond channel error: {exc}")


@_internal.get("/intel-snapshot")
def intel_snapshot() -> dict:
    """Internal (bearer) mirror of /bond/api-snapshot — for the Sit Room KPI strip."""
    from datetime import datetime, timedelta, timezone

    sb  = get_supabase()
    now = datetime.now(timezone.utc)
    thirty_min_ago = (now - timedelta(minutes=30)).isoformat()
    one_hour_ago   = (now - timedelta(hours=1)).isoformat()

    def _count(table: str, filters: list[tuple] | None = None) -> int:
        q = sb.table(table).select("id", count="exact").limit(1)
        for col, val in (filters or []):
            q = q.eq(col, val)
        try:
            return q.execute().count or 0
        except Exception:
            return -1

    trucks_live = -1
    try:
        trucks_live = sb.table("truck_telemetry").select("truck_id", count="exact") \
            .gte("ts", thirty_min_ago).execute().count or 0
    except Exception:
        pass

    violations = -1
    try:
        hos_rows = sb.table("driver_hos_status").select("violation_flags") \
            .gte("ts", one_hour_ago).execute().data or []
        violations = sum(1 for r in hos_rows if r.get("violation_flags"))
    except Exception:
        pass

    loads_active = -1
    try:
        all_loads = sb.table("loads").select("status").execute().data or []
        loads_active = sum(1 for r in all_loads if r.get("status") in
                          ("dispatched", "en_route", "at_pickup", "in_transit"))
    except Exception:
        pass

    pending_directives = -1
    try:
        pending_directives = sb.table("bond_channel").select("id", count="exact") \
            .eq("direction", "internal_to_external").eq("status", "pending") \
            .execute().count or 0
    except Exception:
        pass

    return {
        "snapshot_ts": now.isoformat(),
        "trucks_live_30min":        trucks_live,
        "loads_active":             loads_active,
        "hos_violations_last_hour": violations,
        "total_trucks":             _count("fleet_assets"),
        "total_carriers":           _count("active_carriers"),
        "trucks_on_load":           _count("fleet_assets", [("status", "on_load")]),
        "bond_pending_directives":  pending_directives,
    }


class DeployIn(BaseModel):
    redeploy: bool = True


@_internal.post("/deploy")
def bond_deploy(body: DeployIn | None = None) -> dict:
    """Bond Office one-click deploy: apply pending Supabase migrations, then
    trigger a Render redeploy, then report. Replaces manual SQL-editor +
    dashboard trips."""
    from ..agents import bond_devops
    return bond_devops.run({"action": "sync", "redeploy": (body.redeploy if body else True)})


@_internal.post("/migrate")
def bond_migrate() -> dict:
    """Apply pending Supabase SQL migrations only (no redeploy)."""
    from ..agents import bond_devops
    return bond_devops.run({"action": "migrate"})


@_internal.post("/redeploy")
def bond_redeploy() -> dict:
    """Trigger a Render redeploy only."""
    from ..agents import bond_devops
    return bond_devops.run({"action": "redeploy"})


@_internal.get("/deploy-status")
def bond_deploy_status() -> dict:
    """Pending migrations + last deploy-log entry for the Bond Office tab."""
    from ..agents import bond_devops
    return bond_devops.run({"action": "status"})


@_internal.patch("/message/{msg_id}")
def update_message_status(msg_id: str, body: StatusPatch) -> dict:
    sb = get_supabase()
    result = (
        sb.table("bond_channel")
        .update({"status": body.status})
        .eq("id", msg_id)
        .execute()
    )
    return {"updated": len(result.data or [])}


_external = APIRouter(dependencies=[Depends(_require_bond_key)])


@_external.get("/api-snapshot")
def api_snapshot() -> dict:
    """Full system intelligence snapshot for External Bond.

    External Bond calls this (X-Bond-Key auth) to get live system state
    so it can include real data in its reports and audits.
    """
    sb = get_supabase()
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    one_hour_ago = (now - timedelta(hours=1)).isoformat()
    thirty_min_ago = (now - timedelta(minutes=30)).isoformat()

    def _count(table: str, filters: list[tuple] | None = None) -> int:
        q = sb.table(table).select("id", count="exact").limit(1)
        for col, val in (filters or []):
            q = q.eq(col, val)
        try:
            r = q.execute()
            return r.count or 0
        except Exception:
            return -1

    # Carriers
    total_carriers = _count("active_carriers")

    # Fleet
    total_trucks = _count("fleet_assets")
    on_load       = _count("fleet_assets", [("status", "on_load")])
    available     = _count("fleet_assets", [("status", "available")])
    out_of_svc    = _count("fleet_assets", [("status", "out_of_service")])

    # Telemetry — pings in last 30 min (trucks that are live)
    try:
        tel_live = sb.table("truck_telemetry").select("truck_id", count="exact") \
            .gte("ts", thirty_min_ago).execute().count or 0
    except Exception:
        tel_live = -1

    # Loads
    try:
        loads_res = sb.table("loads").select("status", count="exact").execute()
        loads_all = loads_res.count or 0
        loads_data = loads_res.data or []
        loads_active = sum(1 for r in loads_data if r.get("status") in ("dispatched", "en_route", "at_pickup", "in_transit"))
    except Exception:
        loads_all = -1
        loads_active = -1

    # HOS violations
    try:
        hos_rows = sb.table("driver_hos_status").select("violation_flags,ts") \
            .gte("ts", one_hour_ago).execute().data or []
        violations = sum(1 for r in hos_rows if r.get("violation_flags"))
    except Exception:
        violations = -1

    # Unread messages from IEBC waiting for External Bond
    try:
        pending_directives = sb.table("bond_channel").select("id", count="exact") \
            .eq("direction", "internal_to_external").eq("status", "pending") \
            .execute().count or 0
    except Exception:
        pending_directives = -1

    return {
        "snapshot_ts": now.isoformat(),
        "carriers": {
            "total": total_carriers,
        },
        "fleet": {
            "total_trucks": total_trucks,
            "on_load":      on_load,
            "available":    available,
            "out_of_service": out_of_svc,
        },
        "telemetry": {
            "trucks_live_30min": tel_live,
        },
        "loads": {
            "total":  loads_all,
            "active": loads_active,
        },
        "hos": {
            "violations_last_hour": violations,
        },
        "bond_channel": {
            "pending_directives": pending_directives,
        },
        "api_base": get_settings().site_url,
        "endpoints": {
            "inbox":        "GET  /api/bond/inbox               — pull pending directives",
            "report":       "POST /api/bond/report              — post report back",
            "api_snapshot": "GET  /api/bond/api-snapshot        — this endpoint",
            "health":       "GET  /health/ping                  — liveness check",
        },
    }


@_external.get("/inbox")
def external_inbox(limit: int = 10) -> dict:
    sb = get_supabase()
    rows = (
        sb.table("bond_channel")
        .select("*")
        .eq("direction", "internal_to_external")
        .eq("status", "pending")
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
        .data or []
    )
    if rows:
        ids = [r["id"] for r in rows]
        sb.table("bond_channel").update({"status": "delivered"}).in_("id", ids).execute()
    return {"directives": rows, "count": len(rows)}


@_external.post("/report")
def external_report(body: ReportIn) -> dict:
    valid_types = {"report", "feedback", "suggestion", "acknowledgment"}
    if body.message_type not in valid_types:
        raise HTTPException(400, f"message_type must be one of {valid_types}")
    sb = get_supabase()
    row = {
        "direction":    "external_to_internal",
        "from_label":   "Bond External (Daytona)",
        "message_type": body.message_type,
        "content":      body.content,
        "priority":     body.priority,
        "status":       "pending",
        "metadata":     {
            **(body.metadata or {}),
            "daytona_id": body.daytona_id or get_settings().daytona_sandbox_id,
        },
    }
    result = sb.table("bond_channel").insert(row).execute()
    inserted = result.data[0] if result.data else {}
    return {"status": "received", "id": inserted.get("id")}


router = APIRouter()
router.include_router(_internal)
router.include_router(_external)
