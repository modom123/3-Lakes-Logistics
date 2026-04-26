"""FastAPI entrypoint — mounts every route group exposed to the
command center (3LakesLogistics_OpsSuite_v5.html) and the public
intake form (index (7).html).

Run locally:
    uvicorn app.main:app --reload --port 8080
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .api import (
    agents_router,
    atomic_ledger_router,
    carriers_router,
    clm_router,
    dashboard_router,
    docs_router,
    loads_router,
    execution_router,
    fleet_router,
    founders_router,
    intake_router,
    leads_router,
    settlement_router,
    telemetry_router,
    webhooks_router,
)
from .logging_service import get_logger
from .settings import get_settings

log = get_logger("3ll.main")

# Global limiter instance — routes that need limiting import this
limiter = Limiter(key_func=get_remote_address)


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="3 Lakes Logistics API",
        version="0.2.0",
        description="AI-automated trucking backend — 19 agents, 1,000 trucks.",
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(intake_router,         prefix="/api/carriers",    tags=["intake"])
    app.include_router(carriers_router,       prefix="/api/carriers",    tags=["carriers"])
    app.include_router(fleet_router,          prefix="/api/fleet",       tags=["fleet"])
    app.include_router(telemetry_router,      prefix="/api/telemetry",   tags=["telemetry"])
    app.include_router(leads_router,          prefix="/api/leads",       tags=["leads"])
    app.include_router(dashboard_router,      prefix="/api/dashboard",   tags=["dashboard"])
    app.include_router(founders_router,       prefix="/api/founders",    tags=["founders"])
    app.include_router(agents_router,         prefix="/api/agents",      tags=["agents"])
    app.include_router(webhooks_router,       prefix="/api/webhooks",    tags=["webhooks"])
    app.include_router(clm_router,            prefix="/api/clm",         tags=["clm"])
    app.include_router(execution_router,      prefix="/api/execution",   tags=["execution"])
    app.include_router(atomic_ledger_router,  prefix="/api/ledger",      tags=["ledger"])
    app.include_router(docs_router,           prefix="/api/docs",        tags=["docs"])
    app.include_router(loads_router,          prefix="/api/loads",       tags=["loads"])
    app.include_router(settlement_router,     prefix="/api/settlement",  tags=["settlement"])

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        """Health check — pings Supabase to confirm DB connectivity."""
        db_ok = False
        db_error = None
        try:
            from .supabase_client import get_supabase
            get_supabase().table("active_carriers").select("id").limit(1).execute()
            db_ok = True
        except Exception as exc:  # noqa: BLE001
            db_error = str(exc)
        return {
            "ok": db_ok,
            "env": s.env,
            "version": "0.2.0",
            "db": "connected" if db_ok else f"error: {db_error}",
        }

    log.info("3 Lakes Logistics API ready (env=%s)", s.env)
    return app


app = create_app()
