"""Marcus Reid — CTO · IEBC System Integrity Co-Owner (Node MR-01).

Role: Chief Technology Officer. Owns the AI model strategy, vendor
relationships, platform architecture, and all upgrade decisions.
Reports directly to Mark Odom (Commander). Co-owns the
system_integrity master score with Jamie Park (Node JP-02).

Responsibilities:
  · Tech Stack Review    — weekly evaluation of every API, LLM, and service
  · Model Watch          — tracks new AI model releases and deprecation notices
  · Pricing Intelligence — flags vendor pricing changes vs current spend
  · Upgrade Proposals    — recommends stack changes with cost/benefit analysis
  · Cost Intelligence    — reads IEBC Cost Tracking for spend trends and burn rate
  · Vendor Risk          — single-points-of-failure, lock-in risks, alternatives

Schedule:
  Weekly  Friday 06:00 UTC — full tech stack review → email to mark@3lakeslogistics.com
  On-demand via POST /api/agents/marcus_reid/run

Memory outputs:
  marcus_reid/last_review        — full JSON review report
  marcus_reid/upgrade_proposals  — active pending upgrade items
  marcus_reid/model_registry     — AI models in use + known alternatives
  marcus_reid/risk_flags         — active tech risk items
  org/system_integrity           — system_integrity master score update

LLM strategy:
  Upgrade analysis → Qwen via OpenRouter (~$0.00035/1K tokens)
  Executive summary → Qwen first, Claude fallback
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from ..logging_service import get_logger, log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from . import memory as mem

log = get_logger("iebc.marcus_reid")

_NAME = "marcus_reid"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# ── Current tech stack registry ───────────────────────────────────────────────

_STACK = {
    "ai_llm": [
        {"service": "anthropic",  "model": "claude-sonnet-4-6",       "tier": "primary",   "use": "CLM scanner, contract extraction", "cost_tier": "medium"},
        {"service": "anthropic",  "model": "claude-haiku-4-5-20251001","tier": "secondary", "use": "agent routing, qualification",     "cost_tier": "low"},
        {"service": "openrouter", "model": "qwen/qwen-2.5-72b-instruct","tier": "primary",  "use": "10 IEBC exec agents (analysis)",   "cost_tier": "very_low"},
    ],
    "communications": [
        {"service": "bland_ai",  "version": "v1",  "use": "outbound prospecting calls",       "cost": "$0.06/min"},
        {"service": "twilio",    "version": "2010","use": "SMS alerts, dispatch notifications","cost": "$0.0075/SMS"},
        {"service": "postmark",  "version": "API", "use": "transactional email outbound",      "cost": "$0.0015/email"},
        {"service": "sendgrid",  "version": "v3",  "use": "inbound email parse (load docs)",   "cost": "$0.001/email"},
    ],
    "infrastructure": [
        {"service": "supabase", "plan": "Pro",     "version": "2.9.1 client", "use": "primary database + realtime"},
        {"service": "render",   "plan": "Standard","version": "Docker",        "use": "FastAPI backend hosting"},
        {"service": "vercel",   "plan": "Pro",     "version": "SPA",           "use": "Eagle Eye frontend hosting"},
        {"service": "redis",    "plan": "optional","version": "redis>=5.0.0",  "use": "rate limiting + circuit breaker"},
    ],
    "compliance_data": [
        {"service": "checkr",       "version": "v1", "use": "MVR + background checks", "cost": "$15-65/check"},
        {"service": "fmcsa_webkey", "version": "v1", "use": "carrier lookup (Shield agent)"},
    ],
    "eld_telematics": [
        {"service": "motive",      "use": "primary ELD webhook"},
        {"service": "samsara",     "use": "secondary ELD integration"},
        {"service": "geotab",      "use": "fleet telemetry"},
        {"service": "omnitracs",   "use": "legacy carrier support"},
    ],
    "load_boards": [
        {"service": "dat",         "plan": "$149/mo", "use": "primary load sourcing (Sonny)"},
        {"service": "truckstop",   "plan": "usage",   "use": "secondary load board"},
        {"service": "123loadboard","plan": "usage",   "use": "tertiary load board"},
    ],
    "payments_identity": [
        {"service": "stripe",           "version": "11.1.0","use": "subscriptions, payouts, identity"},
        {"service": "stripe_identity",  "version": "v2",    "use": "driver KYC / license verification"},
    ],
    "mapping_vision": [
        {"service": "google_maps",   "version": "v1", "use": "geocoding, distance matrix"},
        {"service": "google_vision", "version": "v1", "use": "OCR for rate-con / BOL documents"},
    ],
    "crm_data": [
        {"service": "airtable", "plan": "Pro $20/mo", "use": "carrier leads migration"},
        {"service": "firebase", "plan": "Blaze $25/mo","use": "mobile app backend"},
    ],
}

# Known alternatives Marcus watches for upgrade opportunities
_ALTERNATIVES = {
    "qwen/qwen-2.5-72b-instruct": [
        "qwen/qwen-2.5-coder-32b-instruct (~$0.00009/1K — faster, cheaper for routing)",
        "google/gemma-3-27b-it:free (free tier for analysis tasks)",
        "meta-llama/llama-3.3-70b-instruct (~$0.00012/1K — strong general reasoning)",
    ],
    "claude-sonnet-4-6": [
        "claude-haiku-4-5-20251001 (10x cheaper — evaluate if CLM quality holds)",
        "claude-sonnet-4-7 when released (expected performance improvement)",
    ],
    "bland_ai": [
        "vapi.ai (structured voice AI, better transcript quality, $0.05/min)",
        "retell.ai (conversation AI with built-in CRM hooks)",
    ],
    "checkr": [
        "sterling (competitive pricing for MVR bundles)",
        "HireRight (enterprise MVR, better trucking industry support)",
    ],
    "airtable": [
        "Migrate to Supabase table fully (already paying $25/mo, eliminate $20/mo Airtable)",
    ],
}

_QWEN_SYSTEM = """You are Marcus Reid, CTO at 3 Lakes Logistics IEBC Executive OS.
You are performing the weekly tech stack review for Commander Mark Odom.

