"""FastAPI entrypoint — mounts every route group exposed to Eagle Eye.

Run locally:
    uvicorn app.main:app --reload --port 8080
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import (
    agents_router,
    atomic_ledger_router,
    bland_webhooks_router,
    bond_router,
    carriers_router,
    clm_router,
    comms_public_router,
    comms_router,
    compliance_router,
    dashboard_router,
    dat_router,
    fmcsa_router,
    memory_router,
    carrier_brain_router,
    revenue_brain_router,
    mailboxes_router,
    agreements_router,
    driver_auth_router,
    driver_router,
    email_router,
    email_ingest_router,
    executives_router,
    execution_router,
    migration_router,
    adobe_webhooks_router,
    adobe_intake_router,
    notifications_router,
    payout_router,
    fleet_public_router,
    fleet_router,
    founders_router,
    health_router,
    intake_router,
    leads_router,
    prospecting_router,
    rate_con_router,
    customers_router,
    invoices_ar_router,
    settlements_router,
    studio_router,
    telemetry_router,
    triggers_router,
    webhooks_router,
)
from .logging_service import get_logger
from .settings import get_settings

log = get_logger("3ll.main")


def _start_scheduler(app: FastAPI) -> None:
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
        from .triggers import (
            fire_compliance_sweep,
            fire_analytics_update,
            fire_mark_odom,
            fire_cc_gulley,
            fire_alexander,
            fire_victoria,
            fire_naomi,
            fire_winston,
            fire_isabella,
            fire_sofia,
            fire_vance_batch,
            fire_sms_campaign,
            fire_email_campaign,
            fire_social_post,
            fire_follow_up_reminders,
        )
        from .agents.memory import prune_interactions
        from .email.imap_poller import poll_all as poll_all_mailboxes

        scheduler = BackgroundScheduler(timezone="UTC")

        scheduler.add_job(fire_follow_up_reminders, IntervalTrigger(hours=1), id="follow_up_reminders", replace_existing=True)
        scheduler.add_job(poll_all_mailboxes, IntervalTrigger(minutes=2), id="mailbox_poll", replace_existing=True)
        scheduler.add_job(prune_interactions, CronTrigger(hour=5, minute=30), id="memory_prune_daily", replace_existing=True)
        scheduler.add_job(fire_compliance_sweep, CronTrigger(hour=6, minute=0), id="compliance_daily", replace_existing=True)
        scheduler.add_job(fire_analytics_update, CronTrigger(hour=6, minute=30), id="analytics_daily", replace_existing=True)
        scheduler.add_job(fire_alexander, CronTrigger(hour=6, minute=45), id="alexander_daily", replace_existing=True)
        scheduler.add_job(fire_victoria, CronTrigger(hour=7, minute=0), id="victoria_daily", replace_existing=True)
        scheduler.add_job(fire_cc_gulley, CronTrigger(hour=7, minute=5), id="cc_gulley_daily", replace_existing=True)
        scheduler.add_job(fire_naomi, CronTrigger(hour=7, minute=15), id="naomi_daily", replace_existing=True)
        scheduler.add_job(fire_winston, CronTrigger(hour=7, minute=30), id="winston_daily", replace_existing=True)
        scheduler.add_job(fire_isabella, CronTrigger(hour=8, minute=0), id="isabella_daily", replace_existing=True)
        scheduler.add_job(fire_sofia, CronTrigger(hour=8, minute=15), id="sofia_daily", replace_existing=True)
        scheduler.add_job(fire_mark_odom, CronTrigger(hour=8, minute=30), id="mark_odom_daily", replace_existing=True)
        scheduler.add_job(fire_vance_batch, CronTrigger(hour=13, minute=0), id="vance_batch_daily", replace_existing=True)
        scheduler.add_job(fire_sms_campaign, CronTrigger(hour=14, minute=0), id="sms_outreach_daily", replace_existing=True)
        scheduler.add_job(fire_email_campaign, CronTrigger(hour=14, minute=30), id="email_outreach_daily", replace_existing=True)
        scheduler.add_job(fire_social_post, CronTrigger(day_of_week="mon", hour=13, minute=0), id="social_post_weekly", replace_existing=True)

        scheduler.start()
        app.state.scheduler = scheduler
        log.info("APScheduler started")
    except ImportError:
        log.warning("apscheduler not installed — daily cron disabled. Run: pip install apscheduler")
    except Exception as exc:
        log.error("APScheduler failed to start: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _start_scheduler(app)
    yield
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("APScheduler stopped")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="3 Lakes Logistics API",
        version="0.1.0",
        description="AI-automated trucking backend — 30 agents, 1,000 trucks.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(carrier_brain_router,   prefix="/api",              tags=["carrier-brain"])
    app.include_router(revenue_brain_router,   prefix="/api",              tags=["revenue-brain"])
    app.include_router(memory_router,          prefix="/api",              tags=["nexus"])
    app.include_router(intake_router,          prefix="/api/carriers",     tags=["intake"])
    app.include_router(carriers_router,        prefix="/api/carriers",     tags=["carriers"])
    app.include_router(fleet_router,           prefix="/api/fleet",        tags=["fleet"])
    app.include_router(fleet_public_router,    prefix="/api/fleet",        tags=["fleet-public"])
    app.include_router(telemetry_router,       prefix="/api/telemetry",    tags=["telemetry"])
    app.include_router(leads_router,           prefix="/api/leads",        tags=["leads"])
    app.include_router(fmcsa_router,           prefix="/api/fmcsa",        tags=["fmcsa"])
    app.include_router(dat_router,             prefix="/api/loads",        tags=["loads"])
    app.include_router(dashboard_router,       prefix="/api/dashboard",    tags=["dashboard"])
    app.include_router(founders_router,        prefix="/api/founders",     tags=["founders"])
    app.include_router(agents_router,          prefix="/api/agents",       tags=["agents"])
    app.include_router(bond_router,            prefix="/api/bond",         tags=["bond"])
    app.include_router(webhooks_router,        prefix="/api/webhooks",     tags=["webhooks"])
    app.include_router(bland_webhooks_router,  prefix="/api",              tags=["webhooks"])
    app.include_router(email_ingest_router,    prefix="/api",              tags=["webhooks"])
    app.include_router(prospecting_router,     prefix="/api/prospecting",  tags=["prospecting"])
    app.include_router(triggers_router,        prefix="/api/triggers",     tags=["triggers"])
    app.include_router(clm_router,             prefix="/api/clm",          tags=["clm"])
    app.include_router(execution_router,       prefix="/api/execution",    tags=["execution"])
    app.include_router(atomic_ledger_router,   prefix="/api/ledger",       tags=["ledger"])
    app.include_router(compliance_router,      prefix="/api/compliance",   tags=["compliance"])
    app.include_router(comms_router,           prefix="/api/comms",        tags=["comms"])
    app.include_router(comms_public_router,    prefix="/api/comms",        tags=["comms"])
    app.include_router(driver_auth_router,     prefix="/api",              tags=["driver-auth"])
    app.include_router(driver_router,          prefix="/api",              tags=["driver"])
    app.include_router(payout_router,          prefix="/api",              tags=["payout"])
    app.include_router(notifications_router,   prefix="/api",              tags=["notifications"])
    app.include_router(email_router,           prefix="/api",              tags=["email"])
    app.include_router(executives_router,      prefix="/api",              tags=["executives"])
    app.include_router(migration_router,       prefix="/api",              tags=["migration"])
    app.include_router(adobe_webhooks_router,  prefix="/api",              tags=["adobe"])
    app.include_router(adobe_intake_router,    prefix="/api",              tags=["adobe"])
    app.include_router(mailboxes_router,       prefix="/api",              tags=["mailboxes"])
    app.include_router(agreements_router,      prefix="/api/agreements",   tags=["agreements"])
    app.include_router(rate_con_router,        prefix="/api",              tags=["rate-con"])
    app.include_router(customers_router,       prefix="/api",              tags=["customers"])
    app.include_router(invoices_ar_router,     prefix="/api",              tags=["invoices-ar"])
    app.include_router(settlements_router,    prefix="/api",              tags=["settlements"])
    app.include_router(studio_router,          prefix="/api",              tags=["studio"])
    app.include_router(health_router,                                      tags=["health"])

    _marketing_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "marketing")
    )
    if os.path.isdir(_marketing_dir):
        app.mount("/marketing", StaticFiles(directory=_marketing_dir), name="marketing")

    log.info("3 Lakes Logistics API ready (env=%s)", s.env)
    return app


app = create_app()
