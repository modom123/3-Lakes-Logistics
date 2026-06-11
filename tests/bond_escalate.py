"""Bond Escalation & Internal Reporting — invoked by nightly workflow.

Usage:
    python tests/bond_escalate.py <phase>
    python tests/bond_escalate.py report <event> <message>

Phase names: security, live, driver, integration, carriers, e2e

Flow:
  1. Bond files a mission status report to internal command (/api/agents/james_bond/log).
  2. James Bond audits the org (gaps, silent agents, directives).
  3. Outside Bond attempts automated fixes for known error patterns:
       - "Host not in allowlist"  → tries Bland AI IP allowlist API
       - Any failure              → escalates to Mark Odom + CC Gulley
  4. Bond files a final status report on completion.
"""
from __future__ import annotations
import datetime
import json
import os
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
    "e2e":         "ops",
}

ERROR_TASK_MAP = {
    "host not in allowlist": "bland_ai_allowlist",
    "bland":                 "bland_ai_allowlist",
    "connection refused":    "render_restart",
    "502 bad gateway":       "render_restart",
    "503 service":           "render_restart",
    "timeout":               "render_restart",
    "playwright":            "e2e_failure",
    "locator":               "e2e_failure",
    "expect":                "e2e_failure",
}


def _now() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


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


def bond_report(event: str, message: str, details: dict | None = None) -> None:
    """File a mission status update to Bond's internal command log.

    Bond calls this at every significant milestone so Eagle Eye shows
    live field status without waiting for phase completion.
    """
    payload = {
        "agent":     "james_bond",
        "event":     event,
        "message":   message,
        "details":   details or {},
        "timestamp": _now(),
        "source":    "nightly_ci",
        "run_id":    os.environ.get("GITHUB_RUN_ID", "local"),
        "run_url":   (
            f"https://github.com/{os.environ.get('GITHUB_REPOSITORY','')}"
            f"/actions/runs/{os.environ.get('GITHUB_RUN_ID','')}"
        ),
    }
    print(f"\n[ Bond Internal Report — {event} ]")
    print(f"   {message}")
    result = _post("/api/agents/james_bond/log", payload)
    if result:
        log_id = result.get("id", result.get("log_id", "?"))
        print(f"   ✓ Filed to Eagle Eye command log: {log_id}")
    else:
        # Fallback: post to executives escalations table so it's never lost
        fallback = _post("/api/executives/escalations", {
            "tier":        1,
            "event_type":  event,
            "description": message,
            "assigned_to": "James Bond",
            "auto_filed":  True,
        })
        if fallback:
            print(f"   ✓ Fallback to escalations table: {fallback.get('id','?')}")
        else:
            print(f"   ⚠ Internal log offline — event: {event}")


def _detect_task(phase: str) -> tuple[str, str]:
    """Read pytest/playwright output to detect known error patterns."""
    output_file = os.environ.get("PYTEST_OUTPUT_FILE", "")
    error_text = ""

    if output_file and os.path.exists(output_file):
        with open(output_file) as f:
            error_text = f.read().lower()
    else:
        try:
            import urllib.request as ur
            with ur.urlopen(f"{BASE_URL}/api/health/ping", timeout=8) as r:
                if r.status == 200:
                    error_text = ""
        except Exception as exc:
            error_text = str(exc).lower()

    for pattern, task in ERROR_TASK_MAP.items():
        if pattern in error_text:
            return task, error_text[:300]

    if phase in ("carriers", "integration", "live"):
        return "bland_ai_allowlist", f"phase={phase} failed — likely Bland AI IP block"
    if phase == "e2e":
        return "e2e_failure", f"phase=e2e failed — Playwright test(s) failed"

    return "generic", f"phase={phase} failed — no specific error pattern detected"