Your job: analyze the current tech stack state, cost data, and Jamie Park's platform report,
then produce a precise upgrade and risk assessment.

Respond ONLY with a JSON object — no markdown, no prose:
{
  "system_integrity_score": <integer 0-100>,
  "upgrade_proposals": [
    {
      "priority": "HIGH|MEDIUM|LOW",
      "service": "<service name>",
      "current": "<current state>",
      "proposed": "<proposed change>",
      "rationale": "<1-sentence why>",
      "estimated_savings_usd_monthly": <number or null>,
      "effort": "low|medium|high",
      "action_owner": "marcus_reid|jamie_park|mark_odom"
    }
  ],
  "risk_flags": [
    {"severity": "CRITICAL|HIGH|MEDIUM|LOW", "service": "<service>", "risk": "<what could break>", "mitigation": "<fix>"}
  ],
  "model_recommendations": [
    {"current_model": "<model>", "recommended": "<alternative>", "rationale": "<why>", "monthly_saving_estimate": "<$X>"}
  ],
  "stack_health_summary": "<2-3 sentences for the Commander>",
  "top_action": "<single most important thing to do this week>"
}"""


# ── LLM helpers ───────────────────────────────────────────────────────────────

def _call_qwen(system: str, user: str, max_tokens: int = 1200) -> str | None:
    s = get_settings()
    if not s.openrouter_api_key:
        return None
    try:
        r = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {s.openrouter_api_key}",
                "HTTP-Referer": "https://3lakeslogistics.com",
                "X-Title": "3 Lakes Logistics — Marcus Reid CTO",
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
            timeout=30,
        )
        if r.status_code == 200:
            _d = r.json()
            _u = _d.get("usage", {})
            try:
                from ..cost_tracking import track_openrouter as _tor
                _tor(s.openrouter_model, _u.get("prompt_tokens", 0), _u.get("completion_tokens", 0), agent=_NAME)
            except Exception:
                pass
            return _d["choices"][0]["message"]["content"].strip()
    except Exception:
        pass
    return None


def _call_claude(system: str, user: str, max_tokens: int = 1000) -> str | None:
    s = get_settings()
    if not s.anthropic_api_key:
        return None
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": s.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=25,
        )
        if r.status_code == 200:
            _d = r.json()
            try:
                from ..cost_tracking import track_anthropic as _ta
                _u = _d.get("usage", {})
                _ta("claude-haiku-4-5-20251001", _u.get("input_tokens", 0), _u.get("output_tokens", 0), agent=_NAME)
            except Exception:
                pass
            return _d["content"][0]["text"].strip()
    except Exception:
        pass
    return None


def _llm_review(context: str) -> dict | None:
    raw = _call_qwen(_QWEN_SYSTEM, context, max_tokens=1200)
    if not raw:
        raw = _call_claude(_QWEN_SYSTEM, context, max_tokens=1200)
    if not raw:
        return None
    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception:
        return None


# ── Data gathering ─────────────────────────────────────────────────────────────

def _cost_snapshot() -> dict:
    """Pull MTD cost summary from cost_tracking."""
    try:
        from ..cost_tracking.reporter import get_mtd_summary
        s = get_mtd_summary()
        return {
            "api_cost_mtd":          s.get("api_cost_usd", 0),
            "subscription_monthly":  s.get("subscription_cost_usd", 0),
            "total_mtd":             s.get("total_cost_usd", 0),
            "by_service":            s.get("by_service", {}),
            "by_category":           s.get("by_category", {}),
        }
    except Exception:
        return {}


def _env_audit() -> dict:
    """Check which optional integrations are actually configured."""
    s = get_settings()
    configured = []
    missing = []
    for name, val in {
        "anthropic":    s.anthropic_api_key,
        "openrouter":   s.openrouter_api_key,
        "bland_ai":     s.bland_ai_api_key,
        "twilio":       s.twilio_account_sid,
        "postmark":     s.postmark_server_token,
        "sendgrid":     s.sendgrid_api_key,
        "stripe":       s.stripe_secret_key,
        "checkr":       s.checkr_api_key,
        "airtable":     s.airtable_api_key,
        "google_maps":  s.google_maps_api_key,
        "google_vision":s.google_vision_credentials_json,
        "motive":       s.motive_api_key,
        "samsara":      s.samsara_api_key,
        "dat":          s.dat_client_id,
        "firebase":     s.firebase_service_account if hasattr(s, "firebase_service_account") else "",
        "render":       s.render_api_key,
    }.items():
        (configured if val else missing).append(name)
    return {"configured": configured, "missing_or_unconfigured": missing}


def _jamie_park_report() -> dict:
    """Read Jamie Park's latest platform health report from memory."""
    report = mem.recall_value("jamie_park", "platform_health") or {}
    return report


