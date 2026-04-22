"""Step 47: Vapi/ElevenLabs cold-call script for Vance."""
from __future__ import annotations

VANCE_COLD_CALL_SCRIPT = """\
[opener]
"Hey — this is Vance with 3 Lakes Logistics. Quick 30 seconds. You running your own authority right now, or leased on?"

[founders pitch]
"We just opened 1,000 Founders spots — flat $200/mo for full dispatch, load boards, compliance monitoring, weekly ACH payouts. Rate is locked for life. 800+ carriers have already grabbed spots in Dry Van and Reefer."

[qualifier]
"How many trucks you running, and what trailer type are you on?"

[close]
"I can hold a slot in {trailer_type} for you for 24 hours — that's one of {remaining_in_category} remaining. Can I text you the 1-click signup link right now?"
"""


def render_script(lead: dict) -> str:
    return VANCE_COLD_CALL_SCRIPT.format(
        trailer_type=(lead.get("equipment_types") or ["Dry Van"])[0],
        remaining_in_category=lead.get("remaining_in_category", "limited"),
    )
