#!/usr/bin/env python3
"""
UserPromptSubmit hook — detects API keys/secrets in user messages
and upserts them into backend/.env automatically.
"""
import json
import os
import re
import sys
from pathlib import Path

ENV_FILE = Path("/home/user/3-Lakes-Logistics/backend/.env")

# (env_var_name, regex_to_extract_value)
PATTERNS = [
    # Explicit KEY=value or KEY = value anywhere in the message
    (None, r'\b([A-Z][A-Z0-9_]{3,})\s*=\s*([^\s\'"`,;]{8,})'),

    # Bland AI API key  (org_ prefix)
    ("BLAND_AI_API_KEY",    r'\b(org_[a-f0-9]{80,})\b'),
    # Bland AI Org ID (same prefix — user sometimes sends the wrong one)
    ("BLAND_AI_ORG_ID",     r'\b(org_[a-f0-9]{80,})\b'),

    # Stripe secret key
    ("STRIPE_SECRET_KEY",   r'\b(sk_(?:live|test)_[A-Za-z0-9]{24,})\b'),
    # Stripe webhook secret
    ("STRIPE_WEBHOOK_SECRET", r'\b(whsec_[A-Za-z0-9+/=]{32,})\b'),
    # Stripe price ID
    ("STRIPE_PRICE_FOUNDERS", r'\b(price_[A-Za-z0-9]{14,})\b'),

    # Twilio Account SID
    ("TWILIO_ACCOUNT_SID",  r'\b(AC[a-f0-9]{32})\b'),
    # Twilio Auth Token (32-char hex)
    ("TWILIO_AUTH_TOKEN",   r'\b([a-f0-9]{32})\b'),

    # SendGrid API key
    ("SENDGRID_API_KEY",    r'\b(SG\.[A-Za-z0-9_-]{22,}\.[A-Za-z0-9_-]{43,})\b'),

    # Anthropic API key
    ("ANTHROPIC_API_KEY",   r'\b(sk-ant-[A-Za-z0-9_-]{90,})\b'),

    # Bland AI API key (bld_ prefix)
    ("BLAND_AI_API_KEY",    r'\b(bld_[A-Za-z0-9_-]{20,})\b'),

    # Supabase service role / anon key (long JWT)
    ("SUPABASE_SERVICE_ROLE_KEY", r'\b(eyJ[A-Za-z0-9_-]{100,})\b'),
]

# Keys we never want to overwrite blindly (require explicit KEY=value)
PROTECTED = {"SUPABASE_URL", "API_BASE_URL", "DATABASE_URL"}


def load_env(path: Path) -> dict:
    """Parse .env file into an ordered dict."""
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def save_env(path: Path, env: dict, original_lines: list[str]) -> None:
    """Write env dict back, preserving comments and order."""
    # Update existing lines
    updated_keys = set()
    new_lines = []
    for line in original_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.partition("=")[0].strip()
            if k in env:
                new_lines.append(f"{k}={env[k]}")
                updated_keys.add(k)
                continue
        new_lines.append(line)

    # Append new keys
    new_keys = [k for k in env if k not in updated_keys]
    if new_keys:
        new_lines.append("")
        new_lines.append("# Added by Claude Code auto-key hook")
        for k in new_keys:
            new_lines.append(f"{k}={env[k]}")

    path.write_text("\n".join(new_lines) + "\n")


def extract_keys(message: str) -> dict:
    found = {}

    for var_name, pattern in PATTERNS:
        for m in re.finditer(pattern, message, re.IGNORECASE if var_name else 0):
            if var_name is None:
                # Generic KEY=value pattern
                k, v = m.group(1), m.group(2)
                if k not in PROTECTED and len(v) >= 8:
                    found[k] = v
            else:
                if var_name not in PROTECTED:
                    found[var_name] = m.group(1)

    return found


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    message = data.get("user_message", "") or ""
    if not message:
        sys.exit(0)

    found = extract_keys(message)
    if not found:
        sys.exit(0)

    # Load existing .env
    original_lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    env = load_env(ENV_FILE)

    # Only update if value changed
    changed = {}
    for k, v in found.items():
        if env.get(k) != v:
            changed[k] = v
            env[k] = v

    if not changed:
        sys.exit(0)

    # Ensure directory exists
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    save_env(ENV_FILE, env, original_lines)

    # Tell Claude what was saved
    keys_list = "\n".join(f"  • {k}" for k in changed)
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": f"[auto-key hook] Saved to backend/.env:\n{keys_list}"
        }
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
