"""Step 55: Referral loop for non-converting leads.

If a lead lands in stage='dead' with a valid phone, ask them if they
know another owner-op who might be a fit. Reward: $200 credit on month 1.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase

REFERRAL_SMS = (
    "Hey {first_name} — no worries, we get it. "
    "Quick ask: know anyone running 1-5 trucks who'd want flat $200/mo dispatch? "
    "Send them my way and month 1 is on us. Reply STOP to opt out."
)


def compose(lead: dict) -> str:
    first = (lead.get("first_name") or
             (lead.get("contact_name") or "there").split()[0])
    return REFERRAL_SMS.format(first_name=first)


def send(lead_id: str) -> dict[str, Any]:
    """Send referral-ask SMS to a dead/non-converting lead."""
    sb = get_supabase()
    lead = (sb.table("leads").select("*")
              .eq("id", lead_id).maybe_single().execute().data)
    if not lead:
        return {"ok": False, "reason": "lead_not_found"}

    if lead.get("do_not_contact"):
        return {"ok": False, "reason": "do_not_contact"}

    phone = lead.get("phone") or lead.get("owner_phone")
    if not phone:
        return {"ok": False, "reason": "no_phone"}

    from .sms_compliance import compliance_footer
    message = compose(lead) + "\n" + compliance_footer()

    from ..agents.signal import _send_sms
    result = _send_sms(phone, message)

    now = datetime.now(timezone.utc).isoformat()
    sb.table("leads").update({"last_touch_at": now}).eq("id", lead_id).execute()

    log_agent("nova", "referral_sms",
              payload={"lead_id": lead_id, "phone": phone}, result=result)
    return {"ok": True, "lead_id": lead_id, "phone": phone, "sms": result}


def request_referrals(limit: int = 50) -> dict[str, Any]:
    """Send referral asks to dead leads that have a phone on file."""
    sb = get_supabase()
    leads = (
        sb.table("leads")
          .select("id")
          .eq("stage", "dead")
          .eq("do_not_contact", False)
          .limit(limit)
          .execute().data or []
    )
    sent = failed = 0
    for row in leads:
        result = send(row["id"])
        if result.get("ok"):
            sent += 1
        else:
            failed += 1
    log_agent("nova", "referral_batch",
              payload={"total": len(leads), "sent": sent, "failed": failed})
    return {"total": len(leads), "sent": sent, "failed": failed}
