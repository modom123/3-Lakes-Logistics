#!/usr/bin/env python3
"""Trigger the Bond Office deploy endpoint from CI.

Calls POST /api/bond/deploy on the live API, which applies pending Supabase
migrations and triggers a Render redeploy, then prints the report. Exits
non-zero if any migration failed so the workflow surfaces the problem.

Env:
  API_BASE          default https://three-lakes-logistics-api.onrender.com
  API_BEARER_TOKEN  required — internal Bond endpoints use bearer auth
  ACTION            sync | migrate | redeploy | deploy-status   (default sync)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API_BASE = os.environ.get("API_BASE", "https://three-lakes-logistics-api.onrender.com").rstrip("/")
TOKEN    = os.environ.get("API_BEARER_TOKEN", "").strip()
ACTION   = os.environ.get("ACTION", "sync").strip()

_PATHS = {
    "sync":          ("POST", "/api/bond/deploy"),
    "migrate":       ("POST", "/api/bond/migrate"),
    "redeploy":      ("POST", "/api/bond/redeploy"),
    "deploy-status": ("GET",  "/api/bond/deploy-status"),
}


def main() -> int:
    if not TOKEN:
        print("ERROR: API_BEARER_TOKEN not set")
        return 2
    if ACTION not in _PATHS:
        print(f"ERROR: unknown ACTION '{ACTION}' (expected {list(_PATHS)})")
        return 2

    method, path = _PATHS[ACTION]
    req = urllib.request.Request(
        API_BASE + path,
        data=b"{}" if method == "POST" else None,
        method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:500]}")
        return 1
    except Exception as exc:
        print(f"Request failed: {exc}")
        return 1

    print(json.dumps(body, indent=2)[:4000])
    if body.get("failed"):
        print(f"\n✗ {len(body['failed'])} migration(s) failed")
        return 1
    print(f"\n✓ {body.get('summary', 'done')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
