"""Scheduled jobs (Stage 5 step 82).

Uses APScheduler BackgroundScheduler to push work into agent_tasks on
fixed cadences. Start with `start_scheduler()` inside main.py's lifespan
or run standalone with `python -m app.scheduler`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .agents import router as agent_router
from .logging_service import get_logger

_log = get_logger("3ll.scheduler")

# name → (cron, agent, kind, payload)
JOBS: list[tuple[str, str, str, str, dict]] = [
    ("fmcsa_sync_nightly",      "0 3 * * *",  "shield", "fmcsa_sync",      {}),
    ("coi_expiry_scan",         "0 8 * * *",  "shield", "coi_expiry_scan", {}),
    ("clearinghouse_scan",      "0 4 * * *",  "shield", "clearinghouse",   {}),
    ("nurture_cadence_hourly",  "0 * * * *",  "signal", "run_cadence",     {}),
    ("daily_digest",            "0 7 * * *",  "pulse",  "daily_digest",    {}),
    ("settlement_weekly",       "0 18 * * 5", "settler","weekly_run",      {}),
    ("pipeline_scoring_hourly", "15 * * * *", "scout",  "rescore_pipeline",{}),
    ("load_match_every_15",     "*/15 * * * *","sonny", "match_all_trucks",{}),
    ("kpi_snapshot",            "*/5 * * * *","pulse",  "kpi_snapshot",    {}),
    ("retention_purge",         "0 2 * * *",  "audit",  "retention_purge", {}),
]


def _enqueue(agent: str, kind: str, payload: dict, name: str) -> None:
    task_id = agent_router.enqueue(agent, kind, payload)
    _mark_heartbeat(name, "queued" if task_id else "offline")


def _mark_heartbeat(name: str, status: str, error: str | None = None) -> None:
    try:
        from .supabase_client import get_supabase
        get_supabase().table("scheduled_jobs").upsert({
            "name": name,
            "cron": next((c for (n, c, *_rest) in JOBS if n == name), ""),
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "last_status": status,
            "last_error": error,
        }).execute()
    except Exception as exc:  # noqa: BLE001
        _log.warning("scheduled_jobs upsert failed: %s", exc)


def build_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="UTC")
    for name, cron, agent, kind, payload in JOBS:
        sched.add_job(
            _enqueue, CronTrigger.from_crontab(cron),
            args=[agent, kind, payload, name],
            id=name, name=name, replace_existing=True, max_instances=1,
        )
    return sched


def start_scheduler() -> BackgroundScheduler:
    sched = build_scheduler()
    sched.start()
    _log.info("scheduler started with %s jobs", len(JOBS))
    return sched


if __name__ == "__main__":  # pragma: no cover
    import signal
    import threading

    sched = start_scheduler()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT,  lambda *_: stop.set())
    stop.wait()
    sched.shutdown(wait=True)
