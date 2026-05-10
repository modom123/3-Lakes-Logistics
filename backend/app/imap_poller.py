"""IMAP poller service — pulls emails from Hostinger and internal accounts.

Connects to Hostinger IMAP (or any IMAP server) and pulls unseen emails
into the same processing pipeline as SendGrid inbound emails.

Configuration via .env:
  HOSTINGER_IMAP_USERNAME=orders@mydomain.com
  HOSTINGER_IMAP_PASSWORD=***
  HOSTINGER_IMAP_ENABLED=true
  HOSTINGER_IMAP_POLL_INTERVAL_SECONDS=300
"""
from __future__ import annotations

import email
import imaplib
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from .logging_service import get_logger
from .settings import get_settings
from .supabase_client import get_supabase

log = get_logger("imap_poller")


class IMAPPoller:
    """Connect to IMAP server and poll for unseen emails."""

    def __init__(self):
        self.settings = get_settings()
        self.host = self.settings.hostinger_imap_host
        self.port = self.settings.hostinger_imap_port
        self.username = self.settings.hostinger_imap_username
        self.password = self.settings.hostinger_imap_password
        self.enabled = self.settings.hostinger_imap_enabled

    def connect(self) -> imaplib.IMAP4_SSL | None:
        """Connect to IMAP server and return IMAP4_SSL connection."""
        if not self.enabled or not self.username or not self.password:
            log.debug("IMAP poller disabled or credentials missing")
            return None

        try:
            imap_conn = imaplib.IMAP4_SSL(self.host, self.port)
            imap_conn.login(self.username, self.password)
            log.info(f"Connected to IMAP {self.host}:{self.port} as {self.username}")
            return imap_conn
        except Exception as e:  # noqa: BLE001
            log.error(f"IMAP connection failed: {e}")
            return None

    async def poll_inbox(self) -> dict[str, Any]:
        """Poll INBOX for unseen emails and process them.

        Returns summary dict with email count and processing status.
        """
        if not self.enabled:
            return {"ok": False, "status": "disabled", "emails_processed": 0}

        imap_conn = self.connect()
        if not imap_conn:
            return {"ok": False, "status": "connection_failed", "emails_processed": 0}

        try:
            # Select INBOX
            status, mailbox_list = imap_conn.select("INBOX")
            if status != "OK":
                log.error(f"Failed to select INBOX: {status}")
                return {"ok": False, "status": "inbox_select_failed", "emails_processed": 0}

            # Search for unseen emails
            status, unseen_ids = imap_conn.search(None, "UNSEEN")
            if status != "OK":
                log.error("Failed to search for unseen emails")
                return {"ok": False, "status": "search_failed", "emails_processed": 0}

            email_ids = unseen_ids[0].split()
            if not email_ids:
                log.debug("No unseen emails in INBOX")
                return {"ok": True, "status": "ok", "emails_processed": 0}

            log.info(f"Found {len(email_ids)} unseen emails")

            emails_processed = 0
            for email_id in email_ids:
                try:
                    # Fetch the email
                    status, msg_data = imap_conn.fetch(email_id, "(RFC822)")
                    if status != "OK":
                        log.warning(f"Failed to fetch email {email_id}")
                        continue

                    # Parse email
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    # Extract email components
                    from_email = msg.get("From", "unknown@example.com")
                    to_email = msg.get("To", "")
                    subject = msg.get("Subject", "(no subject)")
                    received_date = msg.get("Date", "")

                    # Extract body
                    text_body = ""
                    html_body = ""

                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            if content_type == "text/plain" and not text_body:
                                text_body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                            elif content_type == "text/html" and not html_body:
                                html_body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    else:
                        payload = msg.get_payload(decode=True)
                        if payload:
                            text_body = payload.decode("utf-8", errors="ignore")

                    # Extract attachments
                    attachments = []
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_disposition() == "attachment":
                                filename = part.get_filename()
                                if filename:
                                    attachments.append({
                                        "filename": filename,
                                        "data": part.get_payload(decode=True),
                                        "content_type": part.get_content_type(),
                                    })

                    # Process email
                    await self._process_email(
                        from_email=from_email,
                        to_email=to_email,
                        subject=subject,
                        text_body=text_body,
                        html_body=html_body,
                        attachments=attachments,
                        received_date=received_date,
                        source="hostinger_imap",
                    )

                    # Mark as seen
                    imap_conn.store(email_id, "+FLAGS", "\\Seen")
                    emails_processed += 1

                except Exception as e:  # noqa: BLE001
                    log.error(f"Error processing email {email_id}: {e}")
                    continue

            return {
                "ok": True,
                "status": "ok",
                "emails_processed": emails_processed,
            }

        finally:
            imap_conn.close()
            imap_conn.logout()

    async def _process_email(
        self,
        from_email: str,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str,
        attachments: list[dict],
        received_date: str,
        source: str = "hostinger_imap",
    ) -> None:
        """Process a single email — same logic as SendGrid inbound."""
        from .clm.scanner import scan_contract
        from .email_ingest import extract_pdf_text

        sb = get_supabase()

        # Build email record for audit log
        email_record = {
            "from_email": from_email,
            "to_email": to_email,
            "subject": subject,
            "body_text": text_body[:5000] if text_body else "",
            "body_html": html_body[:5000] if html_body else "",
            "attachment_count": len(attachments),
            "status": "received",
            "source": source,
            "received_at": received_date or datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Insert email record
        try:
            log_result = sb.table("email_log").insert(email_record).execute()
            email_id = log_result.data[0]["id"] if log_result.data else None
        except Exception as e:  # noqa: BLE001
            log.error(f"Failed to insert email_log record: {e}")
            return

        if not email_id:
            log.error("Email audit log insertion failed")
            return

        log.info(f"Email {email_id} logged from {from_email}")

        # Process PDF attachments
        for attachment in attachments:
            if not attachment["filename"].lower().endswith(".pdf"):
                continue

            try:
                pdf_bytes = attachment["data"]
                ocr_text = extract_pdf_text(pdf_bytes)

                if not ocr_text:
                    log.warning(f"Failed to extract text from {attachment['filename']}")
                    continue

                # Run CLM scanner
                extracted, confidence, warnings = scan_contract(ocr_text, "rate_confirmation")

                if warnings:
                    log.info(f"CLM warnings for {attachment['filename']}: {warnings}")

                # Create load if confidence > 0.9
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

                        load_data = {k: v for k, v in load_data.items() if v is not None}

                        load_result = sb.table("loads").insert(load_data).execute()
                        if load_result.data:
                            loads_created = load_result.data[0]
                            log.info(f"Created load {loads_created.get('id')} from email {email_id}")

                            sb.table("email_log").update({
                                "load_id": loads_created.get("id"),
                                "status": "load_created",
                                "confidence": confidence,
                                "broker_name": extracted.get("broker_name"),
                                "processed_at": datetime.now(timezone.utc).isoformat(),
                            }).eq("id", email_id).execute()
                    except Exception as e:  # noqa: BLE001
                        log.error(f"Failed to create load: {e}")
                else:
                    # Low confidence or missing data
                    status_msg = "low_confidence" if confidence <= 0.9 else "invalid_data"
                    sb.table("email_log").update({
                        "status": status_msg,
                        "confidence": confidence,
                        "broker_name": extracted.get("broker_name"),
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", email_id).execute()

                    log.info(f"Low confidence ({confidence:.2f}) — flagged for review")

            except Exception as e:  # noqa: BLE001
                log.error(f"Error processing PDF: {e}")
                sb.table("email_log").update({
                    "status": "error",
                    "notes": f"PDF processing error: {str(e)}",
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", email_id).execute()


async def run_imap_poll() -> dict[str, Any]:
    """Run IMAP polling task — called by scheduler."""
    try:
        poller = IMAPPoller()
        result = await poller.poll_inbox()
        if result.get("emails_processed", 0) > 0:
            log.info(f"IMAP poll: {result['emails_processed']} emails processed")
        return result
    except Exception as e:  # noqa: BLE001
        log.error(f"IMAP polling error: {e}")
        return {"ok": False, "status": "error", "error": str(e)}
