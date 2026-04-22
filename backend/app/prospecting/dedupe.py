"""Step 45: duplicate checker. Compares on DOT/MC — these are unique in FMCSA."""
from __future__ import annotations

from ..supabase_client import get_supabase


def is_duplicate(dot: str | None, mc: str | None) -> bool:
    if not dot and not mc:
        return False
    sb = get_supabase()
    if dot:
        r = sb.table("leads").select("id").eq("dot_number", dot).limit(1).execute()
        if r.data:
            return True
        r = sb.table("active_carriers").select("id").eq("dot_number", dot).limit(1).execute()
        if r.data:
            return True
    if mc:
        r = sb.table("leads").select("id").eq("mc_number", mc).limit(1).execute()
        if r.data:
            return True
        r = sb.table("active_carriers").select("id").eq("mc_number", mc).limit(1).execute()
        if r.data:
            return True
    return False
