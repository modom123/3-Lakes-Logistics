"""CLM REST endpoints — contract scanning, CRUD, milestones, and GL triggers.

New endpoints added for execution engine steps 121-150:
  POST /api/clm/email-inbound          — SendGrid inbound webhook parse
  POST /api/clm/rate-benchmark         — rate vs. market comparison
  GET  /api/clm/blacklist              — list bad-pay brokers
  POST /api/clm/blacklist              — add broker to blacklist
  GET  /api/clm/brokers/{mc}/scorecard — broker reliability scorecard
  GET  /api/clm/disputes               — list disputes
  POST /api/clm/disputes               — open new dispute
  PATCH /api/clm/disputes/{id}/escalate — escalate dispute
  PATCH /api/clm/disputes/{id}/resolve  — resolve dispute
  GET  /api/clm/analytics              — CLM KPI analytics
  GET  /api/clm/{id}/export            — export contract package
  POST /api/clm/{id}/archive           — archive executed contract
  POST /api/clm/{id}/compliance-audit  — run compliance audit
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..api.deps import require_bearer
from ..supabase_client import get_supabase
from ..logging_service import get_logger
from .models import (
    BrokerBlacklistEntry,
    BrokerBlacklistOut,
    BrokerScorecardOut,
    CLMAnalyticsOut,
    ContractExportOut,
    ContractMilestoneUpdate,
    ContractScanRequest,
    ContractScanResponse,
    DisputeCreate,
    DisputeOut,
    DisputeResolve,
    ExtractedContractVars,
    RateBenchmarkRequest,
    RateBenchmarkResult,
)
from .scanner import scan_contract
from .engine import post_contract_event, trigger_invoice, update_milestone
from .steps import (
    step_121_email_inbound_parse,
    step_130_rate_benchmark,
    step_143_archive_executed,
    step_148_contract_export,
    step_149_compliance_audit,
)

router = APIRouter()
log = get_logger("3ll.clm.routes")


# ── Contract scan & CRUD ─────────────────────────────────────────────────────

@router.post("/scan", response_model=ContractScanResponse, status_code=201)
def scan_and_create(req: ContractScanRequest, _: str = Depends(require_bearer)):
    """Scan a document with Claude AI, extract variables, persist contract record."""
    extracted, confidence, warnings = scan_contract(req.raw_text, req.contract_type)

    sb = get_supabase()
    insert_data: dict = {
        "contract_type": req.contract_type,
        "raw_text": req.raw_text,
        "extracted_vars": extracted,
        "status": "active",
        "confidence_score": confidence,
        "counterparty_name": extracted.get("broker_name") or extracted.get("shipper_name"),
        "rate_total": extracted.get("rate_total"),
        "rate_per_mile": extracted.get("rate_per_mile"),
        "origin_city": extracted.get("origin_city"),
        "destination_city": extracted.get("destination_city"),
        "pickup_date": extracted.get("pickup_date"),
        "delivery_date": extracted.get("delivery_date"),
        "payment_terms": extracted.get("payment_terms"),
        "load_number": extracted.get("load_number"),
    }
    if req.carrier_id:
        insert_data["carrier_id"] = str(req.carrier_id)

    result = sb.table("contracts").insert(insert_data).execute()
    contract = result.data[0]
    contract_id = UUID(contract["id"])

    fields_extracted = len([v for v in extracted.values() if v is not None])

    post_contract_event(contract_id, "scanned", "clm.scanner", {
        "confidence": confidence,
        "fields_extracted": fields_extracted,
        "warnings": warnings,
    })

    sb.table("atomic_ledger").insert({
        "event_type": "contract.scanned",
        "event_source": "clm.scanner",
        "logistics_payload": {
            "contract_id": str(contract_id),
            "contract_type": req.contract_type,
            "origin": extracted.get("origin_city"),
            "destination": extracted.get("destination_city"),
        },
        "financial_payload": {
            "rate_total": extracted.get("rate_total"),
            "rate_per_mile": extracted.get("rate_per_mile"),
            "payment_terms": extracted.get("payment_terms"),
        },
        "compliance_payload": {"confidence_score": confidence, "warnings": warnings},
    }).execute()

    log.info("contract scanned id=%s type=%s confidence=%.2f", contract_id, req.contract_type, confidence)

    extra = extracted.pop("extra", {}) if isinstance(extracted.get("extra"), dict) else {}
    safe_vars = {k: v for k, v in extracted.items() if k in ExtractedContractVars.model_fields}
    return ContractScanResponse(
        contract_id=contract_id,
        extracted_vars=ExtractedContractVars(**safe_vars, extra=extra),
        confidence_score=confidence,
        fields_extracted=fields_extracted,
        warnings=warnings,
    )


@router.get("/")
def list_contracts(
    status: str | None = None,
    contract_type: str | None = None,
    carrier_id: str | None = None,
    flagged: bool | None = None,
    _: str = Depends(require_bearer),
):
    sb = get_supabase()
    q = sb.table("contracts").select(
        "id,carrier_id,contract_type,status,counterparty_name,"
        "rate_total,origin_city,destination_city,pickup_date,"
        "delivery_date,payment_terms,milestone_pct,gl_posted,"
        "auto_approved,flagged_for_review,load_number,created_at"
    )
    if status:
        q = q.eq("status", status)
    if contract_type:
        q = q.eq("contract_type", contract_type)
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    if flagged is not None:
        q = q.eq("flagged_for_review", flagged)
    return q.order("created_at", desc=True).limit(200).execute().data


@router.get("/{contract_id}")
def get_contract(contract_id: UUID, _: str = Depends(require_bearer)):
    sb = get_supabase()
    result = sb.table("contracts").select("*").eq("id", str(contract_id)).single().execute()
    if not result.data:
        raise HTTPException(404, "Contract not found")
    return result.data


@router.patch("/{contract_id}/milestone")
def set_milestone(
    contract_id: UUID,
    body: ContractMilestoneUpdate,
    _: str = Depends(require_bearer),
):
    return update_milestone(contract_id, body.milestone_pct, body.notes)


@router.post("/{contract_id}/invoice")
def recognize_revenue(contract_id: UUID, _: str = Depends(require_bearer)):
    return trigger_invoice(contract_id)


@router.get("/{contract_id}/events")
def get_events(contract_id: UUID, _: str = Depends(require_bearer)):
    sb = get_supabase()
    return (
        sb.table("contract_events")
        .select("*")
        .eq("contract_id", str(contract_id))
        .order("created_at")
        .execute()
        .data
    )


@router.get("/vault/docs")
def list_vault(
    carrier_id: str | None = None,
    doc_type: str | None = None,
    scan_status: str | None = None,
    _: str = Depends(require_bearer),
):
    sb = get_supabase()
    q = sb.table("document_vault").select("*")
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    if doc_type:
        q = q.eq("doc_type", doc_type)
    if scan_status:
        q = q.eq("scan_status", scan_status)
    return q.order("uploaded_at", desc=True).limit(500).execute().data


# ── Email inbound (step 121) ─────────────────────────────────────────────────

@router.post("/email-inbound", status_code=202)
def email_inbound_webhook(
    body: dict,
    _: str = Depends(require_bearer),
):
    """Parse a SendGrid inbound email payload for contract attachments.

    Maps to execution engine step 121 (clm.email_inbound_parse).
    Expected body: {message_id, from_address, subject, attachments, carrier_id?, contract_id?}
    """
    carrier_id = UUID(body["carrier_id"]) if body.get("carrier_id") else None
    contract_id = UUID(body["contract_id"]) if body.get("contract_id") else None
    result = step_121_email_inbound_parse(carrier_id, contract_id, body)
    log.info("email-inbound: message_id=%s attachments=%d", body.get("message_id"), result.get("attachment_count", 0))
    return result


# ── Rate benchmark (step 130) ────────────────────────────────────────────────

@router.post("/rate-benchmark", response_model=RateBenchmarkResult)
def rate_benchmark(req: RateBenchmarkRequest, _: str = Depends(require_bearer)):
    """Compare a submitted rate/mi against internal and national benchmarks.

    Maps to execution engine step 130 (clm.rate_benchmark).
    """
    result = step_130_rate_benchmark(None, None, req.model_dump())
    if "error" in result or result.get("assessment") == "unknown":
        raise HTTPException(400, result.get("note", "Unable to benchmark rate"))
    return RateBenchmarkResult(**{
        k: result[k] for k in RateBenchmarkResult.model_fields if k in result
    })


# ── Broker blacklist ──────────────────────────────────────────────────────────

@router.get("/blacklist", response_model=list[BrokerBlacklistOut])
def list_blacklist(_: str = Depends(require_bearer)):
    sb = get_supabase()
    return sb.table("broker_blacklist").select("*").order("added_at", desc=True).execute().data


@router.post("/blacklist", response_model=BrokerBlacklistOut, status_code=201)
def add_to_blacklist(entry: BrokerBlacklistEntry, _: str = Depends(require_bearer)):
    sb = get_supabase()
    existing = sb.table("broker_blacklist").select("id").eq("broker_mc", entry.broker_mc).limit(1).execute().data
    if existing:
        raise HTTPException(409, f"Broker MC {entry.broker_mc} is already blacklisted")
    res = sb.table("broker_blacklist").insert(entry.model_dump()).execute()
    log.info("broker blacklisted mc=%s reason=%s", entry.broker_mc, entry.reason)
    return res.data[0]


@router.delete("/blacklist/{broker_mc}", status_code=204)
def remove_from_blacklist(broker_mc: str, _: str = Depends(require_bearer)):
    sb = get_supabase()
    sb.table("broker_blacklist").delete().eq("broker_mc", broker_mc).execute()
    log.info("broker removed from blacklist mc=%s", broker_mc)


# ── Broker scorecard ──────────────────────────────────────────────────────────

@router.get("/brokers/{broker_mc}/scorecard", response_model=BrokerScorecardOut)
def get_scorecard(broker_mc: str, _: str = Depends(require_bearer)):
    sb = get_supabase()
    res = sb.table("broker_scorecards").select("*").eq("broker_mc", broker_mc).single().execute()
    if not res.data:
        raise HTTPException(404, f"No scorecard found for broker MC {broker_mc}")
    return res.data


@router.get("/brokers", response_model=list[BrokerScorecardOut])
def list_scorecards(
    tier: str | None = None,
    limit: int = 100,
    _: str = Depends(require_bearer),
):
    sb = get_supabase()
    q = sb.table("broker_scorecards").select("*")
    if tier:
        q = q.eq("volume_discount_tier", tier)
    return q.order("total_loads", desc=True).limit(min(limit, 500)).execute().data


# ── Disputes ──────────────────────────────────────────────────────────────────

@router.get("/disputes", response_model=list[DisputeOut])
def list_disputes(
    status: str | None = None,
    carrier_id: str | None = None,
    contract_id: str | None = None,
    limit: int = 100,
    _: str = Depends(require_bearer),
):
    sb = get_supabase()
    q = sb.table("clm_disputes").select("*")
    if status:
        q = q.eq("status", status)
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    if contract_id:
        q = q.eq("contract_id", contract_id)
    return q.order("opened_at", desc=True).limit(min(limit, 500)).execute().data


@router.post("/disputes", response_model=DisputeOut, status_code=201)
def open_dispute(body: DisputeCreate, _: str = Depends(require_bearer)):
    """Open a new dispute record (maps to step 141 clm.dispute_open)."""
    from .steps import step_141_dispute_open
    result = step_141_dispute_open(
        body.carrier_id,
        body.contract_id,
        body.model_dump(),
    )
    if not result.get("dispute_opened"):
        raise HTTPException(400, result.get("reason", "Could not open dispute"))
    sb = get_supabase()
    res = sb.table("clm_disputes").select("*").eq("id", result["dispute_id"]).single().execute()
    return res.data


@router.patch("/disputes/{dispute_id}/escalate", status_code=200)
def escalate_dispute(dispute_id: str, _: str = Depends(require_bearer)):
    """Manually escalate a specific open dispute."""
    sb = get_supabase()
    dispute = sb.table("clm_disputes").select("*").eq("id", dispute_id).single().execute().data
    if not dispute:
        raise HTTPException(404, "Dispute not found")
    if dispute["status"] != "open":
        raise HTTPException(409, f"Dispute is already '{dispute['status']}'")
    sb.table("clm_disputes").update({
        "status": "escalated",
        "escalated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", dispute_id).execute()
    cid = UUID(dispute["contract_id"])
    post_contract_event(cid, "dispute_escalated", "clm.routes", {"dispute_id": dispute_id, "manual": True})
    return {"escalated": True, "dispute_id": dispute_id}


@router.patch("/disputes/{dispute_id}/resolve", status_code=200)
def resolve_dispute(dispute_id: str, body: DisputeResolve, _: str = Depends(require_bearer)):
    """Mark a dispute as resolved with resolution notes."""
    sb = get_supabase()
    dispute = sb.table("clm_disputes").select("*").eq("id", dispute_id).single().execute().data
    if not dispute:
        raise HTTPException(404, "Dispute not found")
    update: dict = {
        "status": "resolved",
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "resolution_notes": body.resolution_notes,
    }
    if body.paid_amount is not None:
        update["paid_amount"] = body.paid_amount
    sb.table("clm_disputes").update(update).eq("id", dispute_id).execute()
    cid = UUID(dispute["contract_id"])
    post_contract_event(cid, "dispute_resolved", "clm.routes", {
        "dispute_id": dispute_id,
        "resolution_notes": body.resolution_notes,
    })
    # Clear contract disputed status if no more open disputes
    remaining = sb.table("clm_disputes").select("id").eq(
        "contract_id", dispute["contract_id"]
    ).in_("status", ["open", "escalated"]).execute().data
    if not remaining:
        sb.table("contracts").update({"status": "active"}).eq(
            "id", dispute["contract_id"]
        ).execute()
    return {"resolved": True, "dispute_id": dispute_id}


# ── CLM Analytics ─────────────────────────────────────────────────────────────

@router.get("/analytics", response_model=list[CLMAnalyticsOut])
def get_analytics(
    limit: int = 30,
    _: str = Depends(require_bearer),
):
    """Return daily CLM analytics snapshots (most recent first)."""
    sb = get_supabase()
    return sb.table("clm_analytics").select("*").order("period_date", desc=True).limit(min(limit, 365)).execute().data


@router.post("/analytics/refresh", status_code=202)
def refresh_analytics(_: str = Depends(require_bearer)):
    """Trigger an immediate CLM analytics recompute (step 144)."""
    from .steps import step_144_analytics_update
    result = step_144_analytics_update(None, None, {})
    return result


# ── Contract archive & export ─────────────────────────────────────────────────

@router.post("/{contract_id}/archive", status_code=200)
def archive_contract(contract_id: UUID, _: str = Depends(require_bearer)):
    """Archive a fully executed contract (step 143 clm.archive_executed)."""
    result = step_143_archive_executed(None, contract_id, {})
    if not result.get("archived"):
        raise HTTPException(400, result.get("reason", "Cannot archive contract"))
    return result


@router.get("/{contract_id}/export", response_model=ContractExportOut)
def export_contract(contract_id: UUID, _: str = Depends(require_bearer)):
    """Export full contract package: metadata + events + vault docs (step 148)."""
    result = step_148_contract_export(None, contract_id, {})
    if not result.get("exported"):
        raise HTTPException(400, result.get("reason", "Export failed"))
    pkg = result["package"]
    return ContractExportOut(
        contract_id=UUID(pkg["contract_id"]),
        contract_type=pkg["contract_type"],
        status=pkg["status"],
        counterparty_name=pkg.get("counterparty_name"),
        rate_total=pkg.get("rate_total"),
        origin_city=pkg.get("origin_city"),
        destination_city=pkg.get("destination_city"),
        milestone_pct=pkg.get("milestone_pct", 0),
        extracted_vars=pkg.get("extracted_vars") or {},
        events=pkg.get("events") or [],
        documents=pkg.get("documents") or [],
        exported_at=datetime.fromisoformat(pkg["exported_at"]),
    )


# ── Compliance audit ──────────────────────────────────────────────────────────

@router.post("/{contract_id}/compliance-audit", status_code=200)
def compliance_audit(contract_id: UUID, _: str = Depends(require_bearer)):
    """Run SOD + GAAP compliance audit on a contract (step 149)."""
    result = step_149_compliance_audit(None, contract_id, {})
    return result
