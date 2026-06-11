#!/usr/bin/env python3
"""Set / patch Render environment variables for 3 Lakes Logistics API.

Usage (full sync — sets all known vars):
    RENDER_API_KEY=rnd_xxxx python3 scripts/render-env-setup.py

Usage (patch specific vars + optional redeploy):
    RENDER_API_KEY=rnd_xxxx python3 scripts/render-env-setup.py \
        --patch KEY1=VALUE1 KEY2=VALUE2 --deploy

Usage (trigger redeploy only):
    RENDER_API_KEY=rnd_xxxx python3 scripts/render-env-setup.py --deploy

Flags:
  --patch KEY=VALUE ...  Update only the listed key/value pairs (leave others untouched)
  --deploy               Trigger a Render redeploy after env-var changes
  --service-id SVC_ID    Skip service discovery (faster, required in CI)

Bond auto-deploy uses --patch + --deploy to push specific vars and redeploy
without human involvement.
"""
from __future__ import annotations

import argparse
import os
import sys
import json
import urllib.request
import urllib.error

RENDER_API   = "https://api.render.com/v1"
SERVICE_NAME = "3-lakes-logistics-api"

# ── Known env var values (safe to set automatically) ───────────────────────
KNOWN_VARS: dict[str, str] = {
    "ENV":                    "production",
    "PORT":                   "8080",
    "SUPABASE_URL":           "https://zngipootstubwvgdmckt.supabase.co",
    "SUPABASE_ANON_KEY":      "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpuZ2lwb290c3R1Ynd2Z2RtY2t0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMxMjk3ODUsImV4cCI6MjA4ODcwNTc4NX0.6MXR8q-CKVuiiJaJKuckxABAUQ-siuyP0-KoaLkt33g",
    "API_BEARER_TOKEN":       os.environ.get("API_BEARER_TOKEN", ""),
    "BOND_API_KEY":           "xUvzgCnQZ-j-0HYTh749E1t6AKX3RNYFqNfoNVcnH1Z0KFCQUy693Q",
    "DAYTONA_SANDBOX_ID":     "2a50d3c2-f813-49c0-8dec-f9248581c5c6",
    "TWILIO_FROM_NUMBER":     "+13135469006",
    "OPENROUTER_MODEL":       "qwen/qwen-2.5-72b-instruct",
    "SENDGRID_INBOUND_EMAIL": "loads@3lakeslogistics.com",
    "POSTMARK_FROM_EMAIL":    "ops@3lakeslogistics.com",
    "CORS_ORIGINS":           (
        "https://3lakeslogistics.com,https://www.3lakeslogistics.com,"
        "https://3-lakes-logistics.vercel.app,https://3-lakes-logistic.vercel.app"
    ),
}

# ── Secrets that must be set manually (or via Bond --patch) ─────────────────
MANUAL_SECRETS = [
    ("SUPABASE_SERVICE_ROLE_KEY", "Supabase → Project Settings → API → service_role key"),
    ("ANTHROPIC_API_KEY",         "console.anthropic.com → API Keys"),
    ("OPENROUTER_API_KEY",        "openrouter.ai/keys"),
    ("STRIPE_SECRET_KEY",         "dashboard.stripe.com → Developers → API keys → Secret key"),
    ("STRIPE_WEBHOOK_SECRET",     "dashboard.stripe.com → Developers → Webhooks → signing secret"),
    ("TWILIO_ACCOUNT_SID",        "console.twilio.com → Account SID"),
    ("TWILIO_AUTH_TOKEN",         "console.twilio.com → Auth Token"),
    ("SENDGRID_API_KEY",          "app.sendgrid.com → Settings → API Keys"),
    ("BLAND_AI_API_KEY",          "app.bland.ai → API Keys"),
    ("BLAND_AI_ORG_ID",           "app.bland.ai → Account Settings → Org ID"),
    ("BLAND_AI_WEBHOOK_SECRET",   "app.bland.ai → Webhooks → secret"),
]


