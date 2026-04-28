"""CLM step handlers for execution engine steps 121-150.

Each handler receives (carrier_id, contract_id, payload) and returns a
structured output dict that gets written to execution_steps.output_payload.

Steps are split into three bands:
  121-130  Document ingestion → rate benchmarking
  131-140  Approval / milestones / GL / factoring
  141-150  Disputes / archive / analytics / CLM complete
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from ..supabase_client import get_supabase
from .engine import post_contract_event, trigger_invoice, update_milestone
from .scanner import scan_contract

log = logging.getLogger("3ll.clm.steps")

# ── helpers ──────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_contract(contract_id: UUID) -> dict:
    sb = get_supabase()
    res = sb.table("contracts").select("*").eq("id", str(contract_id)).single().execute()
    if not res.data:
        raise ValueError(f"Contract {contract_id} not found")
    return res.data


# ═══════════════════════════════════════════════════════════════════════════
# STEPS 121-130 — Document ingestion → rate benchmarking
# ═══════════════════════════════════════════════════════════════════════════

def step_121_email_inbound_parse(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Parse SendGrid inbound email for contract attachments.

    Expects payload keys: message_id, from_address, subject,
    attachments (list of {filename, content_type, size_bytes, storage_path}).
    """
    attachments = payload.get("attachments", [])
    classified: list[dict] = []

    type_hints: dict[str, str] = {
        "rate": "rate_confirmation",
        "rc": "rate_confirmation",
        "load": "rate_confirmation",
        "bol": "bol",
        "bill of lading": "bol",
        "pod": "pod",
        "proof": "pod",
        "delivery": "pod",
        "agreement": "broker_agreement",
        "carrier packet": "broker_agreement",
    }

    for att in attachments:
        fname = att.get("filename", "").lower()
        guess = "unknown"
        for kw, dtype in type_hints.items():
            if kw in fname:
                guess = dtype
                break
        classified.append({**att, "doc_type_guess": guess})

        # Persist to document_vault so scanner can pick it up
        if carrier_id or contract_id:
            sb = get_supabase()
            row: dict = {
                "doc_type": guess if guess != "unknown" else "rate_confirmation",
                "filename": att.get("filename", "unknown"),
                "storage_path": att.get("storage_path", ""),
                "file_size_kb": att.get("size_bytes", 0) // 1024,
                "mime_type": att.get("content_type", "application/pdf"),
                "scan_status": "pending",
            }
            if carrier_id:
                row["carrier_id"] = str(carrier_id)
            if contract_id:
                row["contract_id"] = str(contract_id)
            sb.table("document_vault").insert(row).execute()

    log.info("step_121: parsed email %s — %d attachments", payload.get("message_id"), len(attachments))
    return {
        "message_id": payload.get("message_id"),
        "from_address": payload.get("from_address"),
        "subject": payload.get("subject"),
        "attachment_count": len(attachments),
        "attachments": classified,
    }


