"""Outside Bond — IEBC Field Operative.

When James Bond (the auditor) identifies gaps that require external system
changes, Outside Bond takes over:

  1. Attempts the fix automatically via the relevant external API.
  2. If successful  → logs to org memory, returns success.
  3. If it can't    → creates Tier-2 executive escalations assigned to
                      Mark Odom AND CC Gulley with drill-down instructions.

Automated task types
--------------------
bland_ai_allowlist   Add Render server IP to Bland AI's IP allowlist
render_env           Set / update an env var on the Render service
render_restart       Trigger a clean redeploy of the Render service
api_probe            Health-check a live API endpoint and report status
generic              No automation possible → escalate directly

API surface
-----------
POST /api/agents/outside_bond/run
Payload keys (all optional except task):
  task          str   one of the task types above
  context       dict  task-specific parameters
  phase         str   which test phase triggered this
  error_details str   raw error string from the failing test/step
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from . import memory as mem

_NAME       = "outside_bond"
_BLAND_URL  = "https://api.bland.ai/v1"
_RENDER_URL = "https://api.render.com/v1"
_RENDER_SVC = "three-lakes-logistics-api"


# ── Utilities ─────────────────────────────────────────────────────────────────

def _server_ip() -> str | None:
    """Return the server's outbound IP via ipify."""
    try:
        r = httpx.get("https://api.ipify.org?format=json", timeout=8)
        return r.json().get("ip")
    except Exception:
        return None


def _create_escalation(assigned_to: str, tier: int, event_type: str, desc: str) -> str:
    """Insert directly into executive_escalations table. Returns row id or ''."""
    try:
        result = (
            get_supabase()
            .table("executive_escalations")
            .insert({
                "tier":        tier,
                "event_type":  event_type,
                "description": desc,
                "assigned_to": assigned_to,
                "status":      "open",
            })
            .execute()
        )
        rows = result.data or []
        return rows[0].get("id", "") if rows else ""
    except Exception as exc:
        return f"escalation_error:{exc}"


def _escalate_to_command(task: str, context: dict, reason: str, server_ip: str | None) -> dict:
    """Create Tier-2 escalations for Mark Odom + CC Gulley with exact manual steps."""
    if task == "bland_ai_allowlist":
        ip_str = server_ip or "UNKNOWN — run: curl https://api.ipify.org from Render shell"
        instructions = (
            f"Outside Bond attempted to automate Bland AI IP allowlist but failed: {reason}. "
            f"Manual fix (5 min): "
            f"1) Open https://app.bland.ai → Account Settings → IP Allowlist. "
            f"2) Click 'Add IP' → enter {ip_str} → Save. "
            f"Impact: restores carrier intake, Vance dialer, and 4 nightly test failures."
        )
    elif task == "render_env":
        key = context.get("key", "UNKNOWN_KEY")
        instructions = (
            f"Outside Bond could not set env var automatically: {reason}. "
            f"Manual fix: Render Dashboard → {_RENDER_SVC} → Environment → "
            f"Add variable '{key}' with the value from 1Password / secrets vault."
        )
    elif task == "render_restart":
        instructions = (
            f"Outside Bond could not trigger Render redeploy: {reason}. "
            f"Manual fix: Render Dashboard → {_RENDER_SVC} → Manual Deploy → "
            f"'Deploy latest commit'. Ensure RENDER_API_KEY is set in env for future auto-deploys."
        )
    else:
        instructions = (
            f"Outside Bond could not automate task '{task}': {reason}. "
            f"Context: {json.dumps(context)[:300]}. Manual review required."
        )

    esc_mo = _create_escalation("Mark Odom", 2, "api_down", instructions)
    esc_cc = _create_escalation("CC Gulley",  2, "api_down", instructions)

    mem.remember(
        _NAME, "last_escalation",
        {"task": task, "reason": reason, "server_ip": server_ip,
         "esc_mark_odom": esc_mo, "esc_cc_gulley": esc_cc,
         "timestamp": datetime.now(timezone.utc).isoformat()},
        confidence=0.95,
        summary=f"Outside Bond escalated '{task}' to Mark Odom + CC Gulley — {reason[:80]}",
    )

    return {
        "automated":          False,
        "escalated_to":       ["Mark Odom", "CC Gulley"],
        "escalation_ids":     {"mark_odom": esc_mo, "cc_gulley": esc_cc},
        "instructions":       instructions,
        "server_ip":          server_ip,
    }


# ── Task handlers ─────────────────────────────────────────────────────────────

def _handle_bland_ai_allowlist(context: dict) -> dict:
    """Try to add the Render server IP to Bland AI's IP allowlist via API."""
    s = get_settings()
    ip = _server_ip()

    if not s.bland_ai_api_key:
        return {"automated": False, "reason": "BLAND_AI_API_KEY not configured", "server_ip": ip}

    try:
        r = httpx.post(
            f"{_BLAND_URL}/accounts/ip-allowlist",
            headers={"Authorization": f"Bearer {s.bland_ai_api_key}"},
            json={"ip": ip, "org_id": s.bland_ai_org_id or ""},
            timeout=15,
        )
        if r.status_code in (200, 201):
            return {"automated": True, "action": f"Added {ip} to Bland AI allowlist", "server_ip": ip}
        reason = f"Bland AI API {r.status_code}: {r.text[:200]}"
    except Exception as exc:
        reason = f"Bland AI API unreachable: {str(exc)[:200]}"

    return {"automated": False, "reason": reason, "server_ip": ip}


