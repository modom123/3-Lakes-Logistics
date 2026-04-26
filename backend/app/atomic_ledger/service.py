"""Atomic Ledger service — write and query immutable events."""
from __future__ import annotations

from ..supabase_client import get_supabase
from ..logging_service import get_logger
from .models import AtomicEvent

log = get_logger("3ll.atomic_ledger")


def write_event(event: AtomicEvent) -> dict:
    sb = get_supabase()
    data = event.model_dump(mode="json")
    result = sb.table("atomic_ledger").insert(data).execute()
    log.info("atomic event type=%s source=%s", event.event_type, event.event_source)
    return result.data[0] if result.data else {}


def query_events(
    event_type: str | None = None,
    event_source: str | None = None,
    limit: int = 100,
) -> list[dict]:
    sb = get_supabase()
    q = sb.table("atomic_ledger").select("*")
    if event_type:
        q = q.eq("event_type", event_type)
    if event_source:
        q = q.eq("event_source", event_source)
    return q.order("created_at", desc=True).limit(min(limit, 1000)).execute().data