def main() -> None:
    # ── Handle "report" sub-command (called by workflow for status updates) ──
    if len(sys.argv) >= 2 and sys.argv[1] == "report":
        event   = sys.argv[2] if len(sys.argv) > 2 else "status"
        message = sys.argv[3] if len(sys.argv) > 3 else "no message"
        bond_report(event, message)
        return

    phase = sys.argv[1] if len(sys.argv) > 1 else "integration"
    scope = SCOPE_MAP.get(phase, "full")

    print(f"\n━━ Bond Field Operation — Phase '{phase}' failed ━━━━━━━━━━━━━━━━")

    # ── 1. File immediate internal report — command knows Bond is on it ──────
    bond_report(
        event   = f"phase_{phase}_failed",
        message = f"Phase '{phase}' failed in nightly CI. Bond initiated response.",
        details = {"phase": phase, "scope": scope},
    )

    # ── 2. James Bond audit ───────────────────────────────────────────────────
    print(f"\n[ James Bond — Audit scope: {scope} ]")
    bond_report(
        event   = "audit_start",
        message = f"Bond auditing org — scope={scope}",
    )

    bond = _post("/api/agents/james_bond/run", {
        "scope":     scope,
        "top_n":     5,
        "remediate": True,
    })

    if bond:
        gaps       = bond.get("high_gap_count", "?")
        remediated = bond.get("remediation", {})
        woken      = [k for k, v in remediated.items() if v == "woken"]
        print(f"   Audit complete — {gaps} HIGH-priority gap(s)")
        if woken:
            print(f"   Bond woke {len(woken)} silent agent(s): {', '.join(woken)}")
        bond_report(
            event   = "audit_complete",
            message = f"Audit done — {gaps} HIGH gaps, {len(woken)} agents woken",
            details = {"gaps": gaps, "woken": woken, "remediation": remediated},
        )
    else:
        print("   Bond API offline — continuing to Outside Bond")
        bond_report("audit_failed", "Bond API unreachable — proceeding to Outside Bond")

    # ── 3. Outside Bond — Qwen decides the fix ───────────────────────────────
    task_type, error_snippet = _detect_task(phase)
    print(f"\n[ Outside Bond — Qwen reasoning on phase '{phase}' ]")
    bond_report(
        event   = "outside_bond_start",
        message = f"Outside Bond reasoning on '{phase}' — detected task: {task_type}",
        details = {"task_type": task_type, "error_snippet": error_snippet[:200]},
    )

    ob = _post("/api/agents/outside_bond/run", {
        "task":          "auto",
        "phase":         phase,
        "error_details": error_snippet,
        "context":       {},
    })

    if ob:
        llm       = ob.get("llm", "?")
        reasoning = ob.get("reasoning", "")
        print(f"   LLM engine: {llm}")
        if reasoning:
            print(f"   Reasoning: {reasoning}")

        if ob.get("automated"):
            action = ob.get("action")
            print(f"   ✓ Automated fix applied: {action}")
            print(f"   Server IP: {ob.get('server_ip', '—')}")
            bond_report(
                event   = "fix_applied",
                message = f"Outside Bond automated fix: {action}",
                details = {"action": action, "server_ip": ob.get("server_ip"), "llm": llm},
            )
        else:
            assignees = ob.get("escalated_to", [])
            esc_ids   = ob.get("escalation_ids", {})
            print(f"   ✗ Could not automate — escalated to command")
            print(f"   Assigned: {', '.join(assignees)}")
            for person, eid in esc_ids.items():
                print(f"   Escalation ({person}): {eid}")
            instructions = ob.get("instructions", "")
            if instructions:
                print(f"\n   Instructions filed:\n   {instructions[:400]}")
            bond_report(
                event   = "escalation_filed",
                message = f"Manual escalation filed — assigned to: {', '.join(assignees)}",
                details = {
                    "escalated_to": assignees,
                    "escalation_ids": esc_ids,
                    "instructions": instructions[:400],
                    "llm": llm,
                },
            )
    else:
        print("   Outside Bond API offline — filing manual escalation")
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
        bond_report(
            event   = "escalation_fallback",
            message = f"Outside Bond offline — direct escalation filed for phase '{phase}'",
            details = {"escalation_id": esc.get("id") if esc else None},
        )
        if esc:
            print(f"   Fallback escalation filed: {esc.get('id', '?')}")

    # ── 4. Final mission report ───────────────────────────────────────────────
    bond_report(
        event   = f"phase_{phase}_response_complete",
        message = f"Bond field operation complete for phase '{phase}'.",
    )
    print(f"\n━━ Bond field operation complete ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


if __name__ == "__main__":
    main()
