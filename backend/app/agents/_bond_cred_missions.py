"""Bond credential missions — get_credentials & fetch_supabase_keys.

Imported at bottom of james_bond.py.
"""
from __future__ import annotations

import urllib.request as _req
import urllib.error   as _err
import json           as _j
from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from . import memory as mem

_NAME = "james_bond"


# ── Credential catalogue ─────────────────────────────────────────────────────
# Each entry: (env_attr, display_label, required)
_CRED_CATALOGUE = [
    ("supabase_url",             "Supabase URL",            True),
    ("supabase_anon_key",        "Supabase Anon Key",       True),
    ("supabase_service_role_key","Supabase Service Role",   True),
    ("anthropic_api_key",        "Anthropic API Key",       True),
    ("airtable_api_key",         "Airtable API Key",        False),
    ("render_api_key",           "Render API Key",          False),
    ("postmark_server_token",    "Postmark Token",          False),
    ("openrouter_api_key",       "OpenRouter API Key",      False),
    ("supabase_access_token",    "Supabase Access Token",   False),
    ("vapi_api_key",             "Vapi API Key",            False),
    ("bland_ai_api_key",         "Bland AI Key",            False),
    ("fmcsa_webkey",             "FMCSA Web Key",           False),
    ("dot_api_key",              "DOT API Key",             False),
    ("stripe_secret_key",        "Stripe Secret Key",       False),
]

_VAULT_AGENT = "bond_vault"


def _vault_get(key: str) -> str | None:
    row = mem.recall(_VAULT_AGENT, key)
    if row:
        v = row.get("memory_value")
        if isinstance(v, dict):
            return v.get("value") or None
        if isinstance(v, str) and v:
            return v
    return None


def _vault_set(key: str, value: str) -> None:
    mem.remember(
        _VAULT_AGENT, key,
        {"value": value, "updated": datetime.now(timezone.utc).isoformat()},
        confidence=1.0, source_agent=_NAME,
        summary=f"Bond vault: {key} stored",
    )


