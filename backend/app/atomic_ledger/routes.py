"""Atomic Ledger REST endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..api.deps import require_bearer
from .models import AtomicEvent
from .service import query_events, write_event

router = APIRouter()


@router.post("/events", status_code=201)
def post_event(req: AtomicEvent, _: str = Depends(require_bearer)):
    return write_event(req)


@router.get("/events")
def get_events(
    event_type: str | None = None,
    event_source: str | None = None,
    limit: int = 100,
    _: str = Depends(require_bearer),
):
    return query_events(event_type, event_source, limit)
