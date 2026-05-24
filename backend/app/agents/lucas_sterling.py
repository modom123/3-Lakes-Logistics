"""Lucas Sterling — Node 101 · IEBC Vanilla Full-Stack UI Developer

Specialty: Zero-framework styling, DOM speed optimization, Eagle Eye UI architecture.
Mission: Audit, design, and implement Eagle Eye / Bond Office UI improvements.
Enforces strict vanilla HTML/CSS/JS — no build step, no framework, maximum DOM speed.

Powered by Qwen via OpenRouter for cost-efficient analysis (~$0.00035/1K tokens).

Payload keys (all optional):
  scope    str   "full" | "bond_office" | "layout" | "mobile"   default: "full"
  report   bool  return detailed findings only, no fixes         default: False

Outputs (org memory):
  lucas_sterling/last_ui_audit     — full CSS/layout audit
  lucas_sterling/ui_directives     — ordered improvement queue
  lucas_sterling/pending_fixes     — issues awaiting implementation
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

_NAME = "lucas_sterling"
_FIRM = "IEBC"
_NODE = 101
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM = """You are Lucas Sterling, Node 101 of the IEBC Executive OS.
Your specialty: Vanilla Full-Stack Code — zero-framework styling, DOM speed optimization.
You are auditing the Eagle Eye command centre (a single-file HTML/CSS/JS application).

Analyze the provided HTML/CSS snapshot and return ONLY a JSON object:
{
  "health_score": <0-100>,
  "critical_issues": [{"area": "...", "problem": "...", "fix": "..."}],
  "improvements": [{"area": "...", "suggestion": "...", "effort": "low|medium|high"}],
  "mobile_concerns": ["..."],
  "performance_notes": ["..."],
  "summary": "<2 sentences — direct, no filler>"
}

Rules:
- Flag height:100% chains in nested flex without a definite parent as CRITICAL
- Flag position:fixed elements with z-index below sibling overlays as CRITICAL
- Flag missing overflow:hidden on flex scroll containers as HIGH
- Flag fixed-px grid columns that break on mobile as HIGH
- Flag animation on position:fixed elements as MEDIUM
- Keep critical_issues to real bugs, not style preferences
- Improvements must be actionable vanilla CSS/HTML changes"""

_KNOWN_UI_PATTERNS = [
    ("height:100%", "height:100% in nested flex without definite parent — collapses silently"),
    ("position:fixed", "position:fixed element — verify z-index and top offset"),
    ("grid-template-columns:1fr [0-9]", "fixed-px grid column — breaks on narrow screens"),
    ("animation:pgIn", "pgIn animation on fixed element — creates unwanted stacking context"),
    ("overflow-y:auto", "scroll container — confirm flex:1;min-height:0 on parent chain"),
]


def _read_eagleeye_snapshot() -> str:
    """Extract relevant CSS blocks from eagleeye.html for Qwen analysis."""
    try:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        path = os.path.join(base, "eagleeye.html")
        with open(path, encoding="utf-8") as f:
            html = f.read()
        # Extract Bond Office style block + layout CSS (lines 1-200 + bond style block)
        lines = html.splitlines()
        layout_lines = lines[:210]  # global layout CSS
        bond_start = next((i for i, l in enumerate(lines) if "page-bond" in l and "<style>" in l), None)
        bond_block: list[str] = []
        if bond_start is not None:
            for line in lines[bond_start:bond_start + 160]:
                bond_block.append(line)
        snapshot = "\n".join(layout_lines) + "\n\n[BOND OFFICE STYLE BLOCK]\n" + "\n".join(bond_block)
        return snapshot[:6000]  # keep within Qwen context
    except Exception as exc:
        return f"[Could not read eagleeye.html: {exc}]"


def _rule_based_scan() -> list[dict]:
    """Fast local pattern scan — no LLM cost."""
    issues = []
    try:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        path = os.path.join(base, "eagleeye.html")
        with open(path, encoding="utf-8") as f:
            html = f.read()
        import re
        for pattern, description in _KNOWN_UI_PATTERNS:
            matches = len(re.findall(pattern, html))
            if matches:
                issues.append({
                    "pattern": pattern,
                    "description": description,
                    "occurrences": matches,
                })
    except Exception:
        pass
    return issues


def _call_qwen(snapshot: str) -> dict | None:
    s = get_settings()
    if not s.openrouter_api_key:
        return None
    try:
        r = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {s.openrouter_api_key}",
                "HTTP-Referer": "https://3lakeslogistics.com",
                "X-Title": "3 Lakes Logistics — Lucas Sterling UI Audit",
                "Content-Type": "application/json",
            },
            json={
                "model": s.openrouter_model,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user",   "content": f"Audit this Eagle Eye CSS snapshot:\n\n{snapshot}"},
                ],
                "temperature": 0.1,
                "max_tokens": 900,
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
    scope      = str(payload.get("scope", "full")).lower()
    report_only = bool(payload.get("report", False))

    snapshot    = _read_eagleeye_snapshot()
    rule_issues = _rule_based_scan()
    qwen_audit  = _call_qwen(snapshot)

    health_score = qwen_audit.get("health_score", 75) if qwen_audit else 70
    critical     = qwen_audit.get("critical_issues", []) if qwen_audit else []
    improvements = qwen_audit.get("improvements", []) if qwen_audit else []
    mobile       = qwen_audit.get("mobile_concerns", []) if qwen_audit else []
    perf         = qwen_audit.get("performance_notes", []) if qwen_audit else []
    summary      = qwen_audit.get("summary", "UI audit complete. Manual review recommended.") if qwen_audit else "Qwen unavailable — rule-based scan only."

    # Merge rule-based patterns into critical issues
    for issue in rule_issues:
        critical.append({
            "area":    "Pattern scan",
            "problem": issue["description"],
            "fix":     f"{issue['occurrences']} occurrence(s) found — review each one.",
        })

    directives = []
    idx = 1
    for c in critical[:5]:
        directives.append(f"{idx}. CRITICAL: {c['area']} — {c['fix']}")
        idx += 1
    for imp in improvements[:3]:
        if imp.get("effort") in ("low", "medium"):
            directives.append(f"{idx}. {imp['effort'].upper()}: {imp['area']} — {imp['suggestion']}")
            idx += 1

    report = {
        "agent":       _NAME,
        "node":        _NODE,
        "firm":        _FIRM,
        "scope":       scope,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "health_score":  health_score,
        "critical_issues": critical,
        "improvements":    improvements,
        "mobile_concerns": mobile,
        "performance_notes": perf,
        "rule_scan":       rule_issues,
        "directives":      directives,
        "summary":         summary,
        "qwen_powered":    qwen_audit is not None,
    }

    mem.remember(
        _NAME, "last_ui_audit", report, confidence=0.85,
        summary=f"Lucas UI audit: score={health_score} critical={len(critical)} improvements={len(improvements)}",
    )
    mem.remember(
        _NAME, "ui_directives",
        {"directives": directives, "count": len(directives)},
        confidence=0.9,
        summary=directives[0] if directives else "No critical UI issues found",
    )
    mem.remember(
        _NAME, "pending_fixes",
        {"critical": critical, "mobile": mobile},
        confidence=0.8,
        summary=f"{len(critical)} critical + {len(mobile)} mobile issues pending",
    )

    log_agent(
        _NAME, "ui_audit",
        payload={"scope": scope},
        result=f"health={health_score} critical={len(critical)} qwen={qwen_audit is not None}",
    )

    return report
