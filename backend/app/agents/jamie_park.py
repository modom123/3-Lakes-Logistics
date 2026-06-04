"""Jamie Park — Node 115 · IEBC VP DevOps & Platform

Specialty: Infrastructure reliability, dependency health, API availability, platform limits.
Mission: Daily platform health checks — pings all external APIs, audits env-var coverage,
monitors Supabase/Render/Vercel limits, detects 24-hour cost spikes, and reports to
Marcus Reid (CTO). Escalates P1 failures immediately.

Runs daily at 07:50 UTC. Reports to Marcus Reid's memory; weekly summary goes to Mark Odom.

Payload keys (all optional):
  scope       str   "full" | "api_ping" | "env_audit" | "cost_spike" | "limits"  default: "full"
  silent      bool  suppress email even if issues found                           default: False

Outputs (org memory):
  jamie_park/platform_health       — full daily platform health report
  jamie_park/api_availability      — per-service up/down status with latency
  jamie_park/env_coverage          — env-var coverage audit
  jamie_park/cost_spike_alert      — 24-hour cost anomaly detection
  jamie_park/infra_limits          — service limit utilisation (Supabase rows, etc.)
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from . import memory as mem

_NAME = "jamie_park"
_FIRM = "IEBC"
_NODE = 115

# ── Services to ping ─────────────────────────────────────────────────────────

_PING_TARGETS: list[dict] = [
    {"service": "anthropic",    "url": "https://api.anthropic.com/v1/models",         "auth_header": "x-api-key",  "env_key": "ANTHROPIC_API_KEY"},
    {"service": "openrouter",   "url": "https://openrouter.ai/api/v1/models",         "auth_header": "Authorization", "env_key": "OPENROUTER_API_KEY", "auth_prefix": "Bearer "},
    {"service": "bland_ai",     "url": "https://api.bland.ai/v1/calls?limit=1",        "auth_header": "authorization","env_key": "BLAND_API_KEY"},
    {"service": "postmark",     "url": "https://api.postmarkapp.com/server",           "auth_header": "X-Postmark-Server-Token", "env_key": "POSTMARK_SERVER_TOKEN"},
    {"service": "google_maps",  "url": "https://maps.googleapis.com/maps/api/geocode/json?address=test&key={key}", "env_key": "GOOGLE_MAPS_API_KEY", "url_key": True},
    {"service": "checkr",       "url": "https://api.checkr.com/v1/candidates?per_page=1", "auth_env": "CHECKR_API_KEY", "basic_auth": True},
    {"service": "supabase",     "url": "{SUPABASE_URL}/rest/v1/",                      "env_key": "SUPABASE_KEY",   "auth_header": "apikey", "url_env": "SUPABASE_URL"},
    {"service": "render",       "url": "https://api.render.com/v1/services?limit=1",  "auth_header": "Authorization", "env_key": "RENDER_API_KEY", "auth_prefix": "Bearer "},
]

# ── Required environment variables ─────────────────────────────────────────────

_REQUIRED_ENV: dict[str, str] = {
    "ANTHROPIC_API_KEY":           "Anthropic Claude LLM",
    "OPENROUTER_API_KEY":          "OpenRouter / Qwen LLM",
    "BLAND_API_KEY":               "Bland AI voice calls",
    "TWILIO_ACCOUNT_SID":          "Twilio SMS",
    "TWILIO_AUTH_TOKEN":           "Twilio SMS auth",
    "POSTMARK_SERVER_TOKEN":       "Postmark transactional email",
    "SUPABASE_URL":                "Supabase database URL",
    "SUPABASE_KEY":                "Supabase service key",
    "RENDER_API_KEY":              "Render hosting control",
    "GOOGLE_MAPS_API_KEY":         "Google Maps geocoding",
    "CHECKR_API_KEY":              "Checkr background checks",
    "DAT_USERNAME":                "DAT load board",
    "DAT_PASSWORD":                "DAT load board auth",
    "MOTIVE_API_KEY":              "Motive ELD telematics",
    "STRIPE_SECRET_KEY":           "Stripe payments",
    "SECRET_KEY":                  "JWT / session secret",
    "BEARER_TOKEN":                "API bearer token",
}

# ── Known spend thresholds (daily, USD) ─────────────────────────────────────

_DAILY_SPIKE_THRESHOLDS: dict[str, float] = {
    "anthropic":   5.00,
    "openrouter":  2.00,
    "bland_ai":    10.00,
    "twilio":      3.00,
    "google":      1.50,
    "checkr":      50.00,
    "postmark":    1.00,
}


# ── Helper: API availability ping ────────────────────────────────────────────

def _ping_services() -> list[dict]:
    results = []
    s = get_settings()
    for target in _PING_TARGETS:
        service = target["service"]
        status = "unknown"
        latency_ms = None
        error = None

        env_key = target.get("env_key", "")
        api_key = os.environ.get(env_key, "") if env_key else ""
        if not api_key and env_key:
            results.append({
                "service": service, "status": "no_key",
                "latency_ms": None, "error": f"{env_key} not configured",
            })
            continue

        try:
            url = target["url"]
            if target.get("url_key"):
                url = url.replace("{key}", api_key)
            elif target.get("url_env"):
                base = os.environ.get(target["url_env"], "")
                url = target["url"].replace("{" + target["url_env"] + "}", base)

            headers: dict = {}
            auth = None
            if target.get("basic_auth"):
                auth = (api_key, "")
            elif target.get("auth_header"):
                prefix = target.get("auth_prefix", "")
                headers[target["auth_header"]] = f"{prefix}{api_key}"

            t0 = time.monotonic()
            r = httpx.get(url, headers=headers, auth=auth, timeout=8, follow_redirects=True)
            latency_ms = round((time.monotonic() - t0) * 1000)
            status = "up" if r.status_code < 500 else "degraded"
        except httpx.TimeoutException:
            status = "timeout"
            error = "request timed out (8s)"
        except Exception as exc:
            status = "error"
            error = str(exc)[:120]

        results.append({
            "service": service,
            "status": status,
            "latency_ms": latency_ms,
            "error": error,
        })

    return results


# ── Helper: env coverage audit ────────────────────────────────────────────────

def _env_coverage_audit() -> dict:
    present = []
    missing = []
    for var, description in _REQUIRED_ENV.items():
        val = os.environ.get(var, "")
        if val and val not in ("", "none", "null"):
            present.append({"var": var, "service": description})
        else:
            missing.append({"var": var, "service": description})
    coverage_pct = round(len(present) / len(_REQUIRED_ENV) * 100, 1)
    return {
        "total": len(_REQUIRED_ENV),
        "present": len(present),
        "missing": len(missing),
        "coverage_pct": coverage_pct,
        "missing_vars": missing,
        "present_vars": present,
    }


# ── Helper: cost spike detection ─────────────────────────────────────────────

def _cost_spike_check() -> list[dict]:
    spikes = []
    try:
        from ..cost_tracking.reporter import get_mtd_summary
        from ..supabase_client import get_supabase
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        yesterday = (now - timedelta(days=1)).isoformat()
        sb = get_supabase()
        rows = (
            sb.table("cost_entries")
            .select("service,cost_usd,recorded_at")
            .gte("recorded_at", yesterday)
            .execute()
            .data or []
        )
        by_service: dict[str, float] = {}
        for r in rows:
            svc = r.get("service", "unknown")
            by_service[svc] = round(by_service.get(svc, 0) + float(r.get("cost_usd") or 0), 4)

        for svc, threshold in _DAILY_SPIKE_THRESHOLDS.items():
            actual = by_service.get(svc, 0)
            if actual > threshold:
                spikes.append({
                    "service": svc,
                    "actual_usd": actual,
                    "threshold_usd": threshold,
                    "over_by_pct": round((actual - threshold) / threshold * 100, 1),
                    "severity": "critical" if actual > threshold * 2 else "warning",
                })
    except Exception:
        pass
    return spikes


# ── Helper: infrastructure limits ────────────────────────────────────────────

def _check_infra_limits() -> list[dict]:
    findings = []
    try:
        from ..supabase_client import get_supabase
        sb = get_supabase()
        tables_to_check = [
            ("cost_entries", 50_000),
            ("leads", 100_000),
            ("carriers", 10_000),
            ("agent_interactions", 200_000),
        ]
        for table, soft_limit in tables_to_check:
            try:
                res = sb.table(table).select("id", count="exact").limit(1).execute()
                count = res.count or 0
                pct = round(count / soft_limit * 100, 1)
                if pct >= 70:
                    findings.append({
                        "resource": f"supabase:{table}",
                        "current": count,
                        "soft_limit": soft_limit,
                        "utilisation_pct": pct,
                        "severity": "critical" if pct >= 90 else "warning",
                    })
            except Exception:
                pass
    except Exception:
        pass
    return findings


# ── Email report ──────────────────────────────────────────────────────────────

def _send_report(report: dict, silent: bool) -> bool:
    if silent:
        return False
    critical_count = report.get("critical_count", 0)
    warning_count = report.get("warning_count", 0)
    if critical_count == 0 and warning_count == 0:
        return False  # no issues — no email needed

    try:
        from ..email.postmark_client import PostmarkClient
        s = get_settings()

        api_rows = "".join(
            f"<tr><td>{r['service']}</td>"
            f"<td style='color:{'red' if r['status'] in ('down','timeout','error') else 'green'}'><b>{r['status']}</b></td>"
            f"<td>{r['latency_ms'] or '—'}ms</td>"
            f"<td>{r.get('error') or ''}</td></tr>"
            for r in report.get("api_availability", [])
        )
        spike_rows = "".join(
            f"<tr><td>{s['service']}</td><td>${s['actual_usd']:.4f}</td>"
            f"<td>${s['threshold_usd']:.2f}</td>"
            f"<td style='color:{'red' if s['severity']=='critical' else 'orange'}'>{s['over_by_pct']}%</td></tr>"
            for s in report.get("cost_spikes", [])
        )
        limit_rows = "".join(
            f"<tr><td>{l['resource']}</td><td>{l['utilisation_pct']}%</td>"
            f"<td style='color:{'red' if l['severity']=='critical' else 'orange'}'>{l['severity'].upper()}</td></tr>"
            for l in report.get("infra_limits", [])
        )
        env = report.get("env_coverage", {})
        missing_vars = "".join(f"<li>{v['var']} ({v['service']})</li>" for v in env.get("missing_vars", []))

        html = f"""
