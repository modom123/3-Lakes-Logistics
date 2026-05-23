"""EDI endpoints — receive inbound X12 and send outbound transactions.

Endpoints
─────────
  POST /api/edi/receive         Broker posts raw X12 EDI (204, 990, 214, 210)
  POST /api/edi/send/990        3LL sends a 990 Accept/Decline
  POST /api/edi/send/214        3LL sends a 214 Shipment Status
  POST /api/edi/send/210        3LL sends a 210 Invoice
  GET  /api/edi/log             Recent EDI transactions (all brokers)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse

from ..edi import build_210, build_214, build_990, handle_inbound_edi
from ..logging_service import get_logger
from ..models.broker import (
    EDI210Invoice, EDI214StatusUpdate, EDI990Response, EDIInboundRequest,
)
from ..supabase_client import get_supabase
from .deps import require_bearer

log = get_logger("3ll.edi.routes")
router = APIRouter(dependencies=[Depends(require_bearer)])

# Public receive endpoint (brokers POST here — no Bearer, just validate partner ID)
public_router = APIRouter()


@public_router.post("/receive")
async def receive_edi(request: Request) -> dict:
    """Accept raw X12 EDI from a broker.

    Content-Type can be text/plain, application/edi-x12, or application/json.
    For JSON, expects {raw_edi, broker_mc?, edi_partner_id?}.
    """
    content_type = request.headers.get("content-type", "")

    if "json" in content_type:
        body = await request.json()
        raw_edi      = body.get("raw_edi", "")
        broker_mc    = body.get("broker_mc")
        partner_id   = body.get("edi_partner_id")
    else:
        raw_bytes = await request.body()
        raw_edi   = raw_bytes.decode("utf-8", errors="replace")
        broker_mc  = request.headers.get("X-Broker-MC")
        partner_id = request.headers.get("X-EDI-Partner-ID")

    if not raw_edi.strip():
        raise HTTPException(400, "empty EDI payload")

    result = handle_inbound_edi(raw_edi, broker_mc=broker_mc, edi_partner_id=partner_id)

    response: dict = {
        "ok":               result["ok"],
        "transaction_set":  result["transaction_set"],
        "load_number":      result["load_number"],
        "contract_id":      result.get("contract_id"),
        "message":          result["message"],
    }
    if result.get("outbound_990"):
        response["acknowledgment_990"] = result["outbound_990"]

    return response


# ── Authenticated outbound sends ──────────────────────────────────────────────

@router.post("/send/990", response_class=PlainTextResponse)
def send_990(resp: EDI990Response, broker_id: str | None = None) -> str:
    """Generate and return a 990 Response to Load Tender as raw X12."""
    partner_id, qualifier = _get_partner(broker_id)
    edi_str = build_990(resp, partner_id=partner_id, qualifier=qualifier)
    _log_outbound("990", broker_id, resp.load_number, edi_str)
    return edi_str


@router.post("/send/214", response_class=PlainTextResponse)
def send_214(status_update: EDI214StatusUpdate, broker_id: str | None = None) -> str:
    """Generate and return a 214 Shipment Status as raw X12."""
    partner_id, qualifier = _get_partner(broker_id)
    edi_str = build_214(status_update, partner_id=partner_id, qualifier=qualifier)
    _log_outbound("214", broker_id, status_update.load_number, edi_str)
    return edi_str


@router.post("/send/210", response_class=PlainTextResponse)
def send_210(invoice: EDI210Invoice, broker_id: str | None = None) -> str:
    """Generate and return a 210 Freight Invoice as raw X12."""
    partner_id, qualifier = _get_partner(broker_id)
    edi_str = build_210(invoice, partner_id=partner_id, qualifier=qualifier)
    _log_outbound("210", broker_id, invoice.load_number, edi_str)
    return edi_str


@router.get("/log")
def edi_log(limit: int = 200) -> dict:
    """Recent EDI transactions across all brokers."""
    res = (
        get_supabase().table("broker_edi_log")
        .select("id, broker_id, direction, transaction_set, load_number, status, error_detail, created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"count": len(res.data or []), "items": res.data or []}


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_partner(broker_id: str | None) -> tuple[str, str]:
    if not broker_id:
        return "BROKER", "02"
    res = get_supabase().table("brokers").select("edi_partner_id, edi_qualifier").eq("id", broker_id).maybe_single().execute()
    if res.data:
        return res.data.get("edi_partner_id") or "BROKER", res.data.get("edi_qualifier") or "02"
    return "BROKER", "02"


def _log_outbound(ts: str, broker_id: str | None, load_number: str | None, raw: str) -> None:
    try:
        get_supabase().table("broker_edi_log").insert({
            "broker_id":       broker_id,
            "direction":       "outbound",
            "transaction_set": ts,
            "load_number":     load_number,
            "raw_edi":         raw[:5000],
            "status":          "sent",
        }).execute()
    except Exception as exc:
        log.warning("edi_outbound_log failed: %s", exc)
