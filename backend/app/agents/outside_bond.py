"""Outside Bond — IEBC Field Operative.

When James Bond (the auditor) identifies gaps that require external system
changes, Outside Bond takes over:

  1. Qwen (via OpenRouter) analyses the failure and classifies the task.
  2. Attempts the fix automatically via the relevant external API.
  3. If successful  → logs to org memory, returns success.
  4. If it can't    → creates Tier-2 executive escalations assigned to
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
  task          str   one of the task types above (or "auto" to let Qwen decide)
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

_NAME            = "outside_bond"
_BLAND_URL       = "https://api.bland.ai/v1"
_RENDER_URL      = "https://api.render.com/v1"
_RENDER_SVC      = "three-lakes-logistics-api"
_OPENROUTER_URL  = "https://openrouter.ai/api/v1/chat/completions"

_KNOWN_TASKS = ["bland_ai_allowlist", "render_env", "render_restart", "api_probe", "generic"]

_QWEN_SYSTEM = """You are Outside Bond, an autonomous IEBC field operative for 3 Lakes Logistics.
James Bond (your inside auditor) has handed you a failed test phase with raw error details.
Your job: classify the failure and decide on the best automated action.

Respond ONLY with a JSON object — no markdown, no prose — matching this schema:
{
  "task": "<one of: bland_ai_allowlist | render_env | render_restart | api_probe | generic>",
  "should_automate": true | false,
  "reasoning": "<1-2 sentences explaining the classification>",
  "context": {},
  "manual_instructions": "<step-by-step manual fix for command staff if automation fails>"
}

Classification rules:
- "bland_ai_allowlist"  → error mentions 'allowlist', '403', 'host not in allowlist', 'bland', or Vance/carrier call failures
- "render_restart"      → error mentions '502', '503', 'connection refused', 'service unavailable', 'timeout' on the main API
- "render_env"          → error mentions missing env var, configuration, secret, or key not found
- "api_probe"           → need to health-check a specific endpoint to confirm status
- "generic"             → no automated fix available; should_automate must be false

For render_env tasks, include {"key": "VAR_NAME"} in context if you can identify the missing variable."""


# ── Utilities ─────────────────────────────────────────────────────────────────

def _server_ip() -> str | None:
    """Return the server's outbound IP via ipify."""
    try:
        r = httpx.get("https://api.ipify.org?format=json", timeout=8)
        return r.json().get("ip")
    except Exception:
        return None


def _fallback_classify(error_details: str, phase: str) -> dict:
    """Hardcoded pattern matching used when both LLMs are unavailable."""
    err = error_details.lower()
    if any(p in err for p in ("allowlist", "bland", "host not in")):
        return {"task": "bland_ai_allowlist", "should_automate": True,
                "reasoning": "Bland AI IP allowlist pattern detected.",
                "context": {}, "manual_instructions": ""}
    if any(p in err for p in ("502", "503", "connection refused", "service unavailable")):
        return {"task": "render_restart", "should_automate": True,
                "reasoning": "Service unavailable pattern — restart Render service.",
                "context": {}, "manual_instructions": ""}
    if phase in ("carriers", "integration", "live"):
        return {"task": "bland_ai_allowlist", "should_automate": True,
                "reasoning": f"Phase '{phase}' failures typically caused by Bland AI IP block.",
                "context": {}, "manual_instructions": ""}
    return {"task": "generic", "should_automate": False,
            "reasoning": "No pattern matched — manual review required.",
            "context": {}, "manual_instructions": f"Review phase '{phase}' failure: {error_details[:200]}"}


def _qwen_reason(error_details: str, phase: str, context: dict) -> dict:
    """Ask Qwen (via OpenRouter) to classify the failure and decide the action.

    Falls back to Claude (anthropic_api_key) if OpenRouter is down,
    then to hardcoded pattern matching if both are unavailable.
    """
    s = get_settings()
    prompt_user = (
        f"Test phase '{phase}' FAILED.\n\n"
        f"Error details:\n{error_details[:1500]}\n\n"
        f"Additional context: {json.dumps(context)[:400]}\n\n"
        "Classify and decide. Respond with JSON only."
    )

    # ── Try OpenRouter / Qwen first ────────────────────────────────────────
    if s.openrouter_api_key:
        try:
            r = httpx.post(
                _OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {s.openrouter_api_key}",
                    "HTTP-Referer": "https://3lakeslogistics.com",
                    "X-Title": "3 Lakes Logistics — Outside Bond",
                    "Content-Type": "application/json",
                },
                json={
                    "model": s.openrouter_model,
                    "messages": [
                        {"role": "system", "content": _QWEN_SYSTEM},
                        {"role": "user",   "content": prompt_user},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 512,
                },
                timeout=25,
            )
            if r.status_code == 200:
                content = r.json()["choices"][0]["message"]["content"].strip()
                # Strip any accidental markdown fences
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                parsed = json.loads(content)
                if parsed.get("task") in _KNOWN_TASKS:
                    parsed["llm"] = "qwen"
                    return parsed
        except Exception:
            pass  # fall through to Claude

    # ── Fallback: Claude via Anthropic directly ────────────────────────────
    if s.anthropic_api_key:
        try:
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": s.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 512,
                    "system": _QWEN_SYSTEM,
                    "messages": [{"role": "user", "content": prompt_user}],
                },
                timeout=25,
            )
            if r.status_code == 200:
                content = r.json()["content"][0]["text"].strip()
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                parsed = json.loads(content)
                if parsed.get("task") in _KNOWN_TASKS:
                    parsed["llm"] = "claude-haiku"
                    return parsed
        except Exception:
            pass

    # ── Last resort: hardcoded patterns ───────────────────────────────────
    result = _fallback_classify(error_details, phase)
    result["llm"] = "fallback"
    return result


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
    """Outside Bond field operative — Qwen classifies, then attempt fix or escalate."""
    task          = str(payload.get("task", "auto"))
    context       = dict(payload.get("context") or {})
    phase         = str(payload.get("phase", "unknown"))
    error_details = str(payload.get("error_details", ""))

    qwen_report: dict = {}

    # Let Qwen reason when task is 'auto', 'generic', or unknown
    if task in ("auto", "generic") or task not in _HANDLERS:
        qwen_report = _qwen_reason(error_details, phase, context)
        task = qwen_report.get("task", "generic")
        # Qwen may provide richer context (e.g. env var name for render_env)
        if qwen_report.get("context"):
            context = {**context, **qwen_report["context"]}

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
            "llm":       qwen_report.get("llm"),
            "reasoning": qwen_report.get("reasoning"),
        }

    # Can't automate → escalate to Mark Odom + CC Gulley
    # Use Qwen's manual_instructions to enrich the escalation if available
    reason = result.get("reason", "unknown failure")
    if qwen_report.get("manual_instructions"):
        reason = f"{reason} | Qwen: {qwen_report['manual_instructions'][:300]}"

    esc = _escalate_to_command(task, context, reason, result.get("server_ip"))
    log_agent(
        _NAME, "escalation_filed",
        payload={"task": task, "phase": phase, "error": error_details[:120],
                 "llm": qwen_report.get("llm")},
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
        "llm":           qwen_report.get("llm"),
        "reasoning":     qwen_report.get("reasoning"),
    }
