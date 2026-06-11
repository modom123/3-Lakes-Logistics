"""CRM contacts — server persistence for the executive-office "My CRM" tab.

Each office keeps its own contact book keyed by `owner` ('mark' for Mark
Odom's office, 'cece' for CC Gulley's). Contacts carry a pipeline stage,
priority, deal value, and a JSON activity timeline. The Eagle Eye frontend
mirrors these into localStorage as a synchronous cache and offline fallback.

Requires table `crm_contacts` (see backend/sql/022_crm_contacts.sql).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])

# Columns the frontend may set (kept name-for-name with the localStorage shape).
_FIELDS = (
    "name", "company", "phone", "email", "type", "priority",
    "pipeline_stage", "linkedin", "notes", "source_lead_id",
)


def _num(v):
    """Coerce a deal value ('', '5000', 5000) to float or None."""
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_client(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "owner": row.get("owner") or "mark",
        "name": row.get("name") or "",
        "company": row.get("company") or "",
        "phone": row.get("phone") or "",
        "email": row.get("email") or "",
        "type": row.get("type") or "",
        "priority": row.get("priority") or "none",
        "pipeline_stage": row.get("pipeline_stage") or "",
        "deal_value": row.get("deal_value") if row.get("deal_value") is not None else "",
        "linkedin": row.get("linkedin") or "",
        "last_contacted": row.get("last_contacted"),
        "notes": row.get("notes") or "",
        "activities": row.get("activities") or [],
        "source_lead_id": row.get("source_lead_id") or "",
        "created": row.get("created_at"),
    }


def _from_client(body: dict) -> dict:
    out: dict = {}
    for f in _FIELDS:
        if f in body:
            out[f] = (body.get(f) or None) if f != "name" else (body.get("name") or "").strip()
    if "deal_value" in body:
        out["deal_value"] = _num(body.get("deal_value"))
    if "last_contacted" in body:
        out["last_contacted"] = body.get("last_contacted") or None
    if "activities" in body and isinstance(body.get("activities"), list):
        out["activities"] = body.get("activities")
    if "owner" in body:
        out["owner"] = (body.get("owner") or "mark").strip()
    return out


@router.get("/contacts")
def list_contacts(owner: str = "mark", limit: int = 1000) -> dict:
    sb = get_supabase()
    try:
        res = (
            sb.table("crm_contacts").select("*")
            .eq("owner", owner)
            .order("name")
            .limit(limit)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Database error loading contacts: {exc}") from exc
    return {"items": [_to_client(r) for r in (res.data or [])]}


@router.post("/contacts")
def create_contact(body: dict) -> dict:
    data = _from_client(body)
    if not data.get("name"):
        raise HTTPException(400, "name is required")
    data.setdefault("owner", "mark")
    data.setdefault("activities", [])
    try:
        res = get_supabase().table("crm_contacts").insert(data).execute()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Database error creating contact: {exc}") from exc
    return {"ok": True, "contact": _to_client((res.data or [{}])[0])}


@router.patch("/contacts/{contact_id}")
def update_contact(contact_id: str, body: dict) -> dict:
    data = _from_client(body)
    if not data:
        raise HTTPException(400, "no updatable fields supplied")
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        res = (
            get_supabase().table("crm_contacts").update(data)
            .eq("id", contact_id).execute()
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Database error updating contact: {exc}") from exc
    if not (res.data or []):
        raise HTTPException(404, "contact not found")
    return {"ok": True, "contact": _to_client(res.data[0])}


@router.delete("/contacts/{contact_id}")
def delete_contact(contact_id: str) -> dict:
    try:
        get_supabase().table("crm_contacts").delete().eq("id", contact_id).execute()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Database error deleting contact: {exc}") from exc
    return {"ok": True}
