"""Step 50: Email nurture sequence (authored by Nexus).

7-email cadence over 30 days for leads that don't convert on first touch.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase

NURTURE_SEQUENCE = [
    {"day": 0,  "subject": "Your $200/mo dispatch spot (1 of 1,000)",
     "body_md": "**{first_name}** — we're holding a Founders slot for {company_name}...\n\n- Flat $200/mo, locked for life\n- Full-service dispatch, 10% on loads\n- Weekly ACH payouts via Settler\n\n**[Claim spot →](https://3lakeslogistics.com/?utm={utm})**"},
    {"day": 2,  "subject": "{first_name}, 3 questions about your trucks",
     "body_md": "Quick one — how many of your {fleet_size} trucks run dry van vs reefer? I can pull your DOT {dot_number} and show you what loads we're covering this week."},
    {"day": 5,  "subject": "Carriers like yours are averaging 2.8 $/mi",
     "body_md": "Here's the last 30 days of rates from {equipment_type} loads we dispatched."},
    {"day": 10, "subject": "Quick reminder — Founders price locks at 1,000",
     "body_md": "Dry Van has {dry_van_remaining} spots left. Reefer {reefer_remaining}. Once we hit 1,000 the price goes to market rate forever."},
    {"day": 15, "subject": "Your CSA snapshot",
     "body_md": "I pulled your SAFER report — here's what brokers see."},
    {"day": 22, "subject": "Last call — locking Founders",
     "body_md": "We close Founders pricing at 1,000 carriers. You're number {queue_position} in line."},
    {"day": 30, "subject": "Switching you to our quarterly newsletter",
     "body_md": "No worries on the Founders spot. We'll send rate snapshots quarterly. Reply anytime if you change your mind."},
]

_SAFE_VARS = {
    "first_name": "there",
    "company_name": "your company",
    "fleet_size": "your",
    "dot_number": "N/A",
    "equipment_type": "dry van",
    "dry_van_remaining": "200",
    "reefer_remaining": "50",
    "queue_position": "1",
    "utm": "",
}


def _render(template: str, lead: dict[str, Any], step_index: int) -> str:
    first = (lead.get("first_name") or
             (lead.get("contact_name") or "there").split()[0])
    equip = lead.get("equipment_types")
    equip_str = (", ".join(equip) if isinstance(equip, list) else equip) or "dry van"
    vars_ = {
        **_SAFE_VARS,
        "first_name":     first,
        "company_name":   lead.get("company_name") or "your company",
        "fleet_size":     str(lead.get("fleet_size") or "your"),
        "dot_number":     lead.get("dot_number") or "N/A",
        "equipment_type": equip_str,
        "queue_position": str(step_index + 1),
        "utm":            lead.get("id") or "",
    }
    try:
        return template.format(**vars_)
    except KeyError:
        return template


def send_nurture_email(lead_id: str) -> dict[str, Any]:
    """Send the next scheduled nurture email for this lead."""
    sb = get_supabase()
    lead = (sb.table("leads").select("*")
              .eq("id", lead_id).maybe_single().execute().data)
    if not lead:
        return {"ok": False, "reason": "lead_not_found"}

    if lead.get("do_not_contact"):
        return {"ok": False, "reason": "do_not_contact"}

    email = lead.get("email") or lead.get("owner_email")
    if not email:
        return {"ok": False, "reason": "no_email"}

    step_index: int = int(lead.get("nurture_step") or 0)
    if step_index >= len(NURTURE_SEQUENCE):
        sb.table("leads").update({"stage": "dead"}).eq("id", lead_id).execute()
        return {"ok": False, "reason": "nurture_complete", "stage": "dead"}

    step = NURTURE_SEQUENCE[step_index]
    subject = _render(step["subject"], lead, step_index)
    body = _render(step["body_md"], lead, step_index)

    from ..agents.nova import run as nova_run
    nr = nova_run({
        "action":       "nurture",
        "to_email":     email,
        "subject":      subject,
        "body":         body,
        "carrier_name": lead.get("company_name"),
        "first_name":   (lead.get("first_name") or
                         (lead.get("contact_name") or "there").split()[0]),
    })

    now = datetime.now(timezone.utc)
    next_step = step_index + 1
    if next_step < len(NURTURE_SEQUENCE):
        delay_days = NURTURE_SEQUENCE[next_step]["day"] - step["day"]
        next_touch = (now + timedelta(days=max(delay_days, 1))).isoformat()
    else:
        next_touch = None

    sb.table("leads").update({
        "nurture_step":         next_step,
        "last_nurture_sent_at": now.isoformat(),
        "last_touch_at":        now.isoformat(),
        "next_touch_at":        next_touch,
    }).eq("id", lead_id).execute()

    log_agent("nova", "nurture_sent",
              payload={"lead_id": lead_id, "step": step_index, "subject": subject})
    return {
        "ok": True,
        "lead_id":  lead_id,
        "step":     step_index,
        "subject":  subject,
        "email":    email,
        "nova":     nr,
    }


def enqueue_lead(lead_id: str) -> None:
    """Put a lead into the nurture sequence starting at step 0."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    get_supabase().table("leads").update({
        "stage":        "nurture",
        "nurture_step": 0,
        "next_touch_at": now,
    }).eq("id", lead_id).execute()


def run_due_nurtures() -> dict[str, Any]:
    """Process all leads whose next nurture email is now due."""
    now = datetime.now(timezone.utc).isoformat()
    sb = get_supabase()
    leads = (
        sb.table("leads")
          .select("id")
          .in_("stage", ["nurture", "contacted", "new"])
          .lte("next_touch_at", now)
          .eq("do_not_contact", False)
          .execute().data or []
    )
    sent = skipped = 0
    for row in leads:
        result = send_nurture_email(row["id"])
        if result.get("ok"):
            sent += 1
        else:
            skipped += 1
    log_agent("nova", "nurture_batch",
              payload={"total": len(leads), "sent": sent, "skipped": skipped})
    return {"total": len(leads), "sent": sent, "skipped": skipped}