<html><body style="font-family:Arial,sans-serif;max-width:800px;margin:0 auto">
<h2 style="color:#1a1a2e">🔧 Jamie Park — Platform Health Report</h2>
<p><b>Date:</b> {report['timestamp'][:10]} &nbsp;|&nbsp;
   <b>Criticals:</b> <span style='color:red'>{critical_count}</span> &nbsp;|&nbsp;
   <b>Warnings:</b> <span style='color:orange'>{warning_count}</span></p>

<h3>API Availability</h3>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%">
<tr style="background:#f0f0f0"><th>Service</th><th>Status</th><th>Latency</th><th>Error</th></tr>
{api_rows}
</table>

{'<h3>Cost Spikes (24h)</h3><table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%"><tr style="background:#f0f0f0"><th>Service</th><th>Actual</th><th>Threshold</th><th>Over By</th></tr>' + spike_rows + '</table>' if spike_rows else ''}

{'<h3>Infrastructure Limits</h3><table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%"><tr style="background:#f0f0f0"><th>Resource</th><th>Utilisation</th><th>Severity</th></tr>' + limit_rows + '</table>' if limit_rows else ''}

<h3>Environment Coverage: {env.get('coverage_pct', 0)}%</h3>
<p>{env.get('present', 0)}/{env.get('total', 0)} required vars configured.</p>
{'<ul>' + missing_vars + '</ul>' if missing_vars else ''}