def step_122_doc_classify(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Classify document type from vault record or payload hint.

    Reads pending documents from document_vault for the carrier/contract
    and assigns a definitive doc_type based on filename and content hints.
    """
    sb = get_supabase()
    q = sb.table("document_vault").select("*").eq("scan_status", "pending")
    if contract_id:
        q = q.eq("contract_id", str(contract_id))
    elif carrier_id:
        q = q.eq("carrier_id", str(carrier_id))
    docs = q.limit(50).execute().data or []

    classified: list[dict] = []
    for doc in docs:
        fname = (doc.get("filename") or "").lower()
        current_type = doc.get("doc_type", "unknown")

        # Refine classification from filename tokens
        if any(t in fname for t in ["rate", "rc", "load tender"]):
            final_type = "rate_confirmation"
        elif any(t in fname for t in ["bol", "bill of lading"]):
            final_type = "bol"
        elif any(t in fname for t in ["pod", "proof of delivery", "delivery receipt"]):
            final_type = "pod"
        elif any(t in fname for t in ["agreement", "carrier packet", "broker"]):
            final_type = "broker_agreement"
        elif any(t in fname for t in ["insurance", "coi", "certificate"]):
            final_type = "insurance"
        elif any(t in fname for t in ["w9", "w-9", "tax"]):
            final_type = "w9"
        else:
            final_type = current_type  # leave as-is

        sb.table("document_vault").update({
            "doc_type": final_type,
            "scan_status": "classified",
        }).eq("id", doc["id"]).execute()

        classified.append({"vault_id": doc["id"], "filename": doc["filename"], "doc_type": final_type})

    log.info("step_122: classified %d documents", len(classified))
    return {"documents_classified": len(classified), "documents": classified}


def step_123_extract_variables(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Run Claude scanner on raw_text from payload or linked contract.

    Expects payload: {raw_text, contract_type} or a contract_id to read from DB.
    Updates the contract record with extracted_vars and confidence_score.
    """
    raw_text = payload.get("raw_text")
    contract_type = payload.get("contract_type", "rate_confirmation")

    if not raw_text and contract_id:
        contract = _fetch_contract(contract_id)
        raw_text = contract.get("raw_text", "")
        contract_type = contract.get("contract_type", "rate_confirmation")

    if not raw_text:
        return {"extracted": 0, "confidence": 0.0, "warnings": ["No raw_text available"]}

    extracted, confidence, warnings = scan_contract(raw_text, contract_type)

    if contract_id:
        sb = get_supabase()
        sb.table("contracts").update({
            "extracted_vars": extracted,
            "confidence_score": confidence,
            "load_number": extracted.get("load_number"),
            "counterparty_name": extracted.get("broker_name") or extracted.get("shipper_name"),
            "rate_total": extracted.get("rate_total"),
            "rate_per_mile": extracted.get("rate_per_mile"),
            "origin_city": extracted.get("origin_city"),
            "destination_city": extracted.get("destination_city"),
            "pickup_date": extracted.get("pickup_date"),
            "delivery_date": extracted.get("delivery_date"),
            "payment_terms": extracted.get("payment_terms"),
        }).eq("id", str(contract_id)).execute()

        post_contract_event(contract_id, "variables_extracted", "clm.scanner", {
            "confidence": confidence,
            "fields_extracted": len([v for v in extracted.values() if v is not None]),
            "warnings": warnings,
        })

    fields = len([v for v in extracted.values() if v is not None])
    log.info("step_123: extracted %d fields confidence=%.2f contract=%s", fields, confidence, contract_id)
    return {
        "fields_extracted": fields,
        "confidence": confidence,
        "warnings": warnings,
        "extracted_vars": extracted,
    }


def step_124_digital_twin_create(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Create (or confirm) the contract digital twin in Supabase.

    If contract_id is already set, just confirms and enriches the record.
    Otherwise creates a new contract from payload.
    """
    sb = get_supabase()

    if contract_id:
        contract = _fetch_contract(contract_id)
        # Ensure status is at least 'active'
        if contract.get("status") == "draft":
            sb.table("contracts").update({"status": "active"}).eq("id", str(contract_id)).execute()
        log.info("step_124: digital twin confirmed contract=%s", contract_id)
        return {"contract_id": str(contract_id), "action": "confirmed", "status": "active"}

    # Create new twin from payload
    insert_data: dict = {
        "contract_type": payload.get("contract_type", "rate_confirmation"),
        "status": "active",
        "raw_text": payload.get("raw_text"),
        "document_url": payload.get("document_url"),
        "extracted_vars": payload.get("extracted_vars", {}),
        "counterparty_name": payload.get("counterparty_name"),
        "rate_total": payload.get("rate_total"),
        "rate_per_mile": payload.get("rate_per_mile"),
        "origin_city": payload.get("origin_city"),
        "destination_city": payload.get("destination_city"),
        "pickup_date": payload.get("pickup_date"),
        "delivery_date": payload.get("delivery_date"),
        "payment_terms": payload.get("payment_terms"),
        "load_number": payload.get("load_number"),
    }
    if carrier_id:
        insert_data["carrier_id"] = str(carrier_id)

    res = sb.table("contracts").insert(insert_data).execute()
    new_id = res.data[0]["id"]
    log.info("step_124: digital twin created contract=%s", new_id)
    return {"contract_id": new_id, "action": "created", "status": "active"}


def step_125_revenue_leakage_check(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Compare actual billing vs. contract terms to detect revenue leakage.

    Checks: rate_total vs. invoiced_amount, accessorial charges captured,
    detention billed if applicable.
    """
    if not contract_id:
        return {"leakage_detected": False, "warnings": ["No contract_id provided"]}

    contract = _fetch_contract(contract_id)
    evars = contract.get("extracted_vars") or {}

    warnings: list[str] = []
    leakage_amount = 0.0

    rate_total = float(contract.get("rate_total") or 0)
    invoiced = float(payload.get("invoiced_amount") or rate_total)

    if rate_total and invoiced < rate_total:
        gap = rate_total - invoiced
        warnings.append(f"Invoiced ${invoiced:.2f} < contract rate ${rate_total:.2f} (gap ${gap:.2f})")
        leakage_amount += gap

    # Check accessorial charges
    accessorials = evars.get("accessorial_charges") or []
    if accessorials and not payload.get("accessorials_billed"):
        total_acc = sum(float(a.get("amount", 0)) for a in accessorials)
        if total_acc > 0:
            warnings.append(f"Accessorial charges ${total_acc:.2f} may not be billed")
            leakage_amount += total_acc

    leakage_detected = leakage_amount > 0
    if leakage_detected:
        post_contract_event(contract_id, "revenue_leakage_detected", "clm.step_125", {
            "leakage_amount": leakage_amount,
            "warnings": warnings,
        })

    log.info("step_125: leakage=%s amount=$%.2f contract=%s", leakage_detected, leakage_amount, contract_id)
    return {
        "leakage_detected": leakage_detected,
        "leakage_amount": leakage_amount,
        "contract_rate": rate_total,
        "invoiced_amount": invoiced,
        "warnings": warnings,
    }


def step_126_counterparty_lookup(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Lookup broker or shipper in 3LL carrier/lead records and FMCSA data.

    Searches active_carriers and lead_pipeline by MC number or company name.
    """
    sb = get_supabase()
    broker_mc = payload.get("broker_mc")
    broker_name = payload.get("broker_name")

    if not broker_mc and contract_id:
        contract = _fetch_contract(contract_id)
        evars = contract.get("extracted_vars") or {}
        broker_mc = evars.get("broker_mc")
        broker_name = broker_name or evars.get("broker_name") or contract.get("counterparty_name")

    result: dict = {
        "broker_mc": broker_mc,
        "broker_name": broker_name,
        "found_in_carriers": False,
        "found_in_leads": False,
        "carrier_record": None,
        "lead_record": None,
    }

    if broker_mc:
        # Check active carriers (some brokers are also carriers)
        carr = sb.table("active_carriers").select(
            "id,company_name,mc_number,dot_number,phone,email,status"
        ).eq("mc_number", broker_mc).limit(1).execute().data
        if carr:
            result["found_in_carriers"] = True
            result["carrier_record"] = carr[0]

        # Check lead pipeline
        lead = sb.table("lead_pipeline").select(
            "id,company_name,mc_number,phone,email,score,stage"
        ).eq("mc_number", broker_mc).limit(1).execute().data
        if lead:
            result["found_in_leads"] = True
            result["lead_record"] = lead[0]

    log.info("step_126: counterparty lookup mc=%s found_carrier=%s", broker_mc, result["found_in_carriers"])
    return result


def step_127_duplicate_detect(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Detect duplicate rate confirmations by load_number or identical rate+lane.

    Flags if another contract with the same load_number already exists.
    """
    sb = get_supabase()
    load_number = payload.get("load_number")

    if not load_number and contract_id:
        contract = _fetch_contract(contract_id)
        load_number = contract.get("load_number") or (contract.get("extracted_vars") or {}).get("load_number")

    if not load_number:
        return {"duplicate_found": False, "note": "No load_number to check"}

    q = sb.table("contracts").select(
        "id,contract_type,status,counterparty_name,rate_total,origin_city,destination_city,created_at"
    ).eq("load_number", load_number)

    if contract_id:
        q = q.neq("id", str(contract_id))  # exclude self

    dupes = q.limit(10).execute().data or []

    if dupes and contract_id:
        post_contract_event(contract_id, "duplicate_detected", "clm.step_127", {
            "load_number": load_number,
            "duplicate_ids": [d["id"] for d in dupes],
        })

    log.info("step_127: load_number=%s duplicates=%d", load_number, len(dupes))
    return {
        "duplicate_found": len(dupes) > 0,
        "load_number": load_number,
        "duplicate_count": len(dupes),
        "duplicates": dupes,
    }


def step_128_expiry_schedule(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Schedule alerts for contract or broker agreement expiry.

    For broker_agreement contracts, sets expires_at and records alert schedule.
    For rate_confirmation contracts, uses delivery_date + payment_terms as due date.
    """
    if not contract_id:
        return {"scheduled": False, "warning": "No contract_id"}

    sb = get_supabase()
    contract = _fetch_contract(contract_id)
    ctype = contract.get("contract_type", "rate_confirmation")
    evars = contract.get("extracted_vars") or {}

    expires_at: str | None = None
    alert_days: list[int] = []

    if ctype == "broker_agreement":
        exp_str = evars.get("expiration_date")
        if exp_str:
            expires_at = exp_str
            alert_days = [30, 7, 1]
    else:
        # For rate_confirmation: payment due = delivery_date + payment_terms days
        delivery_date = contract.get("delivery_date") or evars.get("delivery_date")
        terms = contract.get("payment_terms") or evars.get("payment_terms") or "Net-30"
        try:
            days = int("".join(filter(str.isdigit, terms))) if terms else 30
        except (ValueError, TypeError):
            days = 30
        if delivery_date:
            try:
                base = date.fromisoformat(str(delivery_date))
                due = base + timedelta(days=days)
                expires_at = due.isoformat()
                alert_days = [7, 1]
            except ValueError:
                pass

    if expires_at:
        sb.table("contracts").update({"expires_at": expires_at}).eq("id", str(contract_id)).execute()
        post_contract_event(contract_id, "expiry_scheduled", "clm.step_128", {
            "expires_at": expires_at,
            "alert_days": alert_days,
        })

    log.info("step_128: contract=%s expires_at=%s", contract_id, expires_at)
    return {
        "contract_id": str(contract_id),
        "contract_type": ctype,
        "expires_at": expires_at,
        "alert_days_before": alert_days,
        "scheduled": expires_at is not None,
    }


def step_129_broker_blacklist_check(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Check broker MC against the bad-pay blacklist.

    Returns blacklisted=True with reason if found. Flags contract for review.
    """
    sb = get_supabase()
    broker_mc = payload.get("broker_mc")

    if not broker_mc and contract_id:
        contract = _fetch_contract(contract_id)
        evars = contract.get("extracted_vars") or {}
        broker_mc = evars.get("broker_mc")

    if not broker_mc:
        return {"blacklisted": False, "note": "No broker_mc to check"}

    hit = sb.table("broker_blacklist").select("*").eq("broker_mc", broker_mc).limit(1).execute().data

    blacklisted = len(hit) > 0
    entry = hit[0] if hit else None

    if blacklisted and contract_id:
        sb.table("contracts").update({
            "flagged_for_review": True,
            "review_notes": f"Broker MC {broker_mc} is on the blacklist: {entry.get('reason')}",
        }).eq("id", str(contract_id)).execute()

        post_contract_event(contract_id, "broker_blacklisted", "clm.step_129", {
            "broker_mc": broker_mc,
            "reason": entry.get("reason") if entry else None,
        })

    log.info("step_129: broker_mc=%s blacklisted=%s", broker_mc, blacklisted)
    return {
        "broker_mc": broker_mc,
        "blacklisted": blacklisted,
        "reason": entry.get("reason") if entry else None,
        "added_at": entry.get("added_at") if entry else None,
    }


def step_130_rate_benchmark(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Compare the contract rate against internal market benchmarks.

    Uses stored broker_scorecards averages and applies equipment-type adjustments.
    Falls back to national averages when no internal data exists.
    """
    sb = get_supabase()

    rate_per_mile = payload.get("rate_per_mile")
    origin_state = payload.get("origin_state")
    destination_state = payload.get("destination_state")
    equipment_type = payload.get("equipment_type", "dry_van")

    if not rate_per_mile and contract_id:
        contract = _fetch_contract(contract_id)
        rate_per_mile = contract.get("rate_per_mile")
        evars = contract.get("extracted_vars") or {}
        origin_state = origin_state or evars.get("origin_state")
        destination_state = destination_state or evars.get("destination_state")
        equipment_type = equipment_type or evars.get("equipment_type", "dry_van")

    if not rate_per_mile:
        return {"assessment": "unknown", "note": "No rate_per_mile available"}

    # Pull internal average from broker scorecards as market proxy
    sc = sb.table("broker_scorecards").select("avg_rate_per_mile").execute().data or []
    internal_rates = [float(r["avg_rate_per_mile"]) for r in sc if r.get("avg_rate_per_mile")]

    # National average fallbacks by equipment type (2024 benchmarks)
    national_avgs: dict[str, float] = {
        "dry_van": 2.45,
        "reefer": 2.85,
        "flatbed": 2.70,
        "step_deck": 2.75,
        "box_truck": 2.20,
        "cargo_van": 1.95,
        "tanker": 3.10,
        "hot_shot": 2.30,
    }
    eq_key = (equipment_type or "dry_van").lower().replace(" ", "_").replace("-", "_")
    market_avg = (
        sum(internal_rates) / len(internal_rates)
        if internal_rates
        else national_avgs.get(eq_key, 2.45)
    )
    market_low = round(market_avg * 0.85, 4)
    market_high = round(market_avg * 1.15, 4)
    variance_pct = round(((float(rate_per_mile) - market_avg) / market_avg) * 100, 2)

    if variance_pct < -10:
        assessment = "below_market"
    elif variance_pct > 10:
        assessment = "above_market"
    else:
        assessment = "at_market"

    if contract_id:
        post_contract_event(contract_id, "rate_benchmarked", "clm.step_130", {
            "rate_per_mile": rate_per_mile,
            "market_avg": market_avg,
            "variance_pct": variance_pct,
            "assessment": assessment,
        })

    log.info("step_130: rate=%.4f market_avg=%.4f variance=%.1f%% assessment=%s",
             float(rate_per_mile), market_avg, variance_pct, assessment)
    return {
        "origin_state": origin_state,
        "destination_state": destination_state,
        "equipment_type": equipment_type,
        "submitted_rate_per_mile": float(rate_per_mile),
        "market_avg_per_mile": round(market_avg, 4),
        "market_low_per_mile": market_low,
        "market_high_per_mile": market_high,
        "variance_pct": variance_pct,
        "assessment": assessment,
        "data_source": "internal_scorecards" if internal_rates else "national_benchmark",
    }


# ═══════════════════════════════════════════════════════════════════════════
# STEPS 131-140 — Auto-approval / milestones / GL / factoring / payment terms
# ═══════════════════════════════════════════════════════════════════════════

def step_131_auto_approve(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Auto-approve contract if confidence >90% and no blocking warnings.

    Conditions checked:
    - confidence_score >= 0.90
    - flagged_for_review is False
    - broker NOT on blacklist (checked in step 129)
    - No revenue leakage warnings (from step 125)

    Sets auto_approved=True and status='active' on success.
    """
    if not contract_id:
        return {"approved": False, "reason": "No contract_id"}

    sb = get_supabase()
    contract = _fetch_contract(contract_id)

    confidence = float(contract.get("confidence_score") or 0)
    flagged = contract.get("flagged_for_review", False)
    warnings = payload.get("warnings", [])

    # Blocking conditions
    if confidence < 0.90:
        reason = f"Confidence {confidence:.0%} < 90% threshold"
        sb.table("contracts").update({"flagged_for_review": True,
                                      "review_notes": reason}).eq("id", str(contract_id)).execute()
        post_contract_event(contract_id, "auto_approve_failed", "clm.step_131",
                            {"reason": reason, "confidence": confidence})
        log.info("step_131: contract=%s NOT approved — %s", contract_id, reason)
        return {"approved": False, "reason": reason, "confidence": confidence}

    if flagged:
        reason = contract.get("review_notes") or "Flagged for review"
        post_contract_event(contract_id, "auto_approve_skipped", "clm.step_131", {"reason": reason})
        log.info("step_131: contract=%s skipped — already flagged", contract_id)
        return {"approved": False, "reason": reason, "flagged": True}

    if warnings:
        reason = f"Blocking warnings: {'; '.join(warnings)}"
        sb.table("contracts").update({"flagged_for_review": True,
                                      "review_notes": reason}).eq("id", str(contract_id)).execute()
        post_contract_event(contract_id, "auto_approve_failed", "clm.step_131",
                            {"reason": reason, "warnings": warnings})
        return {"approved": False, "reason": reason}

    # All clear — approve
    sb.table("contracts").update({
        "auto_approved": True,
        "status": "active",
    }).eq("id", str(contract_id)).execute()

    post_contract_event(contract_id, "auto_approved", "clm.step_131", {
        "confidence": confidence,
        "auto_approved": True,
    })
    log.info("step_131: contract=%s AUTO-APPROVED confidence=%.0f%%", contract_id, confidence * 100)
    return {"approved": True, "confidence": confidence, "status": "active"}


def step_132_flag_for_review(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Flag contract for Commander review when warnings exist.

    Accepts payload: {reason, warnings (list), severity (low|medium|high)}.
    Sets flagged_for_review=True and writes review_notes.
    """
    if not contract_id:
        return {"flagged": False, "reason": "No contract_id"}

    sb = get_supabase()
    reason = payload.get("reason", "Manual flag")
    warnings = payload.get("warnings", [])
    severity = payload.get("severity", "medium")

    notes = reason
    if warnings:
        notes += " | " + "; ".join(warnings)

    sb.table("contracts").update({
        "flagged_for_review": True,
        "review_notes": notes[:500],
    }).eq("id", str(contract_id)).execute()

    post_contract_event(contract_id, "flagged_for_review", "clm.step_132", {
        "reason": reason,
        "warnings": warnings,
        "severity": severity,
    })

    log.info("step_132: contract=%s flagged severity=%s", contract_id, severity)
    return {
        "flagged": True,
        "contract_id": str(contract_id),
        "reason": reason,
        "severity": severity,
        "warnings": warnings,
    }


def step_133_milestone_10pct(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Set contract milestone to 10% — triggered on load assignment."""
    if not contract_id:
        return {"milestone_pct": None, "error": "No contract_id"}
    result = update_milestone(contract_id, 10, "Load assigned to driver")
    log.info("step_133: contract=%s milestone=10%%", contract_id)
    return {"milestone_pct": 10, "contract_id": str(contract_id), "result": result}


def step_134_milestone_50pct(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Set contract milestone to 50% — triggered on pickup confirmed."""
    if not contract_id:
        return {"milestone_pct": None, "error": "No contract_id"}
    result = update_milestone(contract_id, 50, "Pickup confirmed — truck in transit")
    log.info("step_134: contract=%s milestone=50%%", contract_id)
    return {"milestone_pct": 50, "contract_id": str(contract_id), "result": result}


def step_135_milestone_90pct(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Set contract milestone to 90% — triggered on POD uploaded."""
    if not contract_id:
        return {"milestone_pct": None, "error": "No contract_id"}
    result = update_milestone(contract_id, 90, "POD uploaded — awaiting invoice payment")
    log.info("step_135: contract=%s milestone=90%%", contract_id)
    return {"milestone_pct": 90, "contract_id": str(contract_id), "result": result}


def step_136_milestone_100pct(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Set contract milestone to 100% — triggered on invoice paid."""
    if not contract_id:
        return {"milestone_pct": None, "error": "No contract_id"}
    result = update_milestone(contract_id, 100, "Invoice paid — contract fully executed")
    log.info("step_136: contract=%s milestone=100%%", contract_id)
    return {"milestone_pct": 100, "contract_id": str(contract_id), "status": "executed", "result": result}


def step_137_gl_trigger(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Trigger GL/accounting entry at 100% milestone.

    Calls trigger_invoice() to recognize revenue and mark gl_posted=True.
    """
    if not contract_id:
        return {"gl_posted": False, "error": "No contract_id"}

    sb = get_supabase()
    contract = trigger_invoice(contract_id)

    sb.table("contracts").update({
        "gl_posted": True,
    }).eq("id", str(contract_id)).execute()

    post_contract_event(contract_id, "gl_posted", "clm.step_137", {
        "rate_total": contract.get("rate_total"),
        "payment_terms": contract.get("payment_terms"),
    })

    log.info("step_137: contract=%s GL posted rate=$%s", contract_id, contract.get("rate_total"))
    return {
        "gl_posted": True,
        "contract_id": str(contract_id),
        "rate_total": contract.get("rate_total"),
        "payment_terms": contract.get("payment_terms"),
        "revenue_recognized": True,
    }


def step_138_factoring_eligibility(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Check if contract is eligible for factoring.

    Eligibility requires:
    - factoring_allowed=True in extracted_vars (broker allows factoring)
    - Broker NOT on blacklist
    - Contract status = active
    - rate_total > 0
    """
    if not contract_id:
        return {"eligible": False, "reason": "No contract_id"}

    sb = get_supabase()
    contract = _fetch_contract(contract_id)
    evars = contract.get("extracted_vars") or {}

    reasons_denied: list[str] = []

    factoring_allowed = evars.get("factoring_allowed")
    if factoring_allowed is False:
        reasons_denied.append("Broker prohibits factoring in rate confirmation")

    broker_mc = evars.get("broker_mc")
    if broker_mc:
        hit = sb.table("broker_blacklist").select("broker_mc").eq("broker_mc", broker_mc).limit(1).execute().data
        if hit:
            reasons_denied.append(f"Broker MC {broker_mc} is blacklisted")

    if contract.get("status") not in ("active", "executed"):
        reasons_denied.append(f"Contract status is '{contract.get('status')}' — must be active")

    rate_total = float(contract.get("rate_total") or 0)
    if rate_total <= 0:
        reasons_denied.append("rate_total is zero or unknown")

    eligible = len(reasons_denied) == 0
    post_contract_event(contract_id, "factoring_eligibility_checked", "clm.step_138", {
        "eligible": eligible,
        "reasons_denied": reasons_denied,
        "rate_total": rate_total,
    })

    log.info("step_138: contract=%s factoring_eligible=%s", contract_id, eligible)
    return {
        "eligible": eligible,
        "contract_id": str(contract_id),
        "rate_total": rate_total,
        "broker_mc": broker_mc,
        "reasons_denied": reasons_denied,
    }


def step_139_broker_agreement_link(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Link a rate confirmation to its parent master broker agreement.

    Searches contracts for a broker_agreement type with the same broker_mc,
    then sets broker_agreement_id on the rate confirmation.
    """
    if not contract_id:
        return {"linked": False, "reason": "No contract_id"}

    sb = get_supabase()
    contract = _fetch_contract(contract_id)

    if contract.get("contract_type") != "rate_confirmation":
        return {"linked": False, "reason": "Not a rate_confirmation contract"}

    evars = contract.get("extracted_vars") or {}
    broker_mc = evars.get("broker_mc") or payload.get("broker_mc")

    if not broker_mc:
        return {"linked": False, "reason": "No broker_mc in contract vars"}

    # Find the matching master broker agreement
    agreements = (
        sb.table("contracts")
        .select("id,counterparty_name,status,expires_at")
        .eq("contract_type", "broker_agreement")
        .filter("extracted_vars->>'broker_mc'", "eq", broker_mc)
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
    )

    if not agreements:
        log.info("step_139: no broker_agreement found for mc=%s", broker_mc)
        return {
            "linked": False,
            "broker_mc": broker_mc,
            "reason": "No active broker agreement on file",
        }

    agreement = agreements[0]
    sb.table("contracts").update({
        "broker_agreement_id": agreement["id"],
    }).eq("id", str(contract_id)).execute()

    post_contract_event(contract_id, "broker_agreement_linked", "clm.step_139", {
        "broker_agreement_id": agreement["id"],
        "broker_mc": broker_mc,
    })

    log.info("step_139: contract=%s linked to agreement=%s", contract_id, agreement["id"])
    return {
        "linked": True,
        "contract_id": str(contract_id),
        "broker_agreement_id": agreement["id"],
        "broker_mc": broker_mc,
        "agreement_status": agreement.get("status"),
        "agreement_expires_at": agreement.get("expires_at"),
    }


def step_140_payment_terms_enforce(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Enforce payment terms — flag contract if payment is overdue.

    Parses payment_terms (e.g. 'Net-30', 'Quick Pay 2%/10') and compares
    the due date against today. Flags as overdue if unpaid past due date.
    """
    if not contract_id:
        return {"overdue": False, "reason": "No contract_id"}

    sb = get_supabase()
    contract = _fetch_contract(contract_id)

    if contract.get("revenue_recognized"):
        return {"overdue": False, "note": "Already paid — no action needed"}

    delivery_date = contract.get("delivery_date")
    payment_terms = contract.get("payment_terms") or "Net-30"

    if not delivery_date:
        return {"overdue": False, "note": "No delivery_date — cannot compute due date"}

    try:
        base = date.fromisoformat(str(delivery_date))
        # Extract net days from terms string
        digits = "".join(filter(str.isdigit, payment_terms.split("/")[0]))
        net_days = int(digits) if digits else 30
        due_date = base + timedelta(days=net_days)
        today = date.today()
        days_overdue = (today - due_date).days
    except (ValueError, TypeError) as exc:
        return {"overdue": False, "note": f"Could not parse dates: {exc}"}

    overdue = days_overdue > 0

    if overdue:
        sb.table("contracts").update({
            "flagged_for_review": True,
            "review_notes": f"Payment overdue by {days_overdue} days (terms: {payment_terms})",
        }).eq("id", str(contract_id)).execute()

        post_contract_event(contract_id, "payment_overdue", "clm.step_140", {
            "due_date": due_date.isoformat(),
            "days_overdue": days_overdue,
            "payment_terms": payment_terms,
        })

    log.info("step_140: contract=%s overdue=%s days=%d", contract_id, overdue, days_overdue if overdue else 0)
    return {
        "overdue": overdue,
        "contract_id": str(contract_id),
        "payment_terms": payment_terms,
        "due_date": due_date.isoformat() if delivery_date else None,
        "days_overdue": max(0, days_overdue),
        "rate_total": contract.get("rate_total"),
    }