# ── Main review function ──────────────────────────────────────────────────────

def tech_stack_review() -> dict[str, Any]:
    ts = datetime.now(timezone.utc).isoformat()
    costs = _cost_snapshot()
    env = _env_audit()
    platform = _jamie_park_report()

    # Build context for LLM analysis
    context = json.dumps({
        "review_date": ts,
        "current_stack": _STACK,
        "known_alternatives": _ALTERNATIVES,
        "cost_snapshot": costs,
        "configured_integrations": env["configured"],
        "unconfigured_integrations": env["missing_or_unconfigured"],
        "platform_health_from_jamie_park": platform,
        "stack_size": {
            "total_services": sum(len(v) for v in _STACK.values()),
            "ai_models_in_use": len(_STACK["ai_llm"]),
            "configured_apis": len(env["configured"]),
        },
    }, default=str)

    review = _llm_review(f"Perform weekly CTO tech stack review:\n\n{context}")

    if not review:
        review = {
            "system_integrity_score": 85,
            "upgrade_proposals": [],
            "risk_flags": [
                {"severity": "LOW", "service": "llm_analysis", "risk": "OpenRouter/Claude unavailable for analysis", "mitigation": "Check API keys"}
            ],
            "model_recommendations": [],
            "stack_health_summary": "LLM analysis unavailable this run. Stack operational based on env audit.",
            "top_action": "Verify OPENROUTER_API_KEY and ANTHROPIC_API_KEY are set in Render environment.",
        }

    score = review.get("system_integrity_score", 85)
    proposals = review.get("upgrade_proposals", [])
    risks = review.get("risk_flags", [])
    high_priority = [p for p in proposals if p.get("priority") == "HIGH"]
    critical_risks = [r for r in risks if r.get("severity") == "CRITICAL"]

    result = {
        "agent": _NAME,
        "role": "CTO — System Integrity",
        "timestamp": ts,
        "system_integrity_score": score,
        "upgrade_proposals": proposals,
        "risk_flags": risks,
        "model_recommendations": review.get("model_recommendations", []),
        "stack_health_summary": review.get("stack_health_summary", ""),
        "top_action": review.get("top_action", ""),
        "cost_snapshot": costs,
        "env_audit": env,
        "high_priority_proposals": len(high_priority),
        "critical_risks": len(critical_risks),
    }

    # Write to org memory
    mem.remember(_NAME, "last_review", result, confidence=0.9, source_agent=_NAME,
                 summary=f"CTO review score={score} proposals={len(proposals)} risks={len(risks)}")
    mem.remember(_NAME, "upgrade_proposals", proposals, confidence=0.9, source_agent=_NAME,
                 summary=f"{len(proposals)} upgrade proposals · {len(high_priority)} HIGH priority")
    mem.remember(_NAME, "risk_flags", risks, confidence=0.9, source_agent=_NAME,
                 summary=f"{len(risks)} risk flags · {len(critical_risks)} CRITICAL")
    mem.remember(_NAME, "model_registry",
                 {"in_use": _STACK["ai_llm"], "alternatives": _ALTERNATIVES},
                 confidence=0.95, source_agent=_NAME)
    mem.remember("org", "system_integrity",
                 {"score": score, "owner": "marcus_reid+jamie_park", "trend": "stable",
                  "last_updated": ts, "critical_risks": len(critical_risks)},
                 confidence=0.9, source_agent=_NAME)

    return result


