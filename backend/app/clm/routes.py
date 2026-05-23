"""CLM REST endpoints — contract scanning, CRUD, milestones, and GL triggers.

New endpoints added for execution engine steps 121-150:
  GET  /api/clm/summary                — dashboard KPI summary (counts, revenue, confidence)
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
  POST /api/clm/{id}/complete          — mark CLM workflow complete (step 150)
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

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
    step_144_analytics_update,
    step_148_contract_export,
    step_149_compliance_audit,
    step_150_clm_complete,
)

router = APIRouter()
log = get_logger("3ll.clm.routes")


# ── Dashboard summary (gap 1) ─────────────────────────────────────────────────

@router.get("/summary")
def get_summary(_: str = Depends(require_bearer)) -> dict:
    """Single-call CLM dashboard snapshot: counts, revenue, avg confidence, recent activity."""
    sb = get_supabase()

    contracts = sb.table("contracts").select(
        "id,status,confidence_score,rate_total,revenue_recognized,created_at"
    ).order("created_at", desc=True).limit(500).execute().data or []

    total = len(contracts)
    active = sum(1 for c in contracts if c.get("status") == "active")
    executed = sum(1 for c in contracts if c.get("status") == "executed")
    flagged = sum(1 for c in contracts if c.get("status") == "draft")
    archived = sum(1 for c in contracts if c.get("status") == "archived")

    confs = [float(c["confidence_score"]) for c in contracts if c.get("confidence_score") is not None]
    avg_confidence = round(sum(confs) / len(confs) * 100, 1) if confs else None

    revenue_recognized = sum(
        float(c.get("rate_total") or 0) for c in contracts if c.get("revenue_recognized")
    )
    revenue_pending = sum(
        float(c.get("rate_total") or 0)
        for c in contracts
        if not c.get("revenue_recognized") and c.get("status") in ("active", "executed")
    )

    recent = [
        {
            "id": c["id"],
            "status": c.get("status"),
            "created_at": c.get("created_at"),
        }
        for c in contracts[:5]
    ]

    open_disputes = sb.table("clm_disputes").select("id").in_("status", ["open", "escalated"]).execute().data or []

    return {
        "total": total,
        "active": active,
        "executed": executed,
        "flagged": flagged,
        "archived": archived,
        "avg_confidence_pct": avg_confidence,
        "revenue_recognized": round(revenue_recognized, 2),
        "revenue_pending": round(revenue_pending, 2),
        "open_disputes": len(open_disputes),
        "recent": recent,
    }


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

    # Gap 4: auto-refresh analytics after every scan so dashboard stays current
    try:
        step_144_analytics_update(None, None, {})
    except Exception:
        pass

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
    result = trigger_invoice(contract_id)
    # Gap 4: keep analytics current after every revenue recognition event
    try:
        step_144_analytics_update(None, None, {})
    except Exception:
        pass
    return result


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
    search: str | None = None,
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
    if search:
        q = q.ilike("filename", f"%{search}%")
    return q.order("uploaded_at", desc=True).limit(500).execute().data


def _signed_url(storage_path: str, bucket: str = "documents", expires: int = 3600) -> str | None:
    """Generate a Supabase Storage signed URL. Returns None on any error."""
    try:
        result = get_supabase().storage.from_(bucket).create_signed_url(storage_path, expires)
        return result.get("signedURL") or result.get("signed_url")
    except Exception:
        try:
            result = get_supabase().storage.from_("driver-documents").create_signed_url(storage_path, expires)
            return result.get("signedURL") or result.get("signed_url")
        except Exception:
            return None


@router.get("/vault/{doc_id}")
def get_vault_doc(doc_id: str, _: str = Depends(require_bearer)) -> dict:
    """Single document record with a fresh signed URL."""
    sb = get_supabase()
    res = sb.table("document_vault").select("*").eq("id", doc_id).limit(1).execute()
    if not res.data:
        raise HTTPException(404, "Document not found")
    doc = res.data[0]
    bucket = doc.get("bucket") or "documents"
    doc["signed_url"] = _signed_url(doc["storage_path"], bucket)
    # Fetch send history
    sends = sb.table("vault_sends").select("sent_to,subject,sent_at").eq("document_id", doc_id).order("sent_at", desc=True).limit(10).execute()
    doc["send_history"] = sends.data or []
    return {"ok": True, "doc": doc}


@router.get("/vault/{doc_id}/url")
def vault_doc_url(doc_id: str, expires: int = 3600, _: str = Depends(require_bearer)) -> dict:
    """Generate a fresh signed URL for viewing or downloading a vault document."""
    sb = get_supabase()
    res = sb.table("document_vault").select("id,filename,storage_path,bucket,doc_type").eq("id", doc_id).limit(1).execute()
    if not res.data:
        raise HTTPException(404, "Document not found")
    doc = res.data[0]
    bucket = doc.get("bucket") or "documents"
    url = _signed_url(doc["storage_path"], bucket, expires=min(expires, 86400))
    if not url:
        raise HTTPException(502, f"Could not generate signed URL for {doc['filename']} — check Supabase Storage bucket '{bucket}'")
    return {"ok": True, "doc_id": doc_id, "filename": doc["filename"], "url": url, "expires_in": expires}


@router.post("/vault/upload")
async def upload_vault_doc(
    file: UploadFile = File(...),
    doc_type: str = Form("other"),
    carrier_id: str = Form(None),
    load_number: str = Form(None),
    notes: str = Form(None),
    _: str = Depends(require_bearer),
) -> dict:
    """Upload a document to the vault from Eagle Eye. Stores in Supabase Storage bucket 'documents'."""
    from ..settings import get_settings
    s = get_settings()
    sb = get_supabase()

    content = await file.read()
    size_kb = len(content) // 1024
    safe_name = file.filename or "upload.pdf"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    storage_path = f"vault/{doc_type}/{ts}_{safe_name}"

    # Upload to Supabase Storage
    try:
        sb.storage.from_("documents").upload(
            path=storage_path,
            file=content,
            file_options={"content-type": file.content_type or "application/octet-stream"},
        )
    except Exception as e:
        raise HTTPException(502, f"Storage upload failed: {e}")

    # Insert vault metadata record
    row = {
        "doc_type":     doc_type,
        "filename":     safe_name,
        "storage_path": storage_path,
        "bucket":       "documents",
        "file_size_kb": size_kb,
        "mime_type":    file.content_type or "application/octet-stream",
        "scan_status":  "complete",
        "notes":        notes,
    }
    if carrier_id:
        row["carrier_id"] = carrier_id
    if load_number:
        row["load_number"] = load_number

    result = sb.table("document_vault").insert(row).execute()
    doc_id = result.data[0]["id"] if result.data else None
    signed = _signed_url(storage_path, "documents")

    # Auto-scan scannable doc types in the background
    _SCANNABLE = {"rate_con", "rate_confirmation", "bol", "pod", "broker_agreement", "agreement"}
    if doc_id and doc_type in _SCANNABLE:
        from ..triggers import fire_vault_scan
        fire_vault_scan(doc_id)

    return {"ok": True, "doc_id": doc_id, "filename": safe_name, "size_kb": size_kb, "url": signed, "scan_queued": doc_type in _SCANNABLE}


class _SendPayload:
    pass

@router.post("/vault/{doc_id}/send")
async def send_vault_doc(doc_id: str, body: dict, _: str = Depends(require_bearer)) -> dict:
    """Email a vault document link to a recipient via Postmark.
    Body: {to: str, subject: str, message: str}
    """
    from ..settings import get_settings
    import httpx

    to_email   = body.get("to", "").strip()
    subject    = body.get("subject", "Document from 3 Lakes Logistics")
    message    = body.get("message", "Please find the attached document via the link below.")
    expires    = 604800  # 7-day link

    if not to_email:
        raise HTTPException(400, "Recipient email (to) is required")

    sb = get_supabase()
    res = sb.table("document_vault").select("*").eq("id", doc_id).limit(1).execute()
    if not res.data:
        raise HTTPException(404, "Document not found")
    doc = res.data[0]

    bucket = doc.get("bucket") or "documents"
    url = _signed_url(doc["storage_path"], bucket, expires=expires)
    if not url:
        raise HTTPException(502, "Could not generate signed URL — check Supabase Storage configuration")

    s = get_settings()
    doc_label = {
        "pod": "Proof of Delivery", "bol": "Bill of Lading", "rate_con": "Rate Confirmation",
        "invoice": "Invoice", "compliance": "Compliance Document", "agreement": "Carrier Agreement",
    }.get(doc.get("doc_type", ""), "Document")

    html_body = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
  <div style="background:#001f3f;padding:20px;text-align:center">
    <h2 style="color:#FFD700;margin:0">3 Lakes Logistics</h2>
    <p style="color:#aaa;margin:6px 0 0;font-size:13px">Document Vault</p>
  </div>
  <div style="padding:24px;background:#f9f9f9">
    <p style="margin-top:0">{message}</p>
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
      <tr><td style="padding:8px;color:#555;font-size:13px;border-bottom:1px solid #eee"><strong>Document</strong></td><td style="padding:8px;font-size:13px;border-bottom:1px solid #eee">{doc.get('filename','—')}</td></tr>
      <tr><td style="padding:8px;color:#555;font-size:13px;border-bottom:1px solid #eee"><strong>Type</strong></td><td style="padding:8px;font-size:13px;border-bottom:1px solid #eee">{doc_label}</td></tr>
      <tr><td style="padding:8px;color:#555;font-size:13px"><strong>Link expires</strong></td><td style="padding:8px;font-size:13px">7 days</td></tr>
    </table>
    <div style="text-align:center;margin:24px 0">
      <a href="{url}" style="background:#001f3f;color:#FFD700;padding:14px 32px;text-decoration:none;border-radius:6px;font-weight:bold;font-size:15px">View {doc_label}</a>
    </div>
    <p style="font-size:11px;color:#999;text-align:center">This link expires in 7 days. Sent by 3 Lakes Logistics operations team.</p>
  </div>
</div>"""

    sent = False
    if s.postmark_server_token:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.postmarkapp.com/email",
                headers={"X-Postmark-Server-Token": s.postmark_server_token, "Content-Type": "application/json"},
                json={"From": s.postmark_from_email, "To": to_email, "Subject": subject,
                      "HtmlBody": html_body, "MessageStream": "outbound", "Tag": "vault-send"},
                timeout=15,
            )
        sent = resp.status_code == 200

    # Update vault record
    old_count = int(doc.get("sent_count") or 0)
    sb.table("document_vault").update({
        "sent_count":   old_count + 1,
        "last_sent_at": datetime.now(timezone.utc).isoformat(),
        "last_sent_to": to_email,
    }).eq("id", doc_id).execute()

    # Log to vault_sends
    sb.table("vault_sends").insert({
        "document_id": doc_id,
        "sent_to":     to_email,
        "subject":     subject,
        "message":     message,
    }).execute()

    return {
        "ok": True,
        "sent": sent,
        "to": to_email,
        "doc_id": doc_id,
        "note": "Email sent via Postmark" if sent else "Postmark not configured — send logged only",
        "signed_url": url,
    }


