"""Branded PDF generation for the document vault.

Produces real, downloadable PDF files for the three document types that were
previously created as metadata-only vault rows (and therefore 404'd on view):

  * Signed agreements  — an e-signature certificate (parties + audit trail)
  * Invoices           — bill-to, load, line items, totals, payment terms
  * Rate confirmations — the load/rate breakdown sent to carriers

Each generator returns PDF bytes. ``store_document_bytes`` uploads those bytes to
Supabase Storage (the ``documents`` bucket by default) at the same storage_path
the vault row points at, so the file resolves for view/download.

reportlab is a hard dependency (see backend/requirements.txt). Callers wrap these
in try/except so document delivery never blocks the signing/invoicing flow.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..supabase_client import get_supabase

log = logging.getLogger("3ll.documents.pdf")

# ── Brand ───────────────────────────────────────────────────────────────────────
NAVY = colors.HexColor("#0B2545")
GOLD = colors.HexColor("#C8902A")
MUTED = colors.HexColor("#6B7280")
LIGHT = colors.HexColor("#F3F4F6")

COMPANY = "3 Lakes Logistics LLC"
PHONE = "661-466-9932"
FOOTER_TXT = f"{COMPANY}  ·  {PHONE}  ·  info@3lakeslogistics.com"


def _fmt_money(v: Any) -> str:
    try:
        return f"${float(v or 0):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%b %d, %Y")
    except (ValueError, AttributeError):
        return str(iso)[:10]


def _fmt_dt(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%b %d, %Y %H:%M UTC")
    except (ValueError, AttributeError):
        return str(iso)


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle("brand", parent=base["Title"], textColor=colors.white,
                                fontSize=22, leading=26, spaceAfter=0),
        "doctitle": ParagraphStyle("doctitle", parent=base["Normal"], textColor=GOLD,
                                   fontSize=12, leading=14, spaceBefore=2,
                                   fontName="Helvetica-Bold"),
        "h": ParagraphStyle("h", parent=base["Heading2"], textColor=NAVY, fontSize=13,
                            spaceBefore=14, spaceAfter=6),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=10, leading=15,
                               textColor=colors.HexColor("#1F2937")),
        "muted": ParagraphStyle("muted", parent=base["Normal"], fontSize=9, leading=13,
                                textColor=MUTED),
        "right": ParagraphStyle("right", parent=base["Normal"], fontSize=10, alignment=TA_RIGHT),
        "footer": ParagraphStyle("footer", parent=base["Normal"], fontSize=8, leading=11,
                                 textColor=MUTED, alignment=TA_CENTER),
    }


def _on_page(canvas, doc) -> None:
    """Draw the navy header band and the footer on every page."""
    width, height = LETTER
    canvas.saveState()
    # Header band
    canvas.setFillColor(NAVY)
    canvas.rect(0, height - 1.05 * inch, width, 1.05 * inch, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 20)
    canvas.drawString(0.75 * inch, height - 0.6 * inch, "3 LAKES LOGISTICS")
    canvas.setFillColor(GOLD)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(0.75 * inch, height - 0.8 * inch, "AUTOMATED AMERICAN TRUCKING")
    # Footer
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(width / 2.0, 0.5 * inch, FOOTER_TXT)
    canvas.drawRightString(width - 0.75 * inch, 0.5 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _build(story: list, title: str) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER, title=title, author=COMPANY,
        topMargin=1.3 * inch, bottomMargin=0.85 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )
    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buf.getvalue()


def _kv_table(rows: list[tuple[str, str]], st: dict) -> Table:
    data = [[Paragraph(k, st["muted"]), Paragraph(v, st["body"])] for k, v in rows]
    t = Table(data, colWidths=[1.9 * inch, 4.85 * inch])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#E5E7EB")),
    ]))
    return t


# ── Generators ────────────────────────────────────────────────────────────────

def render_agreement_pdf(
    *,
    label: str,
    carrier_name: str,
    signatory_name: str,
    signed_at: str,
    signatory_ip: str | None = None,
    agreement_no: str | None = None,
    carrier_mc: str | None = None,
    carrier_dot: str | None = None,
    agreement_url: str | None = None,
) -> bytes:
    """Signed-agreement e-signature certificate."""
    st = _styles()
    story: list = [
        Paragraph(label, st["doctitle"]),
        Spacer(1, 6),
        Paragraph("Electronically Signed Agreement", st["h"]),
        HRFlowable(width="100%", thickness=1, color=GOLD, spaceAfter=10),
    ]
    rows = [("Agreement", label)]
    if agreement_no:
        rows.append(("Agreement #", agreement_no))
    rows.append(("Carrier / Party", carrier_name or "—"))
    if carrier_mc:
        rows.append(("MC #", carrier_mc))
    if carrier_dot:
        rows.append(("DOT #", carrier_dot))
    rows += [
        ("Signed By", signatory_name or "—"),
        ("Date & Time", _fmt_dt(signed_at)),
        ("Signer IP", signatory_ip or "—"),
    ]
    story.append(_kv_table(rows, st))
    story.append(Spacer(1, 16))
    story.append(Paragraph(
        f"<b>{signatory_name}</b> electronically reviewed and signed the "
        f"<b>{label}</b> with {COMPANY} on {_fmt_dt(signed_at)}. This record, together "
        f"with the captured IP address and timestamp, constitutes the electronic "
        f"signature and is legally binding under the U.S. ESIGN Act.",
        st["body"],
    ))
    if agreement_url:
        story.append(Spacer(1, 10))
        story.append(Paragraph(
            f'Full agreement text: <a href="{agreement_url}" color="#0B2545">{agreement_url}</a>',
            st["muted"],
        ))
    story.append(Spacer(1, 18))
    story.append(Paragraph(
        f"Issued {_fmt_dt(datetime.now(timezone.utc).isoformat())} · {COMPANY}",
        st["muted"],
    ))
    return _build(story, f"{label} — Signed")


def render_invoice_pdf(
    *,
    invoice_no: str,
    bill_to: str,
    rate_total: float,
    payment_terms: str = "Net-30",
    issued_at: str | None = None,
    load_number: str | None = None,
    origin: str | None = None,
    destination: str | None = None,
    line_items: list[tuple[str, float]] | None = None,
) -> bytes:
    """Freight invoice."""
    st = _styles()
    issued = issued_at or datetime.now(timezone.utc).isoformat()
    story: list = [
        Paragraph("INVOICE", st["doctitle"]),
        Spacer(1, 6),
    ]
    meta_rows = [
        ("Invoice #", invoice_no),
        ("Issue Date", _fmt_date(issued)),
        ("Payment Terms", payment_terms or "Net-30"),
        ("Bill To", bill_to or "—"),
    ]
    if load_number:
        meta_rows.append(("Load #", load_number))
    if origin or destination:
        meta_rows.append(("Lane", f"{origin or '—'} → {destination or '—'}"))
    story.append(_kv_table(meta_rows, st))
    story.append(Spacer(1, 16))
    story.append(Paragraph("Charges", st["h"]))

    items = line_items or [("Freight services" + (f" — Load {load_number}" if load_number else ""), rate_total)]
    data = [[Paragraph("<b>Description</b>", st["body"]), Paragraph("<b>Amount</b>", st["right"])]]
    total = 0.0
    for desc, amt in items:
        data.append([Paragraph(desc, st["body"]), Paragraph(_fmt_money(amt), st["right"])])
        total += float(amt or 0)
    data.append([Paragraph("<b>Total Due</b>", st["body"]), Paragraph(f"<b>{_fmt_money(total)}</b>", st["right"])])
    tbl = Table(data, colWidths=[4.95 * inch, 1.8 * inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), LIGHT),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#E5E7EB")),
        ("LINEABOVE", (0, -1), (-1, -1), 1, NAVY),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 18))
    story.append(Paragraph(
        f"Please remit payment within the stated terms ({payment_terms or 'Net-30'}). "
        f"Reference invoice <b>{invoice_no}</b> on all payments. "
        f"Questions? Email info@3lakeslogistics.com or call {PHONE}.",
        st["muted"],
    ))
    return _build(story, f"Invoice {invoice_no}")


def render_rate_confirmation_pdf(*, load: dict) -> bytes:
    """Carrier rate confirmation for a load."""
    st = _styles()
    origin = ", ".join(filter(None, [load.get("origin_city"), load.get("origin_state")])) or load.get("origin", "—")
    dest = ", ".join(filter(None, [load.get("dest_city"), load.get("dest_state")])) or load.get("destination", "—")
    rate_total = load.get("rate_total") or load.get("rate") or 0
    pct = load.get("dispatch_pct") or "5"
    story: list = [
        Paragraph("RATE CONFIRMATION", st["doctitle"]),
        Spacer(1, 6),
        Paragraph(f"Load #{load.get('load_number', '—')}", st["h"]),
        HRFlowable(width="100%", thickness=1, color=GOLD, spaceAfter=10),
    ]
    rows = [
        ("Origin", str(origin)),
        ("Destination", str(dest)),
        ("Pickup Date", _fmt_date(load.get("pickup_at"))),
        ("Commodity", load.get("commodity") or "General Freight"),
        ("Miles", str(load.get("miles") or "—")),
        ("Rate Total", _fmt_money(rate_total)),
        ("Dispatch Fee", f"{_fmt_money(load.get('dispatch_fee') or 0)} ({pct}%)"),
        ("Carrier", load.get("carrier_name") or "—"),
        ("Driver", load.get("driver_name") or "—"),
    ]
    story.append(_kv_table(rows, st))
    story.append(Spacer(1, 16))
    story.append(Paragraph(
        "By accepting this load, carrier agrees to all applicable terms of "
        f"{COMPANY}. Carrier must maintain required insurance minimums and comply "
        "with all FMCSA/DOT regulations.",
        st["muted"],
    ))
    return _build(story, f"Rate Confirmation — Load {load.get('load_number', '')}")


# ── Storage ─────────────────────────────────────────────────────────────────────

def store_document_bytes(
    storage_path: str,
    data: bytes,
    *,
    content_type: str = "application/pdf",
    bucket: str = "documents",
) -> bool:
    """Upload generated document bytes to Supabase Storage.

    Tries upload first; falls back to update (overwrite) so regenerating a
    document doesn't fail on an already-existing path. Returns True on success.
    """
    storage = get_supabase().storage.from_(bucket)
    try:
        storage.upload(
            path=storage_path,
            file=data,
            file_options={"content-type": content_type, "upsert": "true"},
        )
        return True
    except Exception as exc:  # noqa: BLE001 — path may already exist; try overwrite
        try:
            storage.update(path=storage_path, file=data, file_options={"content-type": content_type})
            return True
        except Exception as exc2:  # noqa: BLE001
            log.warning("store_document_bytes failed for %s: %s / %s", storage_path, exc, exc2)
            return False
