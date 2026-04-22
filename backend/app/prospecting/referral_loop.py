"""Step 55: Referral loop for non-converting leads.

If a lead lands in stage='dead' with a valid phone, ask them if they
know another owner-op who might be a fit. Reward: $200 credit on month 1.
"""
from __future__ import annotations

REFERRAL_SMS = (
    "Hey {first_name} — no worries, we get it. "
    "Quick ask: know anyone running 1-5 trucks who'd want flat $200/mo dispatch? "
    "Send them my way and month 1 is on us. Reply STOP to opt out."
)


def compose(lead: dict) -> str:
    return REFERRAL_SMS.format(first_name=(lead.get("contact_name") or "there").split()[0])
