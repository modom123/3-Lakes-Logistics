"""Signal — Outbound comms + emergency escalation (step 69)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..integrations.email import send_email
from ..integrations.slack import post_alert
from ..integrations.sms import send_sms
from ..logging_service import log_agent

EMERGENCY_KEYWORDS = {
    "breakdown", "accident", "crash", "dot", "inspection", "stop",
    "injury", "fuel out", "locked out", "hijack",
}


def classify(call_transcript: str) -> str:
    text = (call_transcript or "").lower()
    if any(kw in text for kw in EMERGENCY_KEYWORDS):
        return "emergency"
    if "dispatch" in text or "load" in text:
        return "dispatch"
    return "general"


def _send(channel: str, to: str, subject: str, body: str, carrier_id: str | None) -> dict:
    if channel == "sms":
        return send_sms(to, body, carrier_id=carrier_id)
    if channel == "email":
        return send_email(to, subject, body, tag="signal")
    return {"status": "skipped", "reason": f"unsupported channel {channel}"}


def run_cadence() -> dict[str, Any]:
    """Hourly cadence: step each nurture enrollment forward if due."""
    try:
        from ..supabase_client import get_supabase
        now = datetime.now(timezone.utc).isoformat()
        due = (
            get_supabase().table("nurture_enrollments")
            .select("id, lead_id, channel, to_address, step_index, body, subject, carrier_id")
            .lte("next_send_at", now).eq("status", "active").limit(500).execute()
        ).data or []
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    sent = 0
    for row in due:
        res = _send(row.get("channel") or "email", row.get("to_address") or "",
                    row.get("subject") or "3 Lakes Logistics",
                    row.get("body") or "", row.get("carrier_id"))
        ok = res.get("status") == "sent"
        try:
            from ..supabase_client import get_supabase
            get_supabase().table("nurture_enrollments").update({
                "last_sent_at": datetime.now(timezone.utc).isoformat(),
                "step_index": (row.get("step_index") or 0) + 1,
                "status": "active" if ok else "failed",
            }).eq("id", row["id"]).execute()
        except Exception as exc:  # noqa: BLE001
            log_agent("signal", "cadence_update_failed", error=str(exc))
        if ok:
            sent += 1
    log_agent("signal", "run_cadence", result=f"sent={sent}")
    return {"status": "ok", "sent": sent}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    kind = payload.get("kind") or "classify"
    if kind == "run_cadence":
        return {"agent": "signal", **run_cadence()}
    if kind == "send":
        return {"agent": "signal", **_send(
            payload.get("channel") or "email",
            payload.get("to") or "",
            payload.get("subject") or "",
            payload.get("body") or "",
            payload.get("carrier_id"),
        )}
    routing = classify(payload.get("transcript", ""))
    if routing == "emergency":
        post_alert(f":rotating_light: Signal flagged EMERGENCY — transcript: "
                   f"{(payload.get('transcript') or '')[:180]}")
    return {"agent": "signal", "status": "ok", "routing": routing}