def _send_weekly_report(result: dict) -> dict:
    """Email weekly CTO report to Mark Odom."""
    score = result["system_integrity_score"]
    proposals = result["upgrade_proposals"]
    risks = result["risk_flags"]
    ts = datetime.now(timezone.utc).strftime("%B %d, %Y")

    score_color = "#22c55e" if score >= 90 else "#f59e0b" if score >= 75 else "#ef4444"

    proposals_html = ""
    for p in proposals[:8]:
        priority_color = "#ef4444" if p.get("priority") == "HIGH" else "#f59e0b" if p.get("priority") == "MEDIUM" else "#22c55e"
        saving = f" · Est. ${p.get('estimated_savings_usd_monthly',0):.0f}/mo saved" if p.get("estimated_savings_usd_monthly") else ""
        proposals_html += f"""<tr>
          <td style="padding:6px 8px"><span style="color:{priority_color};font-weight:600">{p.get('priority','')}</span></td>
          <td style="padding:6px 8px;font-weight:600">{p.get('service','')}</td>
          <td style="padding:6px 8px">{p.get('proposed','')}</td>
          <td style="padding:6px 8px;font-size:12px;color:#555">{p.get('rationale','')}{saving}</td>
        </tr>"""

    risks_html = ""
    for r in risks[:5]:
        sev_color = "#b91c1c" if r.get("severity") in ("CRITICAL","HIGH") else "#92400e"
        risks_html += f"<li style='color:{sev_color}'><strong>[{r.get('severity','')}] {r.get('service','')}:</strong> {r.get('risk','')} — <em>{r.get('mitigation','')}</em></li>"

    costs = result.get("cost_snapshot", {})
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;padding:20px;color:#222">
  <div style="background:#0f172a;color:#fff;padding:20px 24px;border-radius:8px;margin-bottom:20px">
    <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;opacity:.6;margin-bottom:4px">IEBC · SYSTEM INTEGRITY REPORT</div>
    <h1 style="margin:0;font-size:20px">Marcus Reid — CTO Weekly Review</h1>
    <div style="opacity:.7;font-size:13px;margin-top:4px">{ts} · Prepared for Commander Mark Odom</div>
  </div>

  <div style="display:flex;gap:12px;margin-bottom:20px">
    <div style="flex:1;text-align:center;background:#f8fafc;border-radius:8px;padding:16px;border-top:4px solid {score_color}">
      <div style="font-size:11px;text-transform:uppercase;color:#64748b;letter-spacing:1px">System Integrity</div>
      <div style="font-size:36px;font-weight:700;color:{score_color}">{score}</div>
      <div style="font-size:11px;color:#94a3b8">out of 100</div>
    </div>
    <div style="flex:1;text-align:center;background:#f8fafc;border-radius:8px;padding:16px;border-top:4px solid #3b82f6">
      <div style="font-size:11px;text-transform:uppercase;color:#64748b;letter-spacing:1px">MTD API Cost</div>
      <div style="font-size:36px;font-weight:700;color:#3b82f6">${costs.get('api_cost_mtd',0):.2f}</div>
      <div style="font-size:11px;color:#94a3b8">+ ${costs.get('subscription_monthly',0):.0f}/mo subscriptions</div>
    </div>
    <div style="flex:1;text-align:center;background:#f8fafc;border-radius:8px;padding:16px;border-top:4px solid #f59e0b">
      <div style="font-size:11px;text-transform:uppercase;color:#64748b;letter-spacing:1px">Upgrade Proposals</div>
      <div style="font-size:36px;font-weight:700;color:#f59e0b">{len(proposals)}</div>
      <div style="font-size:11px;color:#94a3b8">{result['high_priority_proposals']} HIGH priority</div>
    </div>
  </div>

  <div style="background:#f0fdf4;border-left:4px solid #22c55e;padding:12px 16px;border-radius:4px;margin-bottom:20px">
    <strong>Stack Summary:</strong> {result.get('stack_health_summary','')}
  </div>
  <div style="background:#fffbeb;border-left:4px solid #f59e0b;padding:10px 16px;border-radius:4px;margin-bottom:20px">
    <strong>Top Action This Week:</strong> {result.get('top_action','')}
  </div>

  <h3>Upgrade Proposals</h3>
  <table style="width:100%;border-collapse:collapse;font-size:13px">
    <thead><tr style="background:#f1f5f9">
      <th style="padding:6px 8px;text-align:left">Priority</th>
      <th style="padding:6px 8px;text-align:left">Service</th>
      <th style="padding:6px 8px;text-align:left">Proposed Change</th>
      <th style="padding:6px 8px;text-align:left">Rationale</th>
    </tr></thead>
    <tbody>{proposals_html or '<tr><td colspan="4" style="padding:12px;text-align:center;color:#94a3b8">No upgrade proposals this week — stack is healthy</td></tr>'}</tbody>
  </table>

  {"<h3>Risk Flags</h3><ul>" + risks_html + "</ul>" if risks else ""}

  <p style="margin-top:30px;font-size:11px;color:#94a3b8">
    Marcus Reid · CTO · IEBC System Integrity · 3 Lakes Logistics AI Platform<br>
    Eagle Eye → Exec Command → Marcus Reid to view full report and memory history
  </p>
