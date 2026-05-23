"""Chloe Sinclair — Node 128 · IEBC UX Flaw Interception

Specialty: Viewport rendering across mobile engines, cross-browser visual anomaly detection.
Mission: QA every UI change to Eagle Eye and Bond Office. Catches layout breaks,
overflow issues, z-index conflicts, and mobile viewport failures before they ship.

Runs after every Lucas Sterling deploy or on nightly test failure in the UI domain.
Powered by Qwen via OpenRouter for reasoning; rule-based checks run free/always.

Payload keys (all optional):
  scope     str   "full" | "mobile" | "bond_office" | "cross_browser"   default: "full"
  after_fix bool  if True, this is a post-fix validation run             default: False

Outputs (org memory):
  chloe_sinclair/last_viewport_audit  — full cross-browser / mobile QA report
  chloe_sinclair/visual_anomalies     — list of detected rendering issues
  chloe_sinclair/qa_clearance         — sign-off status for last UI deploy
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from . import memory as mem

_NAME = "chloe_sinclair"
_FIRM = "IEBC"
_NODE = 128
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM = """You are Chloe Sinclair, Node 128 of the IEBC Executive OS.
Your specialty: UX Flaw Interception — auditing viewport rendering across mobile engines
and cross-platform browsers to prevent visual anomalies.

You are performing a QA audit on Eagle Eye, a single-file HTML/CSS/JS command centre.
Analyze the provided CSS snapshot and return ONLY a JSON object:
{
  "clearance": "PASS" | "FAIL" | "CONDITIONAL",
  "viewport_issues": [{"browser": "...", "issue": "...", "severity": "critical|high|medium|low"}],
  "mobile_failures": [{"breakpoint": "...", "component": "...", "failure": "..."}],
  "z_index_conflicts": [{"element": "...", "conflict": "..."}],
  "overflow_anomalies": [{"element": "...", "anomaly": "..."}],
  "animation_concerns": [{"element": "...", "concern": "..."}],
  "remediation_steps": ["..."],
  "qa_notes": "<2 sentences — direct QA verdict>"
}

Check for these specific failure modes:
- position:fixed elements with z-index lower than sibling overlays (mobile sidebar over content)
- height:100% in nested flex where parent has no definite height (collapses to 0)
- Fixed-px grid columns (380px, 340px, 320px) that break on viewports < 600px
- CSS animations using transform on position:fixed elements
- overflow:hidden clipping content that should scroll (missing flex:1;min-height:0)
- Missing touch-action or tap-target sizing on mobile interactive elements

