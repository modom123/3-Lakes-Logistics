"""Health check endpoints — driver app and monitoring systems poll these."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter

from ..circuit_breaker import breakers
from ..logging_service import get_logger
from ..settings import get_settings

log = get_logger(__name__)
router = APIRouter()

START_TIME = time.time()


@router.get("/api/health", tags=["health"])
async def health_basic():
    """Fast ping — driver app checks this every 30s to detect failover."""
    from ..settings import get_settings
    s = get_settings()
    if not s.supabase_url:
        sb_status = "MISSING_URL — set SUPABASE_URL in Render"
    elif s.supabase_service_role_key:
        sb_status = "service_role_key"
    elif s.supabase_anon_key:
        sb_status = "anon_key_only — set SUPABASE_SERVICE_ROLE_KEY to bypass RLS"
    else:
        sb_status = "MISSING_KEY — set SUPABASE_SERVICE_ROLE_KEY in Render"
    return {
        "ok": True,
        "env": s.env,
        "ts": datetime.now(timezone.utc).isoformat(),
        "supabase": sb_status,
    }


@router.get("/api/health/full", tags=["health"])
async def health_full():
    """Full status — checks all services. Used by monitoring dashboards."""
    s = get_settings()
    results = {}

    # ── Supabase ─────────────────────────────────────────────────────────────
    try:
        from ..supabase_client import get_supabase
        sb = get_supabase()
        sb.table("drivers").select("id").limit(1).execute()
        results["supabase"] = "ok"
    except Exception as e:
        results["supabase"] = f"error: {str(e)[:60]}"

    # ── Stripe ───────────────────────────────────────────────────────────────
    try:
        import stripe
        stripe.api_key = s.stripe_secret_key
        if stripe.api_key:
            stripe.Balance.retrieve()
            results["stripe"] = "ok"
        else:
            results["stripe"] = "no_key"
    except Exception as e:
        results["stripe"] = f"error: {str(e)[:60]}"

    # ── Twilio ───────────────────────────────────────────────────────────────
    try:
        if s.twilio_account_sid:
            from twilio.rest import Client
            Client(s.twilio_account_sid, s.twilio_auth_token).api.accounts.list(limit=1)
            results["twilio"] = "ok"
        else:
            results["twilio"] = "no_key"
    except Exception as e:
        results["twilio"] = f"error: {str(e)[:60]}"

    # ── Bland AI ─────────────────────────────────────────────────────────────
    try:
        import httpx
        if s.bland_ai_api_key:
            r = httpx.get(
                "https://api.bland.ai/v1/calls",
                headers={"authorization": s.bland_ai_api_key},
                params={"limit": 1},
                timeout=8,
            )
            results["bland"] = "ok" if r.status_code in (200, 206) else f"http_{r.status_code}"
        else:
            results["bland"] = "no_key"
    except Exception as e:
        results["bland"] = f"error: {str(e)[:60]}"

    # ── Postmark Email ────────────────────────────────────────────────────────
    results["postmark"] = "ok" if s.postmark_server_token else "no_key"

    # ── FMCSA ────────────────────────────────────────────────────────────────
    results["fmcsa"] = "ok" if s.fmcsa_webkey else "no_key"

    # ── ELD / Motive ─────────────────────────────────────────────────────────
    results["eld"] = "ok" if s.motive_api_key else "no_key"

    # ── Anthropic Claude ─────────────────────────────────────────────────────
    results["claude"] = "ok" if s.anthropic_api_key else "no_key"

    # ── Redis / Cache ─────────────────────────────────────────────────────────
    try:
        from ..cache import cache_set, cache_get
        cache_set("health_check", "ok", ttl=10)
        val = cache_get("health_check")
        results["cache"] = "redis_ok" if val == "ok" else "memory_fallback"
    except Exception as e:
        results["cache"] = f"error: {str(e)[:60]}"

    # ── Circuit breakers ──────────────────────────────────────────────────────
    circuit_status = {name: b.status() for name, b in breakers.items()}
    open_circuits  = [name for name, b in breakers.items() if b.state.value == "open"]

    overall_ok = (
        results.get("supabase") == "ok"
        and len(open_circuits) == 0
    )

    return {
        "ok":             overall_ok,
        "env":            s.env,
        "uptime_seconds": int(time.time() - START_TIME),
        "services":       results,
        "circuits":       circuit_status,
        "open_circuits":  open_circuits,
        "ts":             datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/health/circuits", tags=["health"])
async def health_circuits():
    """Circuit breaker status — shows which external services are failing."""
    return {
        "circuits":      {name: b.status() for name, b in breakers.items()},
        "open_circuits": [name for name, b in breakers.items() if b.state.value == "open"],
        "ts":            datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/health/ping", tags=["health"])
async def health_ping():
    """Ultra-fast ping for load balancer health checks (< 5ms)."""
    return "ok"
