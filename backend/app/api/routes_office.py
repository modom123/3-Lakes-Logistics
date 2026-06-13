"""Office collaboration store — shared TODOs and contacts for the executive offices.

A small key/value (jsonb) store backing the Mark Odom / CC Gulley office task
lists and "My Contacts" so they persist server-side and are shared across users
and devices instead of living only in each browser's localStorage.

Keys in use:
  mo_todos   — shared executive TODO list
  oc_mark    — Mark Odom's contacts
  oc_cece    — CC Gulley's contacts

Endpoints degrade gracefully: if the office_state table isn't present yet, they
return ok=False and the frontend transparently falls back to localStorage.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..logging_service import get_logger
from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])
log = get_logger("3ll.api.office")


def _ok_key(key: str) -> bool:
    return key in ("mo_todos", "cc_todos") or key.startswith("oc_")


@router.get("/state/{key}")
def get_state(key: str) -> dict:
    """Return the stored value for a key (an array). ok=False if unavailable."""
    if not _ok_key(key):
        raise HTTPException(400, "invalid key")
    try:
        res = (
            get_supabase()
            .table("office_state")
            .select("value")
            .eq("key", key)
            .limit(1)
            .execute()
        )
        value = res.data[0]["value"] if res.data else []
        return {"ok": True, "key": key, "value": value}
    except Exception as exc:  # noqa: BLE001 — table may not exist yet
        log.warning("office_state get failed key=%s: %s", key, exc)
        return {"ok": False, "key": key, "value": None}


@router.put("/state/{key}")
def put_state(key: str, body: dict) -> dict:
    """Upsert the value (array/object) for a key."""
    if not _ok_key(key):
        raise HTTPException(400, "invalid key")
    value = body.get("value")
    try:
        get_supabase().table("office_state").upsert(
            {"key": key, "value": value, "updated_at": "now()"},
            on_conflict="key",
        ).execute()
        return {"ok": True, "key": key}
    except Exception as exc:  # noqa: BLE001
        log.warning("office_state put failed key=%s: %s", key, exc)
        return {"ok": False, "key": key, "error": str(exc)}