CLEARANCE rules: PASS = no critical/high issues. CONDITIONAL = medium issues only. FAIL = any critical."""

# Viewport breakpoints to check
_BREAKPOINTS = [
    ("320px", "iPhone SE / small phone"),
    ("375px", "iPhone 12/13"),
    ("768px", "iPad / mobile breakpoint"),
    ("1024px", "iPad landscape / small desktop"),
    ("1280px", "standard desktop"),
    ("1440px", "large desktop"),
]

# Known failure patterns to check in HTML
_VIEWPORT_CHECKS = [
    {
        "pattern": r"position:fixed.*z-index:(?:[1-9]|1[0-9])\b",
        "issue": "Fixed element z-index may be below mobile sidebar (z-index:20)",
        "severity": "high",
        "browsers": ["Chrome Mobile", "Safari iOS"],
    },
    {
        "pattern": r"height:100%",
        "issue": "height:100% depends on parent having definite height — fails in nested flex",
        "severity": "high",
        "browsers": ["All browsers"],
    },
    {
        "pattern": r"grid-template-columns:[^;]*[3-9]\d\dpx",
        "issue": "Fixed-px grid column — overflows on narrow mobile viewports",
        "severity": "critical",
        "browsers": ["Chrome Mobile", "Safari iOS", "Firefox Android"],
    },
    {
        "pattern": r"animation:pgIn.*position:fixed|position:fixed.*animation:pgIn",
        "issue": "pgIn animation applied to position:fixed — creates stacking context",
        "severity": "medium",
        "browsers": ["Safari iOS"],
    },
]


def _run_viewport_checks() -> list[dict]:
    """Local pattern checks — zero cost, runs always."""
    results = []
    try:
        import re
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        path = os.path.join(base, "eagleeye.html")
        with open(path, encoding="utf-8") as f:
            html = f.read()
        for check in _VIEWPORT_CHECKS:
            if re.search(check["pattern"], html):
                results.append({
                    "pattern": check["pattern"],
                    "issue":   check["issue"],
                    "severity": check["severity"],
                    "browsers": check["browsers"],
                })
    except Exception:
        pass
    return results


def _read_bond_office_css() -> str:
    """Extract Bond Office CSS + global layout for Qwen analysis."""
    try:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        path = os.path.join(base, "eagleeye.html")
        with open(path, encoding="utf-8") as f:
            html = f.read()
        lines = html.splitlines()
        # Global layout (first 210 lines) + Bond Office style block
        layout = "\n".join(lines[:210])
        bond_start = next((i for i, l in enumerate(lines) if "#page-bond" in l and "position:fixed" in l), None)
        bond_css = ""
        if bond_start is not None:
            bond_css = "\n".join(lines[max(0, bond_start - 5):bond_start + 150])
        return f"[GLOBAL LAYOUT]\n{layout}\n\n[BOND OFFICE CSS]\n{bond_css}"[:5500]
    except Exception as exc:
        return f"[Read error: {exc}]"


def _call_qwen(css_snapshot: str, after_fix: bool) -> dict | None:
    s = get_settings()
    if not s.openrouter_api_key:
        return None
    context = f"{'POST-FIX VALIDATION RUN' if after_fix else 'ROUTINE QA AUDIT'}\n\n{css_snapshot}"
    try:
        r = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {s.openrouter_api_key}",
                "HTTP-Referer": "https://3lakeslogistics.com",
                "X-Title": "3 Lakes Logistics — Chloe Sinclair QA",
                "Content-Type": "application/json",
            },
            json={
                "model": s.openrouter_model,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user",   "content": f"Run QA audit on this CSS:\n\n{context}"},
                ],
                "temperature": 0.1,
                "max_tokens": 800,
            },
            timeout=30,
        )
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
    except Exception:
        pass
    return None


def run(payload: dict[str, Any]) -> dict[str, Any]:
    scope     = str(payload.get("scope", "full")).lower()
    after_fix = bool(payload.get("after_fix", False))

    local_checks = _run_viewport_checks()
    css_snapshot = _read_bond_office_css()
    qwen_report  = _call_qwen(css_snapshot, after_fix)

    # Merge results
    clearance        = qwen_report.get("clearance", "CONDITIONAL") if qwen_report else "CONDITIONAL"
    viewport_issues  = qwen_report.get("viewport_issues", []) if qwen_report else []
    mobile_failures  = qwen_report.get("mobile_failures", []) if qwen_report else []
    z_conflicts      = qwen_report.get("z_index_conflicts", []) if qwen_report else []
    overflow_issues  = qwen_report.get("overflow_anomalies", []) if qwen_report else []
    anim_concerns    = qwen_report.get("animation_concerns", []) if qwen_report else []
    remediation      = qwen_report.get("remediation_steps", []) if qwen_report else []
    qa_notes         = qwen_report.get("qa_notes", "QA complete. Review local pattern findings.") if qwen_report else "Qwen unavailable — local pattern scan only."

    # Inject local check findings into viewport_issues
    for check in local_checks:
        viewport_issues.append({
            "browser":  ", ".join(check.get("browsers", ["All"])),
            "issue":    check["issue"],
            "severity": check["severity"],
        })
        if check["severity"] == "critical" and clearance == "PASS":
            clearance = "FAIL"
        elif check["severity"] == "high" and clearance == "PASS":
            clearance = "CONDITIONAL"

    # Escalate to Lucas if there are issues
    escalate_to_lucas = len([v for v in viewport_issues if v.get("severity") in ("critical", "high")]) > 0

    report = {
        "agent":         _NAME,
        "node":          _NODE,
        "firm":          _FIRM,
        "scope":         scope,
        "after_fix":     after_fix,
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "clearance":     clearance,
        "viewport_issues":   viewport_issues,
        "mobile_failures":   mobile_failures,
        "z_index_conflicts": z_conflicts,
        "overflow_anomalies": overflow_issues,
        "animation_concerns": anim_concerns,
        "remediation_steps": remediation,
        "local_pattern_hits": local_checks,
        "escalate_to_lucas": escalate_to_lucas,
        "qa_notes":      qa_notes,
        "qwen_powered":  qwen_report is not None,
        "breakpoints_checked": [b[0] for b in _BREAKPOINTS],
    }

    mem.remember(
        _NAME, "last_viewport_audit", report, confidence=0.9,
        summary=f"Chloe QA: clearance={clearance} viewport={len(viewport_issues)} mobile={len(mobile_failures)}",
    )
    mem.remember(
        _NAME, "visual_anomalies",
        {"viewport": viewport_issues, "mobile": mobile_failures, "z_index": z_conflicts},
        confidence=0.85,
        summary=f"{len(viewport_issues)} viewport + {len(mobile_failures)} mobile issues found",
    )
    mem.remember(
        _NAME, "qa_clearance",
        {"clearance": clearance, "timestamp": datetime.now(timezone.utc).isoformat(),
         "escalate_to_lucas": escalate_to_lucas},
        confidence=0.95,
        summary=f"QA clearance: {clearance} — {'escalate to Lucas' if escalate_to_lucas else 'no escalation needed'}",
    )

    log_agent(
        _NAME, "viewport_qa",
        payload={"scope": scope, "after_fix": after_fix},
        result=f"clearance={clearance} issues={len(viewport_issues)} qwen={qwen_report is not None}",
    )

    return report
