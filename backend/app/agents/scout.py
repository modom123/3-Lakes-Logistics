"""Scout — Prospecting ingest → score → pipeline (Stage 5 step 64).

Scout consumes the outputs of `app.prospecting.*` scrapers, scores each
row, dedupes against `leads`, and writes a stage transition.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from ..prospecting.dedupe import is_duplicate
from ..prospecting.scoring import score_lead


def _insert_lead(row: dict) -> str | None:
    try:
        from ..supabase_client import get_supabase
        res = get_supabase().table("leads").insert(row).execute()
        return (res.data or [{}])[0].get("id")
    except Exception as exc:  # noqa: BLE001
        log_agent("scout", "insert_failed", payload=row, error=str(exc))
        return None


def ingest(records: list[dict]) -> dict[str, Any]:
    added = skipped = 0
    now = datetime.now(timezone.utc).isoformat()
    for r in records:
        if is_duplicate(r):
            skipped += 1
            continue
        score = score_lead(r)
        stage = "new"
        if score >= 80:
            stage = "hot"
        elif score >= 60:
            stage = "warm"
        lead = {
            "source": r.get("source") or "scout",
            "dot_number": r.get("dot_number"),
            "mc_number":  r.get("mc_number"),
            "company_name": r.get("company_name"),
            "contact":    r.get("contact"),
            "phone":      r.get("phone"),
            "email":      r.get("email"),
            "score":      score,
            "stage":      stage,
            "owner_agent": "scout",
            "last_touch_at": now,
        }
        if _insert_lead(lead):
            added += 1
    log_agent("scout", "ingest", result=f"added={added} skipped={skipped}")
    return {"status": "ok", "added": added, "skipped": skipped}


def rescore_pipeline() -> dict[str, Any]:
    """Re-evaluate open leads; promote/demote stage by fresh score."""
    try:
        from ..supabase_client import get_supabase
        rows = (
            get_supabase().table("leads")
            .select("id, dot_number, mc_number, source, score, stage")
            .neq("stage", "won").neq("stage", "lost")
            .limit(5000).execute()
        ).data or []
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    moved = 0
    for lead in rows:
        new_score = score_lead(lead)
        if abs(new_score - (lead.get("score") or 0)) < 5:
            continue
        new_stage = lead.get("stage")
        if new_score >= 80:
            new_stage = "hot"
        elif new_score >= 60:
            new_stage = "warm"
        elif new_score < 30:
            new_stage = "cold"
        try:
            from ..supabase_client import get_supabase
            get_supabase().table("leads").update(
                {"score": new_score, "stage": new_stage}
            ).eq("id", lead["id"]).execute()
            moved += 1
        except Exception as exc:  # noqa: BLE001
            log_agent("scout", "rescore_failed", error=str(exc))
    return {"status": "ok", "moved": moved}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    kind = payload.get("kind") or "ingest"
    if kind == "rescore_pipeline":
        return {"agent": "scout", **rescore_pipeline()}
    recs = payload.get("records") or []
    return {"agent": "scout", **ingest(recs)}
