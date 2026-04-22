"""Step 56: Daily digest email to the Commander."""
from __future__ import annotations

from ..agents import beacon
from . import dashboard


def compose_digest() -> dict:
    funnel = dashboard.funnel()
    beacon_digest = beacon.generate_digest()
    return {
        "subject": f"3LL Daily — {beacon_digest['date']}",
        "funnel": funnel,
        "fleet": beacon_digest,
    }