def mission_get_credentials(payload: dict) -> dict:
    """Audit every credential; auto-save vault entries; validate Supabase."""
    from ..settings import get_settings
    from ..supabase_client import get_supabase

    s = get_settings()
    results: list[dict] = []
    missing_required: list[str] = []

    for attr, label, required in _CRED_CATALOGUE:
        env_val = getattr(s, attr, "") or ""
        vault_val = _vault_get(attr.upper())

        if env_val:
            status = "set"
            source = "env"
            # Auto-populate vault if not already there
            if not vault_val:
                try:
                    _vault_set(attr.upper(), env_val)
                except Exception:
                    pass
        elif vault_val:
            status = "vault"
            source = "bond_vault"
        else:
            status = "missing"
            source = None
            if required:
                missing_required.append(label)

        results.append({
            "key":      attr.upper(),
            "label":    label,
            "status":   status,
            "source":   source,
            "required": required,
            # Mask value: show last 4 chars only
            "hint":     (env_val or vault_val or "")[-4:] or None,
        })

    # Quick Supabase health check
    sb_ok = False
    try:
        get_supabase().table("agent_memory").select("id").limit(1).execute()
        sb_ok = True
    except Exception:
        pass

    # Quick Airtable validation if key is available
    at_status = None
    at_key = s.airtable_api_key or _vault_get("AIRTABLE_API_KEY")
    if at_key:
        try:
            r = _req.Request(
                "https://api.airtable.com/v0/meta/whoami",
                headers={"Authorization": f"Bearer {at_key}"}
            )
            with _req.urlopen(r, timeout=8) as resp:
                at_status = "valid" if resp.status == 200 else "invalid"
        except _err.HTTPError as e:
            at_status = "invalid" if e.code in (401, 403) else "unreachable"
        except Exception:
            at_status = "unreachable"

    set_count = sum(1 for r in results if r["status"] in ("set", "vault"))

    # Log actionable blockers for each missing optional credential
    _CRED_ACTIONS = {
        "airtable_api_key":      ("airtable_leads",  "AIRTABLE_API_KEY missing — Bond cannot import leads from Airtable",
                                   "Paste key in Lead Pipeline → Bond card, or store via Bond Office → Credential Vault."),
        "render_api_key":        ("set_render_env",   "RENDER_API_KEY missing — Bond cannot auto-persist env vars to Render",
                                   "Add RENDER_API_KEY in Render Dashboard → Your Service → Environment."),
        "anthropic_api_key":     ("clm_scanner",      "ANTHROPIC_API_KEY missing — CLM contract scanner offline",
                                   "Add ANTHROPIC_API_KEY in Render Dashboard → Environment."),
        "openrouter_api_key":    ("outside_bond",     "OPENROUTER_API_KEY missing — Outside Bond reasoning offline",
                                   "Add OPENROUTER_API_KEY in Render Dashboard → Environment."),
        "postmark_server_token": ("email_delivery",   "POSTMARK_SERVER_TOKEN missing — carrier onboarding emails offline",
                                   "Add POSTMARK_SERVER_TOKEN in Render Dashboard → Environment."),
        "vapi_api_key":          ("vance_calls",      "VAPI_API_KEY missing — Vance voice calling offline",
                                   "Add VAPI_API_KEY in Render Dashboard → Environment."),
        "bland_ai_api_key":      ("vance_outbound",   "BLAND_AI_API_KEY missing — Vance outbound calls offline",
                                   "Add BLAND_AI_API_KEY in Render Dashboard → Environment."),
    }
    try:
        from . import james_bond as _jb
        for r in results:
            attr = r["key"].lower()
            if r["status"] == "missing" and attr in _CRED_ACTIONS:
                mission_tag, msg, action = _CRED_ACTIONS[attr]
                _jb._log_action("blocked", mission_tag, msg, action_required=action)
        # Log overall credential health as info
        _jb._log_action(
            "info", "get_credentials",
            f"Credential audit: {set_count}/{len(results)} set"
            + (f" · {len(missing_required)} required missing" if missing_required else " · all required present"),
            resolved=True,
        )
    except Exception:
        pass

    log_agent(
        _NAME, "get_credentials",
        payload={},
        result=f"checked={len(results)} set={set_count} missing_required={len(missing_required)}",
    )

    return {
        "agent":            _NAME,
        "mission":          "get_credentials",
        "status":           "OK" if not missing_required else "WARN",
        "credentials":      results,
        "supabase_healthy": sb_ok,
        "airtable_key_status": at_status,
        "set_count":        set_count,
        "missing_required": missing_required,
        "vault_backed":     [r["key"] for r in results if r["status"] == "vault"],
        "timestamp":        datetime.now(timezone.utc).isoformat(),
    }


