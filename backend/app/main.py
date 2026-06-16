"""FastAPI entrypoint — mounts every route group exposed to Eagle Eye.

Run locally:
    uvicorn app.main:app --reload --port 8080
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
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
    factoring_router,
    light_fleet_router,
    lf_public_router,
    lf_webhooks_router,
    driver_packet_router,
    checkr_webhook_router,
    stripe_identity_webhook_router,
    driver_auth_router,
    driver_router,
    driver_messages_router,
    load_hunter_router,
    email_router,
    email_ingest_router,
    executives_router,
    execution_router,
    migration_router,
    notifications_router,
    payout_router,
    fleet_public_router,
    fleet_router,
    founders_router,
    health_router,
    intake_router,
    leads_router,
    prospecting_router,
    studio_router,
    telemetry_router,
    triggers_router,
    webhooks_router,
    onboarding_status_router,
    cost_tracking_router,
    office_router,
    lf_bizdev_router,
    trading_autopilot_router,
    growth_router,
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
            fire_lf_compliance_sweep,
            fire_lf_nemt_billing_run,
            fire_lf_weekly_payouts,
            fire_lf_recurring_trips,
            fire_scheduled_tasks,
            fire_partial_submission_reminders,
            fire_insurance_expiry_alerts,
            fire_onboarding_bond_audit,
            fire_stall_reminders,
            fire_iebc_budget_check,
            fire_iebc_weekly_report,
            fire_marcus_reid,
            fire_jamie_park,
            fire_lf_bizdev,
            fire_trading_acquisition,
            fire_trading_coverage,
            fire_trading_daily_close,
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
        scheduler.add_job(fire_naomi, CronTrigger(hour=18, minute=0), id="naomi_evening", replace_existing=True)
        scheduler.add_job(fire_vance_batch, CronTrigger(hour=13, minute=0), id="vance_batch_daily", replace_existing=True)
        scheduler.add_job(fire_vance_batch, CronTrigger(hour=17, minute=0), id="vance_batch_evening", replace_existing=True)
        scheduler.add_job(fire_sms_campaign, CronTrigger(hour=14, minute=0), id="sms_outreach_daily", replace_existing=True)
        scheduler.add_job(fire_email_campaign, CronTrigger(hour=14, minute=30), id="email_outreach_daily", replace_existing=True)
        scheduler.add_job(fire_email_campaign, CronTrigger(hour=11, minute=0), id="email_outreach_morning", replace_existing=True)
        scheduler.add_job(fire_social_post, CronTrigger(day_of_week="mon", hour=13, minute=0), id="social_post_weekly", replace_existing=True)
        scheduler.add_job(fire_lf_compliance_sweep, CronTrigger(hour=6, minute=15), id="lf_compliance_daily", replace_existing=True)
        scheduler.add_job(fire_lf_nemt_billing_run, CronTrigger(day_of_week="mon", hour=9, minute=0), id="lf_nemt_billing_weekly", replace_existing=True)
        scheduler.add_job(fire_scheduled_tasks, IntervalTrigger(hours=1), id="scheduled_tasks_executor", replace_existing=True)
        scheduler.add_job(fire_partial_submission_reminders, CronTrigger(hour=9, minute=0), id="partial_submission_reminders", replace_existing=True)
        scheduler.add_job(fire_insurance_expiry_alerts, CronTrigger(hour=6, minute=45), id="insurance_expiry_alerts", replace_existing=True)
        scheduler.add_job(fire_onboarding_bond_audit, CronTrigger(hour=7, minute=45), id="onboarding_bond_audit_daily", replace_existing=True)
        scheduler.add_job(fire_stall_reminders, CronTrigger(hour=10, minute=0), id="stall_reminders_daily", replace_existing=True)
        scheduler.add_job(fire_iebc_budget_check, CronTrigger(hour=8, minute=45), id="iebc_budget_check_daily", replace_existing=True)
        scheduler.add_job(fire_iebc_weekly_report, CronTrigger(day_of_week="mon", hour=9, minute=30), id="iebc_weekly_report", replace_existing=True)
        scheduler.add_job(fire_jamie_park, CronTrigger(hour=7, minute=50), id="jamie_park_daily", replace_existing=True)
        scheduler.add_job(fire_marcus_reid, CronTrigger(day_of_week="fri", hour=6, minute=0), id="marcus_reid_weekly", replace_existing=True)
        scheduler.add_job(fire_lf_weekly_payouts, CronTrigger(day_of_week="fri", hour=17, minute=0), id="lf_weekly_payouts", replace_existing=True)
        scheduler.add_job(fire_lf_recurring_trips, CronTrigger(hour=5, minute=0), id="lf_recurring_trips_daily", replace_existing=True)
        scheduler.add_job(fire_lf_bizdev, CronTrigger(hour=14, minute=45), id="lf_bizdev_daily", replace_existing=True)
        scheduler.add_job(fire_trading_acquisition, IntervalTrigger(hours=2), id="trading_acquisition", replace_existing=True)
        scheduler.add_job(fire_trading_coverage, IntervalTrigger(minutes=30), id="trading_coverage", replace_existing=True)
        scheduler.add_job(fire_trading_daily_close, CronTrigger(hour=21, minute=0), id="trading_daily_close", replace_existing=True)

        def _fire_load_hunt():
            try:
                from .agents.load_hunter import hunt
                result = hunt()
                log.info("Scheduled load hunt: %s loads found (%s HOT)", result.get("total", 0), result.get("hot", 0))
            except Exception as exc:
                log.warning("Scheduled load hunt failed: %s", exc)

        scheduler.add_job(_fire_load_hunt, IntervalTrigger(minutes=3), id="load_hunter_scan", replace_existing=True)

        scheduler.start()
        app.state.scheduler = scheduler
        log.info("APScheduler started")
    except ImportError:
        log.warning("apscheduler not installed — daily cron disabled. Run: pip install apscheduler")
    except Exception as exc:
        log.error("APScheduler failed to start: %s", exc)


def _run_startup_migrations() -> None:
    """Idempotent migrations that run once on every server start."""
    try:
        from .supabase_client import get_supabase
        sb = get_supabase()

        # Migration 020 — deduplicate light_vehicle_drivers by email then phone
        rows = sb.table("light_vehicle_drivers").select("id,email,phone,created_at").execute().data or []
        rows_sorted = sorted(rows, key=lambda r: (r.get("created_at") or "", r.get("id") or ""))
        seen_emails: dict = {}
        seen_phones: dict = {}
        deleted = 0
        for r in rows_sorted:
            rid = str(r.get("id") or "")
            email = (r.get("email") or "").strip().lower()
            phone = (r.get("phone") or "").strip()
            is_dup = False
            if email:
                if email in seen_emails:
                    is_dup = True
                else:
                    seen_emails[email] = rid
            if not is_dup and phone:
                if phone in seen_phones:
                    is_dup = True
                else:
                    seen_phones[phone] = rid
            if is_dup:
                try:
                    sb.table("light_vehicle_drivers").delete().eq("id", rid).execute()
                    deleted += 1
                except Exception:  # noqa: BLE001
                    pass
        if deleted:
            log.info("Migration 020: removed %d duplicate LF driver records", deleted)
    except Exception as e:  # noqa: BLE001
        log.warning("Startup migration error (non-fatal): %s", e)


def _check_sales_credentials() -> None:
    """Log a clear warning for each missing sales/outreach credential at startup."""
    s = get_settings()
    checks = [
        ("BLAND_AI_API_KEY",        bool(s.bland_ai_api_key),        "Vance outbound calls will be disabled"),
        ("POSTMARK_SERVER_TOKEN",    bool(s.postmark_server_token),   "Cold email outreach will be disabled"),
        ("POSTMARK_FROM_EMAIL",      bool(s.postmark_from_email),     "Cold email outreach will be disabled"),
        ("TWILIO_ACCOUNT_SID",       bool(s.twilio_account_sid),      "SMS outreach will be disabled"),
        ("TWILIO_AUTH_TOKEN",        bool(s.twilio_auth_token),       "SMS outreach will be disabled"),
        ("TWILIO_FROM_NUMBER",       bool(s.twilio_from_number),      "SMS outreach will be disabled"),
        ("DOT_API_KEY",              bool(getattr(s, "dot_api_key", None)), "FMCSA census pulls may be rate-limited"),
    ]
    missing = [(name, reason) for name, ok, reason in checks if not ok]
    if missing:
        log.warning("⚠ SALES/MARKETING CREDENTIALS MISSING — %d unconfigured:", len(missing))
        for name, reason in missing:
            log.warning("  • %s not set → %s", name, reason)
    else:
        log.info("✓ All sales/marketing credentials configured")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _run_startup_migrations()
    _check_sales_credentials()
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
    app.include_router(driver_messages_router, prefix="/api/messages",     tags=["driver-messages"])
    app.include_router(load_hunter_router,     prefix="/api/load-hunter",  tags=["load-hunter"])
    app.include_router(payout_router,          prefix="/api",              tags=["payout"])
    app.include_router(notifications_router,   prefix="/api",              tags=["notifications"])
    app.include_router(email_router,           prefix="/api",              tags=["email"])
    app.include_router(executives_router,      prefix="/api",              tags=["executives"])
    app.include_router(migration_router,       prefix="/api",              tags=["migration"])
    app.include_router(mailboxes_router,       prefix="/api",              tags=["mailboxes"])
    app.include_router(agreements_router,      prefix="/api/agreements",   tags=["agreements"])
    app.include_router(factoring_router,       prefix="/api/factoring",    tags=["factoring"])
    app.include_router(light_fleet_router,     prefix="/api/light-fleet",  tags=["light-fleet"])
    app.include_router(lf_public_router,       prefix="/api/light-fleet",  tags=["light-fleet-public"])
    app.include_router(driver_packet_router,   prefix="/api/light-fleet",  tags=["light-fleet"])
    app.include_router(lf_webhooks_router,     prefix="/api",              tags=["lf-webhooks"])
    app.include_router(checkr_webhook_router,          prefix="/api", tags=["checkr-webhook"])
    app.include_router(stripe_identity_webhook_router, prefix="/api", tags=["stripe-identity-webhook"])
    app.include_router(studio_router,          prefix="/api",              tags=["studio"])
    app.include_router(onboarding_status_router, prefix="/api",           tags=["onboarding-status"])
    app.include_router(cost_tracking_router,    prefix="/api/costs",      tags=["cost-tracking"])
    app.include_router(office_router,           prefix="/api/office",     tags=["office"])
    app.include_router(lf_bizdev_router,                                   tags=["lf-bizdev"])
    app.include_router(trading_autopilot_router,                           tags=["trading"])
    app.include_router(growth_router,                                      tags=["growth"])
    app.include_router(health_router,                                      tags=["health"])

    _marketing_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "marketing")
    )
    if os.path.isdir(_marketing_dir):
        app.mount("/marketing", StaticFiles(directory=_marketing_dir), name="marketing")

    @app.get("/google9f88d93f841d8a95.html", include_in_schema=False)
    async def google_site_verification():
        return PlainTextResponse("google-site-verification: google9f88d93f841d8a95.html")

    log.info("3 Lakes Logistics API ready (env=%s)", s.env)
    return app


app = create_app()
