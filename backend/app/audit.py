"""Immutable audit log writer (step 75).

Call `record()` wherever a sensitive mutation happens. Failures never
raise — logging must not break business logic — but they are logged.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .logging_service import get_logger

_log = get_logger("3ll.audit")


def record(
    *,
    actor: str,
    action: str,
    entity: str | None = None,
    entity_id: str | None = None,
    carrier_id: str | None = None,
    meta: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    try:
        from .supabase_client import get_supabase
        get_supabase().table("audit_log").insert({
            "actor": actor, "action": action,
            "entity": entity, "entity_id": entity_id,
            "carrier_id": carrier_id, "meta": meta,
            "ip": ip, "user_agent": user_agent,
            "ts": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as exc:  # noqa: BLE001
        _log.warning("audit_log insert failed: %s", exc)
