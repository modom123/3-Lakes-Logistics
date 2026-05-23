"""Reagan Cole — CLM Intake & Extraction Manager.

Monitors the document vault for unprocessed or failed scans, drives the
full intake pipeline (steps 121-123), reports extraction throughput and
quality, and ensures no contract hits the floor unseen.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase


# ── helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _post_agent_log(action: str, result: str, payload: dict | None = None) -> None:
    log_agent("reagan_cole", action, payload=payload or {}, result=result)


# ── core work ─────────────────────────────────────────────────────────────────

def audit_vault(limit: int = 100) -> dict[str, Any]:
    """Scan document_vault for stuck/unprocessed docs and re-queue them."""
    sb = get_supabase()

    # Docs pending extraction (uploaded but never scanned)
    pending = (
        sb.table("document_vault")
        .select("id,filename,doc_type,uploaded_at,scan_status")
        .eq("scan_status", "pending")
        .order("uploaded_at", desc=False)
        .limit(limit)
        .execute()
        .data or []
    )

    # Docs that failed extraction
    failed = (
        sb.table("document_vault")
        .select("id,filename,doc_type,uploaded_at,scan_status")
        .eq("scan_status", "failed")
        .order("uploaded_at", desc=False)
        .limit(limit)
        .execute()
        .data or []
    )

    requeued = 0
    requeue_ids: list[str] = []

    for doc in pending + failed:
        doc_type = doc.get("doc_type", "other")
        scannable = {
            "rate_confirmation", "rate_con", "bol", "pod",
            "broker_agreement", "broker_carrier_agreement",
            "master_service_agreement", "invoice", "other",
        }
        if doc_type not in scannable:
            continue
        try:
            from ..triggers import fire_vault_scan  # noqa: PLC0415
            fire_vault_scan(doc["id"])
            requeue_ids.append(doc["id"])
            requeued += 1
        except Exception:  # noqa: BLE001
            pass

    return {
        "pending_found": len(pending),
        "failed_found": len(failed),
        "requeued": requeued,
        "requeue_ids": requeue_ids[:20],
    }


def extraction_metrics() -> dict[str, Any]:
    """Compute extraction quality metrics across all scanned contracts."""
    sb = get_supabase()

    contracts = (
        sb.table("contracts")
        .select("id,contract_type,confidence_score,flagged_for_review,auto_approved,created_at")
        .order("created_at", desc=True)
        .limit(500)
        .execute()
        .data or []
    )

    total = len(contracts)
    if total == 0:
        return {"total_contracts": 0, "note": "No contracts in database yet"}

    scores = [float(c["confidence_score"]) for c in contracts if c.get("confidence_score")]
    avg_conf = round(sum(scores) / len(scores), 3) if scores else 0.0
    high_conf = sum(1 for s in scores if s >= 0.90)
    low_conf  = sum(1 for s in scores if s < 0.60)
    flagged   = sum(1 for c in contracts if c.get("flagged_for_review"))
    approved  = sum(1 for c in contracts if c.get("auto_approved"))

    # Doc type breakdown
    type_counts: dict[str, int] = {}
    for c in contracts:
        t = c.get("contract_type") or "unknown"
        type_counts[t] = type_counts.get(t, 0) + 1

    return {
        "total_contracts": total,
        "avg_confidence": avg_conf,
        "high_confidence_count": high_conf,
        "low_confidence_count": low_conf,
        "flagged_for_review": flagged,
        "auto_approved": approved,
        "approval_rate_pct": round(approved / total * 100, 1) if total else 0.0,
        "flag_rate_pct": round(flagged / total * 100, 1) if total else 0.0,
        "by_type": type_counts,
    }


def pipeline_health() -> dict[str, Any]:
    """Check vault scan backlog depth and recent extraction volume."""
    sb = get_supabase()

    unextracted = (
        sb.table("document_vault")
        .select("id", count="exact")
        .is_("extracted_at", "null")
        .neq("doc_type", "folder")
        .execute()
    )
    backlog = unextracted.count or 0

    recent_vault = (
        sb.table("document_vault")
        .select("id,scan_status,doc_type,uploaded_at")
        .order("uploaded_at", desc=True)
        .limit(50)
        .execute()
        .data or []
    )

    by_status: dict[str, int] = {}
    for d in recent_vault:
        s = d.get("scan_status") or "unknown"
        by_status[s] = by_status.get(s, 0) + 1

    return {
        "extraction_backlog": backlog,
        "recent_docs": len(recent_vault),
        "status_breakdown": by_status,
        "backlog_critical": backlog > 20,
    }


# ── main entry point ──────────────────────────────────────────────────────────

def run(payload: dict[str, Any]) -> dict[str, Any]:
    """Daily CLM intake sweep: audit vault → compute metrics → report health."""
    vault_result = audit_vault(limit=int(payload.get("limit", 100)))
    metrics      = extraction_metrics()
    health       = pipeline_health()

    action_required = (
        vault_result["requeued"] > 0
        or health["backlog_critical"]
        or metrics.get("low_confidence_count", 0) > 5
    )

    summary = (
        f"backlog={health['extraction_backlog']} "
        f"requeued={vault_result['requeued']} "
        f"avg_conf={metrics.get('avg_confidence', 0):.0%} "
        f"flagged={metrics.get('flagged_for_review', 0)}"
    )

    _post_agent_log("clm_intake_sweep", summary, payload={
        "vault": vault_result,
        "metrics": metrics,
        "health": health,
    })

    return {
        "agent": "reagan_cole",
        "role": "CLM Intake & Extraction Manager",
        "vault_audit": vault_result,
        "extraction_metrics": metrics,
        "pipeline_health": health,
        "action_required": action_required,
        "summary": summary,
        "ran_at": _now(),
    }