def render_request(method: str, path: str, body: list | dict | None = None) -> dict | list:
    api_key = os.environ.get("RENDER_API_KEY", "").strip()
    if not api_key:
        print("ERROR: RENDER_API_KEY environment variable not set.")
        print("Get it from: https://dashboard.render.com/u/settings#api-keys")
        sys.exit(1)

    url  = RENDER_API + path
    data = json.dumps(body).encode() if body is not None else None
    req  = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        print(f"Render API error {e.code}: {body_text}")
        sys.exit(1)
    except Exception as exc:
        print(f"Render API request failed: {exc}")
        sys.exit(1)


def find_service_id() -> str:
    print(f"Looking up service '{SERVICE_NAME}'...")
    result   = render_request("GET", f"/services?name={SERVICE_NAME}&limit=5")
    services = result if isinstance(result, list) else result.get("services", [])
    for item in services:
        svc = item.get("service", item)
        if svc.get("name") == SERVICE_NAME:
            sid = svc["id"]
            print(f"  ✓ Found: {sid}")
            return sid
    print(f"ERROR: Service '{SERVICE_NAME}' not found on Render.")
    sys.exit(1)


def get_current_env(service_id: str) -> dict[str, str]:
    """Fetch current env vars from Render so a --patch doesn't wipe unknowns."""
    result = render_request("GET", f"/services/{service_id}/env-vars")
    if isinstance(result, list):
        return {item["key"]: item["value"] for item in result}
    return {}


def set_env_vars(service_id: str, vars_dict: dict[str, str]) -> None:
    print(f"\nPushing {len(vars_dict)} environment variable(s) to {service_id}...")
    payload = [{"key": k, "value": v} for k, v in vars_dict.items() if v]
    render_request("PUT", f"/services/{service_id}/env-vars", payload)
    print("  ✓ Environment variables updated.\n")


def trigger_deploy(service_id: str) -> None:
    deploy_hook = os.environ.get("RENDER_DEPLOY_HOOK_URL", "").strip()
    if deploy_hook:
        print("Triggering deploy via hook URL...")
        req = urllib.request.Request(deploy_hook, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                print(f"  ✓ Deploy hook accepted (HTTP {r.status})")
                return
        except Exception as exc:
            print(f"  ⚠ Hook failed: {exc} — falling back to Render API deploy")

    print(f"Triggering deploy via Render API for {service_id}...")
    result = render_request("POST", f"/services/{service_id}/deploys", {})
    deploy_id = result.get("id", result.get("deploy", {}).get("id", "?"))
    print(f"  ✓ Deploy triggered — deploy ID: {deploy_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render env-var sync for 3 Lakes Logistics")
    parser.add_argument("--patch",      nargs="+", metavar="KEY=VALUE",
                        help="Update only these key=value pairs (leaves others intact)")
    parser.add_argument("--deploy",     action="store_true",
                        help="Trigger a Render redeploy after env-var changes")
    parser.add_argument("--service-id", metavar="SVC_ID",
                        help="Skip service discovery (use known service ID)")
    args = parser.parse_args()

    service_id = args.service_id or find_service_id()

    if args.patch:
        # Patch mode: read current vars, merge, write back
        overrides: dict[str, str] = {}
        for pair in args.patch:
            if "=" not in pair:
                print(f"  ⚠ Skipping malformed patch entry (expected KEY=VALUE): {pair!r}")
                continue
            k, _, v = pair.partition("=")
            overrides[k.strip()] = v.strip()

        print(f"\n[ Bond Patch Mode — {len(overrides)} var(s) ]")
        for k, v in overrides.items():
            masked = v[:4] + "…" if len(v) > 8 else "***"
            print(f"  {k} = {masked}")

        current = get_current_env(service_id)
        merged  = {**current, **overrides}
        set_env_vars(service_id, merged)
    else:
        # Full sync mode
        set_env_vars(service_id, {k: v for k, v in KNOWN_VARS.items() if v})

    if args.deploy:
        trigger_deploy(service_id)

    if not args.patch:
        print("=" * 60)
        print("DONE — Known vars set in Render.")
        print("=" * 60)
        print("\n⚠️  The following SECRETS still need to be set manually")
        print("   in the Render dashboard (or via Bond --patch):\n")
        for key, where in MANUAL_SECRETS:
            print(f"  {key:<35} ← {where}")
        print("\nRender dashboard: https://dashboard.render.com")
        if not args.deploy:
            print("Re-run with --deploy to trigger a redeploy after setting secrets.")


if __name__ == "__main__":
    main()
