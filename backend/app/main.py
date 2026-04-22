"""FastAPI entrypoint.

Run locally:
    uvicorn app.main:app --reload --port 8080
Run the worker:
    python -m app.worker
Run the scheduler:
    python -m app.scheduler
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import (
    agents_router,
    carriers_router,
    dashboard_router,
    fleet_router,
    founders_router,
    intake_router,
    leads_router,
    telemetry_router,
    webhooks_router,
)
from .logging_service import get_logger
from .settings import get_settings

log = get_logger("3ll.main")


def _init_sentry(s) -> None:
    """Step 97 observability — wire Sentry if DSN configured."""
    if not s.sentry_dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        sentry_sdk.init(
            dsn=s.sentry_dsn, environment=s.env,
            traces_sample_rate=0.1, profiles_sample_rate=0.1,
            integrations=[FastApiIntegration()],
        )
        log.info("Sentry initialized env=%s", s.env)
    except Exception as exc:  # noqa: BLE001
        log.warning("sentry init failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    _init_sentry(s)
    sched = None
    if os.getenv("ENABLE_SCHEDULER") == "1":
        from .scheduler import start_scheduler
        sched = start_scheduler()
    yield
    if sched is not None:
        sched.shutdown(wait=False)


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="3 Lakes Logistics API",
        version="1.0.0-stage5",
        description="AI-automated trucking backend — 14 agents, 1,000 trucks.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(intake_router,    prefix="/api/carriers",  tags=["intake"])
    app.include_router(carriers_router,  prefix="/api/carriers",  tags=["carriers"])
    app.include_router(fleet_router,     prefix="/api/fleet",     tags=["fleet"])
    app.include_router(telemetry_router, prefix="/api/telemetry", tags=["telemetry"])
    app.include_router(leads_router,     prefix="/api/leads",     tags=["leads"])
    app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
    app.include_router(founders_router,  prefix="/api/founders",  tags=["founders"])
    app.include_router(agents_router,    prefix="/api/agents",    tags=["agents"])
    app.include_router(webhooks_router,  prefix="/api/webhooks",  tags=["webhooks"])

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {"ok": True, "env": s.env, "version": app.version}

    @app.get("/api/ready", tags=["meta"])
    def ready() -> dict:
        """Readiness probe: confirm Supabase is reachable."""
        try:
            from .supabase_client import get_supabase
            get_supabase().table("active_carriers").select("id").limit(1).execute()
            return {"ready": True}
        except Exception as exc:  # noqa: BLE001
            return {"ready": False, "error": str(exc)}

    log.info("3 Lakes Logistics API ready (env=%s)", s.env)
    return app


app = create_app()
