"""Bond Escalation — invoked by nightly workflow when a test phase fails.

Usage:
    python tests/bond_escalate.py <phase>

Phase names: security, live, driver, integration, carriers

Calls POST /api/agents/james_bond/run to audit then creates a
Tier-1 executive escalation so the failure appears on the Eagle Eye
IEBC Executive Command panel.
"""
from __future__ import annotations
import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get(
    "API_BASE_URL", "https://three-lakes-logistics-api.onrender.com"
)
TOKEN = os.environ.get("API_BEARER_TOKEN", "taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE")

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

EVENT_MAP = {
    "security":    "fraud_alert",
    "live":        "api_down",
    "driver":      "api_down",
    "integration": "api_down",
    "carriers":    "api_down",
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


def main() -> None:
    phase = sys.argv[1] if len(sys.argv) > 1 else "integration"
    scope = SCOPE_MAP.get(phase, "full")
    event = EVENT_MAP.get(phase, "api_down")

    print(f"\n━━ Bond Escalation — Phase '{phase}' failed ━━━━━━━━━━━━━━━━━━━")

    # 1. Dispatch Bond audit
    print(f"\n[ James Bond — Audit scope: {scope} ]")
    bond = _post("/api/agents/james_bond/run", {"scope": scope, "top_n": 5})
    if bond:
        gaps = bond.get("high_gap_count", "?")
        print(f"   Audit complete — {gaps} HIGH-priority gap(s) surfaced")
        brief = (bond.get("brief") or "")[:200]
        if brief:
            print(f"   Brief: {brief}")
    else:
        gaps = "unknown"
        print("   Bond API offline — proceeding to escalation anyway")

    # 2. Create Tier-1 executive escalation
    print(f"\n[ Executive Escalation ]")
    desc = (
        f"Nightly '{phase}' test phase FAILED — Bond dispatched "
        f"(scope={scope}, high_gaps={gaps}). "
        "Review Bond Office → Last Audit in Eagle Eye."
    )
    esc = _post("/api/executives/escalations", {
        "tier":        1,
        "event_type":  event,
        "description": desc,
        "assigned_to": "James Bond",
    })
    if esc:
        eid = esc.get("id") or esc.get("items", [{}])[0].get("id", "?")
        print(f"   Escalation created — ID: {eid}")
    else:
        print("   Escalation creation failed (API may be offline)")

    print(f"\n━━ Bond handoff complete ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


if __name__ == "__main__":
    main()
