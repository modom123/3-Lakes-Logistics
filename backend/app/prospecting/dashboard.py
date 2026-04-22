"""Step 52: prospect conversion dashboard."""
from __future__ import annotations

from ..supabase_client import get_supabase


STAGES = ["new", "contacted", "engaged", "qualified", "converted", "nurture", "dead"]


def funnel() -> dict:
    sb = get_supabase()
    out: dict[str, int] = {}
    for stage in STAGES:
        res = sb.table("leads").select("id", count="exact").eq("stage", stage).execute()
        out[stage] = res.count or 0
    total = sum(out.values()) or 1
    out["conversion_rate_pct"] = round(100 * out["converted"] / total, 2)
    return out
