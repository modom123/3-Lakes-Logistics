"""Step 48: TCPA 'STOP' handling. All outbound SMS routes through this."""
from __future__ import annotations

STOP_WORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit"}
HELP_WORDS = {"help", "info"}


def is_opt_out(msg: str) -> bool:
    return (msg or "").strip().lower() in STOP_WORDS


def is_help_request(msg: str) -> bool:
    return (msg or "").strip().lower() in HELP_WORDS


def compliance_footer() -> str:
    return "Reply STOP to opt out. Msg&data rates may apply."


def mark_dnc(lead_id: str) -> None:
    from ..supabase_client import get_supabase
    get_supabase().table("leads").update({"do_not_contact": True, "stage": "dead"}).eq("id", lead_id).execute()