@router.patch("/vault/{doc_id}")
def update_vault_doc(doc_id: str, body: dict, _: str = Depends(require_bearer)) -> dict:
    """Update notes, doc_type, or load_number on a vault document."""
    allowed = {k: v for k, v in body.items() if k in ("notes", "doc_type", "load_number", "carrier_id")}
    if not allowed:
        raise HTTPException(400, "Nothing to update — allowed fields: notes, doc_type, load_number, carrier_id")
    get_supabase().table("document_vault").update(allowed).eq("id", doc_id).execute()
    return {"ok": True, "doc_id": doc_id, "updated": allowed}


@router.post("/vault/{doc_id}/scan")
def scan_vault_doc(doc_id: str, _: str = Depends(require_bearer)) -> dict:
    """Extract structured data from a vault document using Claude AI.

    Chooses PDF text extraction (PyPDF2) for digital PDFs, or Claude Vision
    for scanned PDFs and images. Results stored in document_vault.extracted_data.
    """
    from .doc_extractor import extract_vault_doc
    result = extract_vault_doc(doc_id)
    if "error" in result:
        raise HTTPException(422, result["error"])
    return result


@router.delete("/vault/{doc_id}")
def delete_vault_doc(doc_id: str, _: str = Depends(require_bearer)) -> dict:
    """Delete a document record and attempt storage cleanup."""
    sb = get_supabase()
    res = sb.table("document_vault").select("id,filename,storage_path,bucket").eq("id", doc_id).limit(1).execute()
    if not res.data:
        raise HTTPException(404, "Document not found")
    doc = res.data[0]
    bucket = doc.get("bucket") or "documents"
    storage_deleted = False
    try:
        sb.storage.from_(bucket).remove([doc["storage_path"]])
        storage_deleted = True
    except Exception:
        pass
    sb.table("document_vault").delete().eq("id", doc_id).execute()
    return {"ok": True, "doc_id": doc_id, "filename": doc["filename"], "storage_deleted": storage_deleted}


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


# ── CLM complete (gap 3) ──────────────────────────────────────────────────────

@router.post("/{contract_id}/complete", status_code=200)
def clm_complete(contract_id: UUID, _: str = Depends(require_bearer)):
    """Mark CLM workflow complete — writes terminal atomic ledger event (step 150)."""
    result = step_150_clm_complete(None, contract_id, {})
    if not result.get("complete"):
        raise HTTPException(400, result.get("reason", "Could not complete CLM workflow"))
    # Refresh analytics so the dashboard reflects the newly executed contract
    try:
        step_144_analytics_update(None, None, {})
    except Exception:
        pass
    log.info("CLM workflow complete contract=%s status=%s", contract_id, result.get("final_status"))
    return result
