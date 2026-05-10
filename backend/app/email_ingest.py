"""Email ingest service — receives broker rate confirmations via SendGrid webhook.

Parses incoming emails, extracts PDFs, runs OCR + CLM contract scanner,
auto-creates load records, and logs audit trail.

SendGrid Inbound Parse webhook:
  POST /api/webhooks/email/inbound
  Content-Type: multipart/form-data
  Contains: from, to, subject, text, html, attachments, etc.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from .clm.scanner import scan_contract
from .logging_service import get_logger
from .supabase_client import get_supabase
from .settings import get_settings

log = get_logger("email_ingest")
router = APIRouter()


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF using PyPDF2.

    Falls back to empty string if PDF is unreadable.
    This text is passed to the CLM scanner for contract extraction.
    """
    try:
        try:
            import PyPDF2
        except ImportError:
            log.warning("PyPDF2 not installed — PDF text extraction disabled. Run: pip install PyPDF2")
            return ""

        pdf_file = BytesIO(pdf_bytes)
        pdf_reader = PyPDF2.PdfReader(pdf_file)

        text_parts = []
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            text = page.extract_text()
            if text:
                text_parts.append(text)

        return "\n".join(text_parts)
    except Exception as e:  # noqa: BLE001
        log.error("PDF text extraction failed: %s", e)
        return ""


def verify_sendgrid_signature(request_body: bytes, signature: str | None) -> bool:
    """Verify SendGrid inbound webhook signature (optional security layer).

    Set SENDGRID_INBOUND_SECRET in .env to enable verification.
    """
    s = get_settings()
    if not s.sendgrid_inbound_secret:
        log.debug("SendGrid signature verification disabled (no SENDGRID_INBOUND_SECRET)")
        return True

    if not signature:
        log.warning("SendGrid webhook received without signature")
        return False

    # SendGrid sends: signature = base64(hmac-sha256(secret, request_body))
    try:
        expected_sig = base64.b64encode(
            hmac.new(
                s.sendgrid_inbound_secret.encode(),
                request_body,
                hashlib.sha256
            ).digest()
        ).decode()

        is_valid = hmac.compare_digest(signature, expected_sig)
        if not is_valid:
            log.warning("SendGrid webhook signature mismatch")
        return is_valid
    except Exception as e:  # noqa: BLE001
        log.error("SendGrid signature verification error: %s", e)
        return False


