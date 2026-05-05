"""Driver communication routes — SMS via Twilio, inbound webhook, thread history.

Endpoints
─────────
  POST /api/comms/send            → send SMS to a driver (dispatcher use)
  POST /api/comms/load_offer      → blast load offer SMS to list of driver phones
  GET  /api/comms/thread/{phone}  → conversation history for a driver phone
  GET  /api/comms/threads         → all driver conversations (last message each)
  POST /api/comms/webhook/twilio  → Twilio inbound SMS webhook (no auth)
  PATCH /api/comms/read/{phone}   → mark thread as read
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from ..logging_service import get_logger, log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from .deps import require_bearer

log = get_logger("3ll.comms")

router = APIRouter()                               # public — Twilio webhook
router_auth = APIRouter(dependencies=[Depends(require_bearer)])  # bearer-protected


# ── helpers ───────────────────────────────────────────────────────────────────

def _e164(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return "+" + digits if not phone.startswith("+") else phone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _send_twilio(to: str, body: str) -> dict:
    s = get_settings()
    if s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number:
        try:
            from twilio.rest import Client  # type: ignore
            sid = Client(s.twilio_account_sid, s.twilio_auth_token).messages.create(
                body=body, from_=s.twilio_from_number, to=to
            ).sid
            return {"sent": True, "sid": sid}
        except Exception as exc:
            log.warning("Twilio send failed: %s", exc)
            return {"sent": False, "error": str(exc)}
    return {"sent": False, "note": "twilio_not_configured", "preview": body[:120]}


def _store(direction: str, phone: str, body: str,
           driver_id: str | None = None, load_id: str | None = None,
           msg_type: str = "text") -> None:
    try:
        get_supabase().table("driver_messages").insert({
            "direction": direction,
            "driver_phone": _e164(phone),
            "body": body,
            "driver_id": driver_id,
            "load_id": load_id,
            "msg_type": msg_type,
            "read": direction == "outbound",
            "created_at": _now(),
        }).execute()
    except Exception as exc:
        log.debug("driver_messages insert skipped: %s", exc)


# ── request models ────────────────────────────────────────────────────────────

class SendSMSReq(BaseModel):
    to: str
    body: str
    driver_id: str | None = None
    load_id: str | None = None


class LoadOfferReq(BaseModel):
    load_id: str
    load_number: str
    origin: str
    destination: str
    rate: float
    miles: float | None = None
    pickup_date: str | None = None
    driver_phones: list[str]


# ── authenticated routes ───────────────────────────────────────────────────────

@router_auth.post("/send")
def send_sms(req: SendSMSReq) -> dict:
    """Dispatcher sends an SMS to a driver."""
    phone = _e164(req.to)
    result = _send_twilio(phone, req.body)
    _store("outbound", phone, req.body, driver_id=req.driver_id, load_id=req.load_id)
    log_agent("signal", "sms.send", payload={"to": phone, "load_id": req.load_id}, result=result)
    return {**result, "to": phone}


@router_auth.post("/load_offer")
def send_load_offer(req: LoadOfferReq) -> dict:
    """Blast a load offer SMS to one or more driver phones."""
    rpm = f" · ${req.rate / req.miles:.2f}/mi" if req.miles and req.miles > 0 else ""
    body = (
        f"LOAD OFFER — 3 Lakes Logistics\n"
        f"Load #{req.load_number}\n"
        f"{req.origin} → {req.destination}\n"
        f"Rate: ${req.rate:,.0f}{rpm}\n"
        f"Pickup: {req.pickup_date or 'TBD'}\n"
        f"Reply YES to accept or NO to decline"
    )
    results = []
    for raw_phone in req.driver_phones:
        phone = _e164(raw_phone)
        r = _send_twilio(phone, body)
        _store("outbound", phone, body, load_id=req.load_id, msg_type="load_offer")
        results.append({"phone": phone, **r})

    sent_count = sum(1 for r in results if r.get("sent"))
    log_agent("signal", "load_offer.blast",
              payload={"load_id": req.load_id, "drivers": len(req.driver_phones)},
              result=f"sent={sent_count}")
    return {"ok": True, "load_id": req.load_id, "sent": sent_count, "results": results}


@router_auth.get("/thread/{driver_phone}")
def get_thread(driver_phone: str, limit: int = 60) -> dict:
    """Return full SMS conversation with a driver."""
    phone = _e164(driver_phone)
    try:
        rows = (
            get_supabase()
            .table("driver_messages")
            .select("*")
            .eq("driver_phone", phone)
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        ).data or []
    except Exception:
        rows = []
    return {"messages": rows, "phone": phone}


@router_auth.get("/threads")
def list_threads() -> dict:
    """Return last message per driver for the conversations sidebar."""
    try:
        rows = (
            get_supabase()
            .table("driver_messages")
            .select("driver_phone,body,direction,created_at,read,msg_type,load_id")
            .order("created_at", desc=True)
            .limit(300)
            .execute()
        ).data or []
        seen: dict[str, dict] = {}
        unread: dict[str, int] = {}
        for r in rows:
            p = r["driver_phone"]
            if p not in seen:
                seen[p] = r
            if not r.get("read") and r.get("direction") == "inbound":
                unread[p] = unread.get(p, 0) + 1
        threads = []
        for p, last in seen.items():
            threads.append({**last, "unread": unread.get(p, 0)})
        return {"threads": threads}
    except Exception:
        return {"threads": []}


@router_auth.patch("/read/{driver_phone}")
def mark_read(driver_phone: str) -> dict:
    phone = _e164(driver_phone)
    try:
        get_supabase().table("driver_messages").update({"read": True}).eq(
            "driver_phone", phone
        ).eq("direction", "inbound").execute()
    except Exception:
        pass
    return {"ok": True, "phone": phone}


# ── Twilio inbound webhook (no auth required — Twilio POSTs here) ─────────────

@router.post("/webhook/twilio")
async def twilio_inbound(request: Request) -> Response:
    """Receive inbound driver SMS from Twilio; reply via TwiML."""
    form = await request.form()
    from_phone = form.get("From", "")
    body = (form.get("Body") or "").strip()

    _store("inbound", from_phone, body)
    log_agent("signal", "sms.inbound",
              payload={"from": from_phone, "body": body[:120]},
              result="received")

    upper = body.upper()
    if upper in ("YES", "Y", "ACCEPT", "OK", "YEP", "YEAH"):
        reply = "Load accepted! Your dispatcher will send details shortly. Drive safe. — 3 Lakes"
        log_agent("signal", "load.accepted_via_sms", payload={"from": from_phone}, result="accepted")
    elif upper in ("NO", "N", "DECLINE", "PASS", "NOPE"):
        reply = "No problem — we'll reach out on the next one. — 3 Lakes"
    elif upper in ("STATUS", "?"):
        reply = "For your current load status open the 3 Lakes Driver app or reply with your load number."
    else:
        reply = "Message received! Your dispatcher will respond shortly. — 3 Lakes Logistics"

    twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{reply}</Message></Response>'
    return Response(content=twiml, media_type="application/xml")
