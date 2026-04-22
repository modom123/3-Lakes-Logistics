"""Step 46: route leads to voice (Vance) vs SMS (Echo)."""
from __future__ import annotations

from typing import Literal

Channel = Literal["voice", "sms", "email", "hold"]


def pick_channel(lead: dict) -> Channel:
    if lead.get("do_not_contact"):
        return "hold"
    score = lead.get("score") or 0
    if lead.get("phone") and score >= 8:
        return "voice"
    if lead.get("phone") and score >= 5:
        return "sms"
    if lead.get("email"):
        return "email"
    return "hold"
