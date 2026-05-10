"""FastAPI entrypoint — mounts every route group exposed to the
command center (3LakesLogistics_OpsSuite_v5.html) and the public
intake form (index (7).html).

Run locally:
    uvicorn app.main:app --reload --port 8080
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import (
    agents_router,
    atomic_ledger_router,
    bland_webhooks_router,
    carriers_router,
    clm_router,
    comms_public_router,
    comms_router,
    compliance_router,
    dashboard_router,
    driver_auth_router,
    driver_router,
    email_router,
    email_ingest_router,
    executives_router,
    execution_router,
    notifications_router,
    payout_router,
    fleet_public_router,
    fleet_router,
    founders_router,
    health_router,
    intake_router,
    leads_router,
    prospecting_router,
    telemetry_router,
    triggers_router,
    webhooks_router,
)
from .logging_service import get_logger
from .settings import get_settings

log = get_logger("3ll.main")


# ── APScheduler daily compliance cron ────────────────────────────────────────

def _start_scheduler(app: FastAPI) -> None:
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from .triggers import fire_compliance_sweep, fire_analytics_update

        scheduler = BackgroundScheduler(timezone="UTC")

        # Daily compliance sweep — 06:00 UTC
        scheduler.add_job(
            fire_compliance_sweep,
            CronTrigger(hour=6, minute=0),
            id="compliance_daily",
            replace_existing=True,
        )

        # Analytics refresh — 06:30 UTC (after compliance completes)
        scheduler.add_job(
            fire_analytics_update,
            CronTrigger(hour=6, minute=30),
            id="analytics_daily",
            replace_existing=True,
        )

        scheduler.start()
        app.state.scheduler = scheduler
        log.info("APScheduler started — compliance@06:00 UTC, analytics@06:30 UTC")
    except ImportError:
        log.warning("apscheduler not installed — daily cron disabled. Run: pip install apscheduler")
    except Exception as exc:  # noqa: BLE001
        log.error("APScheduler failed to start: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _start_scheduler(app)
    yield
    # Shutdown scheduler cleanly
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("APScheduler stopped")


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="3 Lakes Logistics API",
        version="0.1.0",
        description="AI-automated trucking backend — 19 agents, 1,000 trucks.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(intake_router,         prefix="/api/carriers",     tags=["intake"])
    app.include_router(carriers_router,       prefix="/api/carriers",     tags=["carriers"])
    app.include_router(fleet_router,          prefix="/api/fleet",        tags=["fleet"])
    app.include_router(fleet_public_router,   prefix="/api/fleet",        tags=["fleet-public"])
    app.include_router(telemetry_router,      prefix="/api/telemetry",    tags=["telemetry"])
    app.include_router(leads_router,          prefix="/api/leads",        tags=["leads"])
    app.include_router(dashboard_router,      prefix="/api/dashboard",    tags=["dashboard"])
    app.include_router(founders_router,       prefix="/api/founders",     tags=["founders"])
    app.include_router(agents_router,         prefix="/api/agents",       tags=["agents"])
    app.include_router(webhooks_router,       prefix="/api/webhooks",     tags=["webhooks"])
    app.include_router(bland_webhooks_router, prefix="/api",              tags=["webhooks"])
    app.include_router(email_ingest_router,   prefix="/api",              tags=["webhooks"])
    app.include_router(prospecting_router,    prefix="/api/prospecting",  tags=["prospecting"])
    app.include_router(triggers_router,       prefix="/api/triggers",     tags=["triggers"])
    app.include_router(clm_router,            prefix="/api/clm",          tags=["clm"])
    app.include_router(execution_router,      prefix="/api/execution",    tags=["execution"])
    app.include_router(atomic_ledger_router,  prefix="/api/ledger",       tags=["ledger"])
    app.include_router(compliance_router,     prefix="/api/compliance",   tags=["compliance"])
    app.include_router(comms_router,          prefix="/api/comms",        tags=["comms"])
    app.include_router(comms_public_router,   prefix="/api/comms",        tags=["comms"])
    app.include_router(driver_auth_router,    prefix="/api",              tags=["driver-auth"])
    app.include_router(driver_router,         prefix="/api",              tags=["driver"])
    app.include_router(payout_router,         prefix="/api",              tags=["payout"])
    app.include_router(notifications_router,  prefix="/api",              tags=["notifications"])
    app.include_router(email_router,          prefix="/api",              tags=["email"])
    app.include_router(executives_router,      prefix="/api",              tags=["executives"])
    app.include_router(health_router,                                     tags=["health"])

    log.info("3 Lakes Logistics API ready (env=%s)", s.env)
    return app


app = create_app()
