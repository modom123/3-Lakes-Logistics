"""Central trigger module — fires execution-engine domains in response to real events.

All `fire_*` functions are safe to call from any route handler.  They spawn a
daemon thread so they never block the HTTP response.

Trigger map
───────────
  carrier intake submitted  →  fire_onboarding(carrier_id)
  load status → Booked      →  fire_dispatch(carrier_id, load_id)
  load status → En Route    →  fire_transit(carrier_id, load_id)
  load status → Delivered   →  fire_settlement(carrier_id, load_id)
  daily 06:00 UTC cron      →  fire_compliance_sweep()
"""
from __future__ import annotations

import threading
from typing import Any
from uuid import UUID

from .execution_engine.executor import run_domain, run_step
from .logging_service import get_logger

log = get_logger("3ll.triggers")


# ── internal helper ───────────────────────────────────────────────────────────

def _bg(fn, *args, **kwargs) -> None:
    """Run `fn(*args, **kwargs)` in a daemon thread — fire and forget."""
    t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
    t.start()


def _run_domain_safe(domain: str, carrier_id=None, contract_id=None, context: str = "") -> None:
    try:
        log.info("trigger domain=%s carrier=%s ctx=%s", domain, carrier_id, context)
        results = run_domain(domain, carrier_id, contract_id)
        ok = sum(1 for r in results if r.get("status") == "complete")
        fail = sum(1 for r in results if r.get("status") == "failed")
        log.info("trigger domain=%s done ok=%d fail=%d ctx=%s", domain, ok, fail, context)
    except Exception as exc:  # noqa: BLE001
        log.error("trigger domain=%s raised: %s ctx=%s", domain, exc, context)


def _run_step_safe(step_number: int, carrier_id=None, contract_id=None,
                   payload: dict | None = None, context: str = "") -> None:
    try:
        log.info("trigger step=%d carrier=%s ctx=%s", step_number, carrier_id, context)
        run_step(step_number, carrier_id, contract_id, payload or {})
    except Exception as exc:  # noqa: BLE001
        log.error("trigger step=%d raised: %s ctx=%s", step_number, exc, context)


# ── public fire_* functions ───────────────────────────────────────────────────

def fire_onboarding(carrier_id: str | UUID) -> None:
    """Trigger when a carrier intake form is submitted and carrier_id is known."""
    _bg(_run_domain_safe, "onboarding", carrier_id, None, f"intake:{carrier_id}")


def fire_dispatch(carrier_id: str | UUID | None, load_id: str,
                  payload: dict | None = None) -> None:
    """Trigger when a load is booked (status → Booked)."""
    _bg(_run_domain_safe, "dispatch", carrier_id, None, f"load_booked:{load_id}")


def fire_transit(carrier_id: str | UUID | None, load_id: str,
                 payload: dict | None = None) -> None:
    """Trigger when a driver confirms pickup (status → En Route)."""
    _bg(_run_domain_safe, "transit", carrier_id, None, f"pickup:{load_id}")


def fire_settlement(carrier_id: str | UUID | None, load_id: str,
                    payload: dict | None = None) -> None:
    """Trigger when a delivery is confirmed (status → Delivered / Completed)."""
    _bg(_run_domain_safe, "settlement", carrier_id, None, f"delivery:{load_id}")


def fire_compliance_sweep() -> None:
    """Trigger daily compliance domain sweep (no specific carrier — all carriers)."""
    _bg(_run_domain_safe, "compliance", None, None, "daily_cron")


def fire_analytics_update() -> None:
    """Trigger analytics domain (runs after settlement or on schedule)."""
    _bg(_run_domain_safe, "analytics", None, None, "analytics_refresh")
