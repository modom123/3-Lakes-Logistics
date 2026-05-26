#!/usr/bin/env python3
"""Set Render environment variables for 3 Lakes Logistics API.

Usage:
    RENDER_API_KEY=rnd_xxxx python3 scripts/render-env-setup.py

Get your Render API key from: https://dashboard.render.com/u/settings#api-keys

The script will:
  1. Find the 3-lakes-logistics-api service on Render
  2. Set all env vars that have known values (bearer token, bond key, Supabase URL, etc.)
  3. Print a list of secrets that still need to be set manually in the Render dashboard
"""
from __future__ import annotations

import os
import sys
import json
import urllib.request
import urllib.error

RENDER_API = "https://api.render.com/v1"
SERVICE_NAME = "3-lakes-logistics-api"

# ── Known env var values (safe to set automatically) ───────────────────────
KNOWN_VARS = {
    "ENV":                   "production",
    "PORT":                  "8080",
    "SUPABASE_URL":          "https://zngipootstubwvgdmckt.supabase.co",
    "SUPABASE_ANON_KEY":     "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpuZ2lwb290c3R1Ynd2Z2RtY2t0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMxMjk3ODUsImV4cCI6MjA4ODcwNTc4NX0.6MXR8q-CKVuiiJaJKuckxABAUQ-siuyP0-KoaLkt33g",
    "API_BEARER_TOKEN":      "taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE",
    "BOND_API_KEY":          "xUvzgCnQZ-j-0HYTh749E1t6AKX3RNYFqNfoNVcnH1Z0KFCQUy693Q",
    "DAYTONA_SANDBOX_ID":    "2a50d3c2-f813-49c0-8dec-f9248581c5c6",
    "TWILIO_FROM_NUMBER":    "+13135469006",
    "OPENROUTER_MODEL":      "qwen/qwen-2.5-72b-instruct",
    "SENDGRID_INBOUND_EMAIL":"loads@3lakeslogistics.com",
    "POSTMARK_FROM_EMAIL":   "ops@3lakeslogistics.com",
    "CORS_ORIGINS":          "https://3lakeslogistics.com,https://www.3lakeslogistics.com,https://3-lakes-logistics.vercel.app,https://3-lakes-logistic.vercel.app",
}

# ── Secrets that must be set manually ──────────────────────────────────────
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


def render_request(method: str, path: str, body: dict | None = None) -> dict:
    api_key = os.environ.get("RENDER_API_KEY", "").strip()
    if not api_key:
        print("ERROR: RENDER_API_KEY environment variable not set.")
        print("Get it from: https://dashboard.render.com/u/settings#api-keys")
        sys.exit(1)

    url = RENDER_API + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"Render API error {e.code}: {e.read().decode()}")
        sys.exit(1)


def find_service_id() -> str:
    print(f"Looking up service '{SERVICE_NAME}'...")
    result = render_request("GET", f"/services?name={SERVICE_NAME}&limit=5")
    services = result if isinstance(result, list) else result.get("services", [])
    for item in services:
        svc = item.get("service", item)
        if svc.get("name") == SERVICE_NAME:
            return svc["id"]
    print(f"ERROR: Service '{SERVICE_NAME}' not found on Render.")
    print("Verify the service name at https://dashboard.render.com")
    sys.exit(1)


def set_env_vars(service_id: str) -> None:
    print(f"\nSetting {len(KNOWN_VARS)} environment variables on service {service_id}...")
    payload = [{"key": k, "value": v} for k, v in KNOWN_VARS.items()]
    render_request("PUT", f"/services/{service_id}/env-vars", payload)
    print("✅ Environment variables set successfully.\n")


def main() -> None:
    service_id = find_service_id()
    set_env_vars(service_id)

    print("=" * 60)
    print("DONE — Known vars have been set in Render.")
    print("=" * 60)
    print("\n⚠️  The following SECRETS still need to be set manually")
    print("   in the Render dashboard (Dashboard → Service → Environment):\n")
    for key, where in MANUAL_SECRETS:
        print(f"  {key:<35} ← {where}")
    print("\nRender dashboard: https://dashboard.render.com")
    print("After setting all secrets, trigger a manual deploy to pick them up.")


if __name__ == "__main__":
    main()
