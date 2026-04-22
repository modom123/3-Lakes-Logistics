"""Structured logging + agent decision audit (step 16).

log_agent() writes to Supabase `agent_log` so every AI action is
auditable. Falls back to stdout if Supabase is unavailable.
"""
from __future__ import annotations

import logging
import sys
from typing import Any

from .settings import get_settings

_configured = False


def get_logger(name: str) -> logging.Logger:
    global _configured
    if not _configured:
        logging.basicConfig(
            level=get_settings().log_level,
            format="%(asctime)s %(levelname)s %(name)s - %(message)s",
            stream=sys.stdout,
        )
        _configured = True
    return logging.getLogger(name)


def log_agent(
    agent: str,
    action: str,
    *,
    carrier_id: str | None = None,
    payload: dict[str, Any] | None = None,
    result: str | None = None,
    error: str | None = None,
) -> None:
    """Write a row to agent_log. Never raises — logging must not crash business logic."""
    log = get_logger(f"agent.{agent}")
    if error:
        log.error("%s %s %s", action, result or "", error)
    else:
        log.info("%s %s", action, result or "")

    try:
        from .supabase_client import get_supabase

        get_supabase().table("agent_log").insert(
            {
                "agent": agent,
                "action": action,
                "carrier_id": carrier_id,
                "payload": payload,
                "result": result,
                "error": error,
            }
        ).execute()
    except Exception as e:  # noqa: BLE001
        log.warning("agent_log write failed: %s", e)