</body></html>"""

    from ..email.smtp_sender import send_transactional
    result_send = send_transactional(
        to="mark@3lakeslogistics.com",
        subject=f"[CTO Report] System Integrity {score}/100 · {len(proposals)} Upgrade Proposals — {ts}",
        body_html=html,
        mailbox="info",
    )
    if result_send.get("ok"):
        return {"sent": True, "to": "mark@3lakeslogistics.com"}
    log.warning("marcus_reid report email failed: %s", result_send.get("error") or result_send.get("reason"))
    return {"sent": False, "error": result_send.get("error") or result_send.get("reason")}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action", "review")
    log.info("marcus_reid starting action=%s", action)

    result = tech_stack_review()

    email_result = _send_weekly_report(result)
    result["email"] = email_result

    mem.log_interaction(
        _NAME, "mark_odom", "weekly_cto_report",
        payload={"score": result["system_integrity_score"]},
        result={"proposals": len(result["upgrade_proposals"]), "risks": len(result["risk_flags"])},
        outcome="success",
        outcome_notes=(
            f"integrity={result['system_integrity_score']} "
            f"proposals={result['high_priority_proposals']} HIGH "
            f"email_sent={email_result.get('sent')}"
        ),
    )

    log_agent(
        _NAME, "weekly_review",
        payload={"action": action},
        result=(
            f"score={result['system_integrity_score']} "
            f"proposals={len(result['upgrade_proposals'])} "
            f"risks={len(result['risk_flags'])} "
            f"email={email_result.get('sent')}"
        ),
    )

    return {"agent": _NAME, "role": "CTO", **result}
