"""Bond Escalation — invoked by nightly workflow when a test phase fails.

Usage:
    python tests/bond_escalate.py <phase>

Phase names: security, live, driver, integration, carriers

Flow:
  1. James Bond audits the org (gaps, silent agents, directives).
  2. Outside Bond attempts automated fixes for known error patterns:
       - "Host not in allowlist"  → tries Bland AI IP allowlist API
       - Any failure              → escalates to Mark Odom + CC Gulley
  3. If Outside Bond can't automate, Tier-2 escalation is created for command.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get(
    "API_BASE_URL", "https://three-lakes-logistics-api.onrender.com"
)
TOKEN = os.environ.get("API_BEARER_TOKEN", "")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

SCOPE_MAP = {
    "security":    "full",
    "live":        "ops",
    "driver":      "ops",
    "integration": "tech",
    "carriers":    "ops",
}

# Known error patterns → Outside Bond task type
ERROR_TASK_MAP = {
    "host not in allowlist": "bland_ai_allowlist",
    "bland":                 "bland_ai_allowlist",
    "connection refused":    "render_restart",
    "502 bad gateway":       "render_restart",
    "503 service":           "render_restart",
}


def _post(path: str, body: dict) -> dict | None:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, headers=HEADERS, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"   HTTP {e.code} — {e.read().decode()[:200]}")
        return None
    except Exception as exc:
        print(f"   Error: {exc}")
        return None


def _detect_task(phase: str) -> tuple[str, str]:
    """Read pytest output from the last run to detect error pattern.
    Returns (task_type, error_snippet).
    """
    # Read pytest output from GitHub Actions or local run
    output_file = os.environ.get("PYTEST_OUTPUT_FILE", "")
    error_text = ""

    if output_file and os.path.exists(output_file):
        with open(output_file) as f:
            error_text = f.read().lower()
    else:
        # Fallback: run a quick probe to detect live error
        probe = _post("/api/health/ping", {}) if False else None  # read-only
        try:
            import urllib.request as ur
            with ur.urlopen(f"{BASE_URL}/api/health/ping", timeout=8) as r:
                if r.status == 200:
                    error_text = ""  # API is up — phase failure is env-specific
        except Exception as exc:
            error_text = str(exc).lower()

    for pattern, task in ERROR_TASK_MAP.items():
        if pattern in error_text:
            return task, error_text[:300]

    # Default: carriers and integration failures are often Bland AI related
    if phase in ("carriers", "integration", "live"):
        return "bland_ai_allowlist", f"phase={phase} failed — likely Bland AI IP block"

    return "generic", f"phase={phase} failed — no specific error pattern detected"


def main() -> None:
    phase = sys.argv[1] if len(sys.argv) > 1 else "integration"
    scope = SCOPE_MAP.get(phase, "full")

    print(f"\n━━ Bond Escalation — Phase '{phase}' failed ━━━━━━━━━━━━━━━━━━━")

    # ── 1. James Bond audit ───────────────────────────────────────────────────
    print(f"\n[ James Bond — Audit scope: {scope} ]")
    bond = _post("/api/agents/james_bond/run", {"scope": scope, "top_n": 5, "remediate": True})
    if bond:
        gaps       = bond.get("high_gap_count", "?")
        remediated = bond.get("remediation", {})
        woken      = [k for k, v in remediated.items() if v == "woken"]
        print(f"   Audit complete — {gaps} HIGH-priority gap(s)")
        if woken:
            print(f"   Bond woke {len(woken)} silent agent(s): {', '.join(woken)}")
    else:
        gaps = "unknown"
        print("   Bond API offline — continuing to Outside Bond")

    # ── 2. Pass full error context to Outside Bond — Qwen decides the task ──────
    _, error_snippet = _detect_task(phase)
    print(f"\n[ Outside Bond — Qwen reasoning on phase '{phase}' ]")

    ob = _post("/api/agents/outside_bond/run", {
        "task":          "auto",   # Qwen classifies
        "phase":         phase,
        "error_details": error_snippet,
        "context":       {},
    })

    if ob:
        llm = ob.get("llm", "?")
        reasoning = ob.get("reasoning", "")
        print(f"   LLM engine: {llm}")
        if reasoning:
            print(f"   Reasoning: {reasoning}")
        if ob.get("automated"):
            print(f"   ✓ Automated fix applied: {ob.get('action')}")
            print(f"   Server IP: {ob.get('server_ip', '—')}")
        else:
            print(f"   ✗ Could not automate — escalated to command")
            print(f"   Assigned: {', '.join(ob.get('escalated_to', []))}")
            esc_ids = ob.get("escalation_ids", {})
            for person, eid in esc_ids.items():
                print(f"   Escalation ({person}): {eid}")
            instructions = ob.get("instructions", "")
            if instructions:
                print(f"\n   Instructions filed:\n   {instructions[:400]}")
    else:
        print("   Outside Bond API offline — filing manual escalation")
        # Direct fallback escalation if Outside Bond is unreachable
        esc = _post("/api/executives/escalations", {
            "tier":        2,
            "event_type":  "api_down",
            "description": (
                f"Nightly '{phase}' phase FAILED. Outside Bond unreachable. "
                f"Likely cause: Bland AI IP allowlist blocking Render. "
                f"Fix: app.bland.ai → Settings → IP Allowlist → add Render server IP."
            ),
            "assigned_to": "Mark Odom",
        })
        if esc:
            print(f"   Fallback escalation filed: {esc.get('id', '?')}")

    print(f"\n━━ Bond field operation complete ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


if __name__ == "__main__":
    main()
