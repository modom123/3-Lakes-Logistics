"""Twilio SMS (step 86). Outbound + STOP handling."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

import httpx

from ..logging_service import get_logger
from ..settings import get_settings

_log = get_logger("3ll.sms")


def send_sms(to: str, body: str, *, carrier_id: str | None = None) -> dict:
    s = get_settings()
    if not (s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number):
        return {"status": "stub", "reason": "twilio_not_configured"}
    if _is_opted_out(to):
        return {"status": "blocked", "reason": "opted_out"}
    url = f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json"
    try:
        r = httpx.post(
            url,
            auth=(s.twilio_account_sid, s.twilio_auth_token),
            data={"To": to, "From": s.twilio_from_number, "Body": body},
            timeout=15,
        )
        r.raise_for_status()
        sid = (r.json() or {}).get("sid")
        _record("out", to, body, sid, carrier_id)
        return {"status": "sent", "sid": sid}
    except Exception as exc:  # noqa: BLE001
        _log.exception("twilio send failed")
        return {"status": "error", "error": str(exc)}


def handle_inbound(from_: str, body: str) -> Literal["opted_out", "opted_in", "received"]:
    norm = (body or "").strip().upper()
    if norm in {"STOP", "STOPALL", "UNSUBSCRIBE", "QUIT", "CANCEL", "END"}:
        _set_opt_out(from_, True)
        return "opted_out"
    if norm in {"START", "UNSTOP", "YES"}:
        _set_opt_out(from_, False)
        return "opted_in"
    _record("in", from_, body, None, None)
    return "received"


def _record(direction: str, phone: str, body: str, sid: str | None, carrier_id: str | None) -> None:
    try:
        from ..supabase_client import get_supabase
        get_supabase().table("sms_log").insert({
            "direction": direction, "phone": phone, "body": body,
            "provider_sid": sid, "carrier_id": carrier_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as exc:  # noqa: BLE001
        _log.warning("sms_log insert failed: %s", exc)


def _is_opted_out(phone: str) -> bool:
    try:
        from ..supabase_client import get_supabase
        rows = (
            get_supabase().table("sms_opt_out")
            .select("phone").eq("phone", phone).limit(1).execute().data or []
        )
        return bool(rows)
    except Exception:  # noqa: BLE001
        return False


def _set_opt_out(phone: str, opted_out: bool) -> None:
    try:
        from ..supabase_client import get_supabase
        sb = get_supabase()
        if opted_out:
            sb.table("sms_opt_out").upsert({"phone": phone}).execute()
        else:
            sb.table("sms_opt_out").delete().eq("phone", phone).execute()
    except Exception as exc:  # noqa: BLE001
        _log.warning("opt-out toggle failed: %s", exc)