@router.post("/webhooks/email/inbound")
async def receive_inbound_email(request: Request) -> dict[str, Any]:
    """Receive email from SendGrid Inbound Parse webhook.

    Returns 200 OK immediately to SendGrid, then processes asynchronously.
    """
    try:
        # Verify webhook signature (optional)
        body = await request.body()
        signature = request.headers.get("X-SendGrid-Signature")
        if not verify_sendgrid_signature(body, signature):
            log.warning("Invalid SendGrid webhook signature")
            raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid signature")

        # Parse multipart form data
        form = await request.form()

        from_email = form.get("from") or "unknown@example.com"
        to_email = form.get("to") or ""
        subject = form.get("subject") or "(no subject)"
        text = form.get("text") or ""
        html = form.get("html") or ""

        # Build email record for audit log
        email_record = {
            "from_email": from_email,
            "to_email": to_email,
            "subject": subject,
            "body_text": text[:5000] if text else "",  # Truncate to 5000 chars
            "body_html": html[:5000] if html else "",
            "attachment_count": 0,
            "status": "received",
            "source": "sendgrid",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Extract attachments
        files = form.getlist("attachments") if form else []
        email_record["attachment_count"] = len(files)

        # Insert email record into audit log
        sb = get_supabase()
        try:
            log_result = sb.table("email_log").insert(email_record).execute()
            email_id = log_result.data[0]["id"] if log_result.data else None
        except Exception as e:  # noqa: BLE001
            log.error("Failed to insert email_log record: %s", e)
            email_id = None

        if not email_id:
            log.error("Email audit log insertion failed — cannot proceed with processing")
            # Still return 200 to SendGrid to avoid redelivery
            return {"ok": False, "email_id": None, "status": "audit_log_failed"}

        # Process attachments (PDFs for rate confirmations)
        loads_created = 0
        processing_error = None
        extracted_data = None

        for file in files:
            if not file.filename:
                continue

            log.info(f"Processing attachment: {file.filename}")

            if file.filename.lower().endswith(".pdf"):
                try:
                    pdf_bytes = await file.read()

                    # Extract text from PDF
                    ocr_text = extract_pdf_text(pdf_bytes)
                    if not ocr_text:
                        log.warning(f"Failed to extract text from {file.filename}")
                        continue

                    # Run CLM scanner to extract contract variables
                    extracted, confidence, warnings = scan_contract(ocr_text, "rate_confirmation")

                    if warnings:
                        log.info(f"CLM scanner warnings for {file.filename}: {warnings}")

                    # Store extraction results for audit
                    extracted_data = {
                        "extracted": extracted,
                        "confidence": confidence,
                        "warnings": warnings,
                        "pdf_filename": file.filename,
                    }

                    # Create load record if confidence > 0.9
                    if confidence > 0.9 and extracted.get("broker_name"):
                        try:
                            load_data = {
                                "broker_name": extracted.get("broker_name"),
                                "broker_phone": extracted.get("broker_phone"),
                                "load_number": extracted.get("load_number"),
                                "origin_city": extracted.get("origin_city"),
                                "origin_state": extracted.get("origin_state"),
                                "dest_city": extracted.get("destination_city"),
                                "dest_state": extracted.get("destination_state"),
                                "pickup_at": extracted.get("pickup_date"),
                                "delivery_at": extracted.get("delivery_date"),
                                "miles": extracted.get("miles"),
                                "rate_total": extracted.get("rate_total"),
                                "rate_per_mile": extracted.get("rate_per_mile"),
                                "commodity": extracted.get("commodity"),
                                "weight": extracted.get("weight_lbs"),
                                "equipment_type": extracted.get("equipment_type"),
                                "special_instructions": extracted.get("special_instructions"),
                                "status": "available",
                                "email_source_id": email_id,
                                "created_at": datetime.now(timezone.utc).isoformat(),
                            }

                            # Remove None values
                            load_data = {k: v for k, v in load_data.items() if v is not None}

                            load_result = sb.table("loads").insert(load_data).execute()
                            if load_result.data:
                                new_load = load_result.data[0]
                                loads_created += 1
                                log.info(f"Created load {new_load.get('id')} from email {email_id}")

                                # Update email log with load link
                                sb.table("email_log").update({
                                    "load_id": new_load.get("id"),
                                    "status": "load_created",
                                    "confidence": confidence,
                                    "extracted_data": extracted_data,
                                    "broker_name": extracted.get("broker_name"),
                                    "processed_at": datetime.now(timezone.utc).isoformat(),
                                }).eq("id", email_id).execute()
                        except Exception as e:  # noqa: BLE001
                            log.error(f"Failed to create load from email: {e}")
                            processing_error = str(e)
                    else:
                        # Low confidence → flag for review
                        status_msg = "low_confidence" if confidence <= 0.9 else "invalid_data"
                        sb.table("email_log").update({
                            "status": status_msg,
                            "confidence": confidence,
                            "extracted_data": extracted_data,
                            "broker_name": extracted.get("broker_name"),
                            "processed_at": datetime.now(timezone.utc).isoformat(),
                            "notes": f"Confidence {confidence:.2f}, missing broker_name" if not extracted.get("broker_name") else f"Confidence {confidence:.2f}",
                        }).eq("id", email_id).execute()

                        log.info(f"Low confidence ({confidence:.2f}) for {file.filename} — flagged for review")

                except Exception as e:  # noqa: BLE001
                    log.error(f"Error processing PDF attachment: {e}")
                    processing_error = str(e)
                    sb.table("email_log").update({
                        "status": "error",
                        "notes": f"PDF processing error: {processing_error}",
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", email_id).execute()

        result_status = "ok"
        if processing_error and loads_created == 0:
            result_status = "error"
        elif loads_created == 0 and files:
            result_status = "no_loads_created"

        return {
            "ok": result_status == "ok",
            "email_id": email_id,
            "status": result_status,
            "loads_created": loads_created,
            "error": processing_error,
        }

    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error(f"Unhandled error in inbound email endpoint: {e}")
        # Return 200 to prevent SendGrid redelivery
        return {"ok": False, "status": "error", "error": str(e)}
