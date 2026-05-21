"""Carrier Brain API — per-carrier relationship intelligence.

GET  /api/carriers/brain                      — all carriers with any brain data
GET  /api/carriers/brain/at-risk              — carriers with risk_profile memory
GET  /api/carriers/{carrier_id}/brain         — full intelligence for one carrier
GET  /api/carriers/{carrier_id}/brain/{type}  — specific memory type for a carrier
POST /api/carriers/{carrier_id}/brain/note    — Commander adds a manual relationship note
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..agents import carrier_brain as cb
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


@router.get("/carriers/brain")
def all_carrier_brain(limit: int = 50) -> dict:
    """All carriers that have any brain data, grouped by carrier."""
    try:
        from ..supabase_client import get_supabase
        res = (
            get_supabase().table("carrier_brain")
            .select("carrier_id,carrier_name,memory_type,confidence,summary,last_agent,updated_at")
            .order("updated_at", desc=True)
            .limit(limit * 5)
            .execute()
        )
        rows = res.data or []
        # Group by carrier
        by_carrier: dict[str, dict] = {}
        for r in rows:
            cid = r["carrier_id"]
            if cid not in by_carrier:
                by_carrier[cid] = {"carrier_id": cid, "carrier_name": r.get("carrier_name"), "memories": []}
            by_carrier[cid]["memories"].append(r)
        carriers = list(by_carrier.values())[:limit]
        return {"ok": True, "carrier_count": len(carriers), "carriers": carriers}
    except Exception as e:
        raise HTTPException(502, f"Carrier Brain unavailable: {e}")


@router.get("/carriers/brain/at-risk")
def at_risk_carriers(limit: int = 25) -> dict:
    """Carriers flagged at-risk by Winston, sorted by priority."""
    carriers = cb.get_at_risk_carriers(limit=limit)
    return {"ok": True, "count": len(carriers), "at_risk": carriers}


@router.get("/carriers/{carrier_id}/brain")
def carrier_intelligence(carrier_id: str) -> dict:
    """Full Carrier Brain profile — all memory types for one carrier."""
    intel = cb.get_carrier_intelligence(carrier_id)
    return {"ok": True, **intel}


@router.get("/carriers/{carrier_id}/brain/{memory_type}")
def carrier_memory_type(carrier_id: str, memory_type: str) -> dict:
    """Specific memory type for one carrier."""
    mem = cb.recall_carrier(carrier_id, memory_type)
    if not mem:
        raise HTTPException(404, f"No {memory_type} memory for carrier {carrier_id}")
    return {"ok": True, **mem}


class NotePayload(BaseModel):
    note: str
    summary: str | None = None


@router.post("/carriers/{carrier_id}/brain/note")
def add_carrier_note(carrier_id: str, body: NotePayload) -> dict:
    """Commander or dispatcher adds a manual relationship note to a carrier's brain."""
    cb.remember_carrier(
        carrier_id, None, "relationship",
        {"note": body.note, "added_by": "commander"},
        agent="commander",
        confidence=0.9,
        summary=body.summary or body.note[:80],
    )
    return {"ok": True, "carrier_id": carrier_id, "note_saved": True}
