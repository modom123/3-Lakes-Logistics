"""Sofia Rossi — Dir. Fin Automation (IEBC Step 56).
Reconciles invoices vs. delivered loads, flags missing invoices,
surfaces overdue AR, and reports financial cycle health.
"""
from __future__ import annotations

from typing import Any

from datetime import datetime, timezone

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from . import revenue_brain as rb


def reconcile(limit: int = 200) -> dict[str, Any]:
    sb = get_supabase()

    closed_loads = (
        sb.table("loads")
        .select("id,load_number,rate,status,carrier_id,created_at")
        .in_("status", ["delivered", "closed"])
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data or []
    )

    invoices = (
        sb.table("invoices")
        .select("load_id,amount,status,created_at")
        .limit(limit * 2)
        .execute()
        .data or []
    )

    invoiced_ids = {inv["load_id"] for inv in invoices if inv.get("load_id")}
    missing = [ld for ld in closed_loads if ld["id"] not in invoiced_ids]

    sent_invoices = [inv for inv in invoices if inv.get("status") == "sent"]
    paid_invoices = [inv for inv in invoices if inv.get("status") == "paid"]

    total_ar = sum(float(inv.get("amount") or 0) for inv in sent_invoices)
    total_collected = sum(float(inv.get("amount") or 0) for inv in paid_invoices)

    collection_rate = (
        round(total_collected / (total_collected + total_ar) * 100, 1)
        if (total_collected + total_ar) > 0 else 0.0
    )

    return {
        "loads_checked": len(closed_loads),
        "invoices_found": len(invoices),
        "missing_invoices": len(missing),
        "missing_load_numbers": [ld.get("load_number") for ld in missing[:10]],
        "overdue_invoices": len(sent_invoices),
        "total_ar_outstanding": round(total_ar, 2),
        "total_collected": round(total_collected, 2),
        "collection_rate_pct": collection_rate,
        "action_required": len(missing) > 0 or len(sent_invoices) > 5,
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    result = reconcile(limit=int(payload.get("limit", 200)))
    log_agent(
        "sofia", "reconcile",
        payload={},
        result=f"missing={result['missing_invoices']} ar=${result['total_ar_outstanding']} collection={result['collection_rate_pct']}%",
    )

    # Publish to Revenue Brain — all_time and rolling snapshots
    now = datetime.now(timezone.utc)
    month_key = now.strftime("%Y-%m")

    rb.record_metric("all_time", "ar_outstanding",
        {"amount": result["total_ar_outstanding"], "overdue_count": result["overdue_invoices"]},
        agent="sofia", confidence=0.8,
        summary=f"AR ${result['total_ar_outstanding']:,.0f} · {result['overdue_invoices']} overdue",
    )
    rb.record_metric("all_time", "collection_rate",
        {"rate_pct": result["collection_rate_pct"], "sample_size": result["invoices_found"]},
        agent="sofia", confidence=0.75,
        summary=f"{result['collection_rate_pct']}% collected · {result['invoices_found']} invoices sampled",
    )
    rb.record_metric("all_time", "missing_invoices",
        {"count": result["missing_invoices"], "load_numbers": result["missing_load_numbers"]},
        agent="sofia", confidence=0.85,
        summary=f"{result['missing_invoices']} loads missing invoices",
    )
    rb.record_metric(month_key, "ar_outstanding",
        {"amount": result["total_ar_outstanding"], "collection_rate_pct": result["collection_rate_pct"]},
        agent="sofia", confidence=0.75,
        summary=f"{month_key} AR ${result['total_ar_outstanding']:,.0f} · {result['collection_rate_pct']}% collected",
    )

    return {"agent": "sofia", **result}