<hr><p style="color:#666;font-size:12px">Jamie Park · Node {_NODE} · IEBC Platform Team · 3 Lakes Logistics</p>
</body></html>"""

        subject_tag = "🚨 CRITICAL" if critical_count else "⚠️ WARNING"
        pm = PostmarkClient(s.postmark_server_token)
        pm.send(
            from_email="platform@3lakeslogistics.com",
            to_email="mark@3lakeslogistics.com",
            subject=f"{subject_tag} — Jamie Park Platform Health | {report['timestamp'][:10]}",
            html_body=html,
        )
        return True
    except Exception:
        return False


# ── Main entry point ──────────────────────────────────────────────────────────

def run(payload: dict[str, Any]) -> dict[str, Any]:
    scope  = str(payload.get("scope", "full")).lower()
    silent = bool(payload.get("silent", False))

    api_availability: list[dict] = []
    env_coverage: dict = {}
    cost_spikes: list[dict] = []
    infra_limits: list[dict] = []

    if scope in ("full", "api_ping"):
        api_availability = _ping_services()

    if scope in ("full", "env_audit"):
        env_coverage = _env_coverage_audit()

    if scope in ("full", "cost_spike"):
        cost_spikes = _cost_spike_check()

    if scope in ("full", "limits"):
        infra_limits = _check_infra_limits()

    # Count issues
    api_down = [s for s in api_availability if s["status"] in ("down", "timeout", "error")]
    critical_count = (
        len([s for s in api_availability if s["status"] in ("down",)]) +
        len([s for s in cost_spikes if s["severity"] == "critical"]) +
        len([l for l in infra_limits if l["severity"] == "critical"]) +
        len(env_coverage.get("missing_vars", []))
    )
    warning_count = (
        len([s for s in api_availability if s["status"] in ("timeout", "error", "degraded")]) +
        len([s for s in cost_spikes if s["severity"] == "warning"]) +
        len([l for l in infra_limits if l["severity"] == "warning"])
    )

    overall_status = "healthy"
    if critical_count > 0:
        overall_status = "critical"
    elif warning_count > 0:
        overall_status = "degraded"

    report = {
        "agent":            _NAME,
        "node":             _NODE,
        "firm":             _FIRM,
        "scope":            scope,
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "overall_status":   overall_status,
        "critical_count":   critical_count,
        "warning_count":    warning_count,
        "api_availability": api_availability,
        "api_down":         api_down,
        "env_coverage":     env_coverage,
        "cost_spikes":      cost_spikes,
        "infra_limits":     infra_limits,
    }

    email_sent = _send_report(report, silent)
    report["email_sent"] = email_sent

    mem.remember(
        _NAME, "platform_health", report, confidence=0.95,
        summary=f"Jamie platform: {overall_status} critical={critical_count} warn={warning_count}",
    )
    mem.remember(
        _NAME, "api_availability",
        {"services": api_availability, "down_count": len(api_down)},
        confidence=0.9,
        summary=f"{len([s for s in api_availability if s['status']=='up'])}/{len(api_availability)} APIs up",
    )
    if env_coverage:
        mem.remember(
            _NAME, "env_coverage", env_coverage, confidence=0.95,
            summary=f"Env coverage: {env_coverage.get('coverage_pct', 0)}% ({env_coverage.get('missing', 0)} missing)",
        )
    if cost_spikes:
        mem.remember(
            _NAME, "cost_spike_alert",
            {"spikes": cost_spikes, "count": len(cost_spikes)},
            confidence=0.9,
            summary=f"{len(cost_spikes)} cost spike(s) detected in last 24h",
        )
    if infra_limits:
        mem.remember(
            _NAME, "infra_limits",
            {"limits": infra_limits, "count": len(infra_limits)},
            confidence=0.85,
            summary=f"{len(infra_limits)} infrastructure limit warning(s)",
        )

    # Write into Marcus Reid's memory for CTO awareness
    mem.remember(
        "marcus_reid", "jamie_park_platform_health",
        {
            "overall_status": overall_status,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "api_down": [s["service"] for s in api_down],
            "cost_spikes": [s["service"] for s in cost_spikes],
            "env_coverage_pct": env_coverage.get("coverage_pct", 0),
            "timestamp": report["timestamp"],
        },
        confidence=0.9,
        summary=f"Jamie → Marcus: platform {overall_status}, {critical_count} critical",
    )

    log_agent(
        _NAME, "platform_health_check",
        payload={"scope": scope},
        result=f"status={overall_status} critical={critical_count} warn={warning_count} email={email_sent}",
    )

    return report