def _handle_render_env(context: dict) -> dict:
    """Set an environment variable on the Render service."""
    s = get_settings()
    key   = context.get("key", "")
    value = context.get("value", "")

    if not key:
        return {"automated": False, "reason": "No 'key' in context", "server_ip": None}
    if not s.render_api_key:
        return {"automated": False, "reason": "RENDER_API_KEY not configured", "server_ip": None}

    try:
        hdr = {"Authorization": f"Bearer {s.render_api_key}", "Accept": "application/json"}
        svcs = httpx.get(f"{_RENDER_URL}/services?limit=20", headers=hdr, timeout=15).json()
        svc_id = next(
            ((svc.get("service") or svc).get("id")
             for svc in svcs
             if _RENDER_SVC.lower() in (svc.get("service") or svc).get("name", "").lower()),
            None,
        )
        if not svc_id:
            return {"automated": False, "reason": f"Service '{_RENDER_SVC}' not found in Render account", "server_ip": None}

        r = httpx.put(
            f"{_RENDER_URL}/services/{svc_id}/env-vars",
            headers={**hdr, "Content-Type": "application/json"},
            json=[{"key": key, "value": value}],
            timeout=15,
        )
        if r.status_code in (200, 201):
            return {"automated": True, "action": f"Set {key} on Render service {svc_id}"}
        return {"automated": False, "reason": f"Render API {r.status_code}: {r.text[:200]}", "server_ip": None}
    except Exception as exc:
        return {"automated": False, "reason": f"Render API error: {str(exc)[:200]}", "server_ip": None}


def _handle_render_restart(context: dict) -> dict:
    """Trigger a Render service redeploy."""
    s = get_settings()
    if not s.render_api_key:
        return {"automated": False, "reason": "RENDER_API_KEY not configured", "server_ip": None}
    try:
        from .technical_team import _trigger_render_deploy
        ok, msg = _trigger_render_deploy(s.render_api_key)
        if ok:
            return {"automated": True, "action": msg}
        return {"automated": False, "reason": msg, "server_ip": None}
    except Exception as exc:
        return {"automated": False, "reason": str(exc)[:200], "server_ip": None}


def _handle_api_probe(context: dict) -> dict:
    """Probe a live API endpoint and return status."""
    url = context.get("url", "https://three-lakes-logistics-api.onrender.com/api/health/ping")
    try:
        r = httpx.get(url, timeout=10)
        return {"automated": True, "action": f"Probe {url} → {r.status_code}", "status_code": r.status_code}
    except Exception as exc:
        return {"automated": False, "reason": f"Probe failed: {str(exc)[:200]}", "server_ip": _server_ip()}


def _handle_generic(context: dict) -> dict:
    return {"automated": False, "reason": "No automated handler for this task type", "server_ip": _server_ip()}


_HANDLERS: dict[str, Any] = {
    "bland_ai_allowlist": _handle_bland_ai_allowlist,
    "render_env":         _handle_render_env,
    "render_restart":     _handle_render_restart,
    "api_probe":          _handle_api_probe,
    "generic":            _handle_generic,
}


# ── Entry point ───────────────────────────────────────────────────────────────

def run(payload: dict[str, Any]) -> dict[str, Any]:
    """Outside Bond field operative — attempt fix or escalate to command."""
    task          = str(payload.get("task", "generic"))
    context       = dict(payload.get("context") or {})
    phase         = str(payload.get("phase", "unknown"))
    error_details = str(payload.get("error_details", ""))

    handler = _HANDLERS.get(task, _handle_generic)
    result  = handler(context)

    if result.get("automated"):
        # Log success to org memory
        mem.remember(
            _NAME, "last_fix",
            {"task": task, "phase": phase, "action": result.get("action"),
             "timestamp": datetime.now(timezone.utc).isoformat()},
            confidence=0.95,
            summary=f"Outside Bond fixed '{task}': {result.get('action', '')[:80]}",
        )
        log_agent(
            _NAME, "automated_fix",
            payload={"task": task, "phase": phase},
            result=result.get("action", ""),
        )
        return {
            "agent":     _NAME,
            "task":      task,
            "phase":     phase,
            "automated": True,
            "action":    result.get("action"),
            "server_ip": result.get("server_ip"),
        }

    # Can't automate → escalate to Mark Odom + CC Gulley
    esc = _escalate_to_command(
        task, context,
        result.get("reason", "unknown failure"),
        result.get("server_ip"),
    )
    log_agent(
        _NAME, "escalation_filed",
        payload={"task": task, "phase": phase, "error": error_details[:120]},
        result=f"escalated to Mark Odom + CC Gulley — {result.get('reason', '')[:80]}",
    )
    return {
        "agent":         _NAME,
        "task":          task,
        "phase":         phase,
        "automated":     False,
        "reason":        result.get("reason"),
        "escalated_to":  esc["escalated_to"],
        "escalation_ids": esc["escalation_ids"],
        "instructions":  esc["instructions"],
        "server_ip":     esc.get("server_ip"),
    }
