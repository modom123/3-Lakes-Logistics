"""Background worker loop (Stage 5 step 81).

Polls `agent_tasks` via agents.router.claim_next() and dispatches each
claimed task to the matching agent. One process handles N concurrent
tasks up to `queue_max_concurrency`.

Run:
    python -m app.worker
"""
from __future__ import annotations

import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future

from .agents import router as agent_router
from .logging_service import get_logger
from .settings import get_settings

_log = get_logger("3ll.worker")
_stop = threading.Event()


def _run_one(task: dict) -> None:
    agent = task["agent"]
    payload = dict(task.get("payload") or {})
    payload["_task_id"] = task["id"]
    payload["kind"] = task.get("kind")
    try:
        result = agent_router.dispatch(agent, payload)
        agent_router.finalize(task, result, error=None)
    except Exception as exc:  # noqa: BLE001
        _log.exception("task %s crashed", task.get("id"))
        agent_router.finalize(task, {"status": "error"}, error=str(exc))


def main() -> int:
    s = get_settings()
    poll = s.queue_poll_interval_sec
    pool = ThreadPoolExecutor(max_workers=s.queue_max_concurrency)
    _install_signals()
    _log.info("worker ready (concurrency=%s poll=%ss)", s.queue_max_concurrency, poll)
    inflight: set[Future] = set()

    while not _stop.is_set():
        # Harvest completed futures
        for fut in list(inflight):
            if fut.done():
                inflight.discard(fut)
        # Fill up to concurrency
        while len(inflight) < s.queue_max_concurrency and not _stop.is_set():
            task = agent_router.claim_next()
            if not task:
                break
            inflight.add(pool.submit(_run_one, task))
        _stop.wait(poll)

    _log.info("draining %s inflight tasks…", len(inflight))
    for fut in list(inflight):
        try:
            fut.result(timeout=30)
        except Exception:  # noqa: BLE001
            pass
    pool.shutdown(wait=True)
    _log.info("worker stopped cleanly")
    return 0


def _install_signals() -> None:
    def _graceful(_signum, _frame):
        _stop.set()

    signal.signal(signal.SIGTERM, _graceful)
    signal.signal(signal.SIGINT, _graceful)


if __name__ == "__main__":
    sys.exit(main())
