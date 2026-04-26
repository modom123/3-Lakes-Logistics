"""CLM REST endpoints — contract scanning, CRUD, milestones, and GL triggers."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..api.deps import require_bearer
from ..supabase_client import get_supabase
from ..logging_service import get_logger
from .models import (
    ContractMilestoneUpdate,
    ContractScanRequest,
    ContractScanResponse,
    ExtractedContractVars,
)
from .scanner import scan_contract
from .engine import post_contract_event, trigger_invoice, update_milestone

router = APIRouter()
log = get_logger("3ll.clm.routes")


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
        "counterparty_name": extracted.get("broker_name") or extracted.get("shipper_name"),
        "rate_total": extracted.get("rate_total"),
        "rate_per_mile": extracted.get("rate_per_mile"),
        "origin_city": extracted.get("origin_city"),
        "destination_city": extracted.get("destination_city"),
        "pickup_date": extracted.get("pickup_date"),
        "delivery_date": extracted.get("delivery_date"),
        "payment_terms": extracted.get("payment_terms"),
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
    _: str = Depends(require_bearer),
):
    sb = get_supabase()
    q = sb.table("contracts").select(
        "id,carrier_id,contract_type,status,counterparty_name,"
        "rate_total,origin_city,destination_city,pickup_date,"
        "delivery_date,payment_terms,milestone_pct,gl_posted,created_at"
    )
    if status:
        q = q.eq("status", status)
    if contract_type:
        q = q.eq("contract_type", contract_type)
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
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