def mission_fetch_supabase_keys(payload: dict) -> dict:
    """Pull Supabase anon key + service role from Supabase Management API.

    Requires SUPABASE_ACCESS_TOKEN (personal access token from
    https://supabase.com/dashboard/account/tokens) in payload or env.
    Derives project ref from SUPABASE_URL automatically.
    """
    from ..settings import get_settings
    s = get_settings()

    access_token = (
        payload.get("supabase_access_token")
        or s.supabase_access_token
        or _vault_get("SUPABASE_ACCESS_TOKEN")
    )
    if not access_token:
        try:
            from . import james_bond as _jb
            _jb._log_action(
                "blocked", "fetch_supabase_keys",
                "Cannot fetch Supabase keys — SUPABASE_ACCESS_TOKEN not set",
                action_required="Get a personal access token at supabase.com/dashboard/account/tokens, then paste it in Bond Office → Credential Vault → Fetch Supabase Keys.",
            )
        except Exception:
            pass
        return {
            "agent":   _NAME,
            "mission": "fetch_supabase_keys",
            "status":  "BLOCKED",
            "reason":  "SUPABASE_ACCESS_TOKEN not set. Get one at supabase.com/dashboard/account/tokens, then pass in payload or set in Render.",
        }

    # Extract project ref from SUPABASE_URL (https://<ref>.supabase.co)
    project_ref = payload.get("project_ref")
    if not project_ref and s.supabase_url:
        host = s.supabase_url.replace("https://", "").split(".")[0]
        if host:
            project_ref = host

    if not project_ref:
        return {
            "agent":   _NAME,
            "mission": "fetch_supabase_keys",
            "status":  "BLOCKED",
            "reason":  "Cannot determine project ref. Set SUPABASE_URL or pass project_ref in payload.",
        }

    hdr = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    try:
        url = f"https://api.supabase.com/v1/projects/{project_ref}/api-keys"
        req = _req.Request(url, headers=hdr)
        with _req.urlopen(req, timeout=15) as resp:
            keys_raw = _j.loads(resp.read())
    except _err.HTTPError as e:
        return {
            "agent":   _NAME,
            "mission": "fetch_supabase_keys",
            "status":  "ERROR",
            "reason":  f"Supabase Management API {e.code}: {e.read()[:200].decode()}",
        }
    except Exception as exc:
        return {
            "agent":   _NAME,
            "mission": "fetch_supabase_keys",
            "status":  "ERROR",
            "reason":  str(exc)[:200],
        }

    # keys_raw is a list: [{name, api_key}, ...]
    fetched: dict[str, str] = {}
    for k in (keys_raw if isinstance(keys_raw, list) else []):
        name = k.get("name", "")
        val  = k.get("api_key") or k.get("apiKey") or ""
        if name == "anon" and val:
            fetched["SUPABASE_ANON_KEY"] = val
        elif name in ("service_role", "service-role") and val:
            fetched["SUPABASE_SERVICE_ROLE_KEY"] = val

    if not fetched:
        return {
            "agent":   _NAME,
            "mission": "fetch_supabase_keys",
            "status":  "ERROR",
            "reason":  f"No keys returned from Supabase Management API. Response: {str(keys_raw)[:300]}",
        }

    # Also get project URL to confirm
    try:
        purl = f"https://api.supabase.com/v1/projects/{project_ref}"
        preq = _req.Request(purl, headers=hdr)
        with _req.urlopen(preq, timeout=10) as pr:
            proj = _j.loads(pr.read())
        api_url = f"https://{project_ref}.supabase.co"
        fetched["SUPABASE_URL"] = api_url
    except Exception:
        pass

    # Save everything to vault
    for k, v in fetched.items():
        try:
            _vault_set(k, v)
        except Exception:
            pass

    # Also save access token to vault for future use
    if payload.get("supabase_access_token"):
        try:
            _vault_set("SUPABASE_ACCESS_TOKEN", access_token)
        except Exception:
            pass

    # Try to set in Render too (fire-and-forget via Bond's set_render_env)
    render_set: list[str] = []
    if s.render_api_key:
        try:
            from . import james_bond as _jb
            result = _jb._mission_set_render_env({
                "vars": fetched, "deploy": False
            })
            if result.get("status") == "SUCCESS":
                render_set = list(fetched.keys())
        except Exception:
            pass

    log_agent(
        _NAME, "fetch_supabase_keys",
        payload={"project_ref": project_ref},
        result=f"fetched={list(fetched.keys())} render_set={render_set}",
    )

    try:
        from . import james_bond as _jb
        _jb._log_action(
            "success", "fetch_supabase_keys",
            f"Fetched Supabase keys: {', '.join(fetched.keys())}"
            + (f" · also set in Render" if render_set else ""),
            resolved=True,
        )
    except Exception:
        pass
    return {
        "agent":        _NAME,
        "mission":      "fetch_supabase_keys",
        "status":       "SUCCESS",
        "project_ref":  project_ref,
        "keys_fetched": list(fetched.keys()),
        "vault_saved":  list(fetched.keys()),
        "render_set":   render_set,
        "directive":    (
            f"BOND DIRECTIVE: Supabase keys fetched and saved to vault. "
            + (f"Also set in Render: {render_set}. " if render_set else "Set RENDER_API_KEY to auto-persist to Render. ")
            + "Run get_credentials to verify full credential health."
        ),
    }
