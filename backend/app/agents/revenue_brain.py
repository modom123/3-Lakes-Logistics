"""Revenue Brain — financial pattern and period intelligence.

Sofia writes reconciliation metrics each run. Eleanor Wei (when built)
will add payment-behavior patterns. Victoria and the Commander read this
for financial strategic context.

Period keys:
    'all_time'       — rolling lifetime aggregate
    '2026-05'        — YYYY-MM monthly snapshots
    '2026-Q2'        — YYYY-QN quarterly
    'rolling_30d'    — sliding 30-day window (Sofia overwrites each run)

Metric keys:
    'ar_outstanding'   — total open AR, overdue count
    'collection_rate'  — % invoices paid, sample size
    'missing_invoices' — loads without invoices
    'monthly_revenue'  — total collected in period
    'load_revenue'     — load-level rate data
    'days_to_pay'      — average payment lag (future: when payment timestamps exist)

API:
    record_metric(period_key, metric_key, value, ...)
    recall_metric(period_key, metric_key)
    get_period_snapshot(period_key)
    get_revenue_intelligence()
"""
from __future__ import annotations

from typing import Any

from ..logging_service import get_logger
from ..supabase_client import get_supabase

log = get_logger("revenue.brain")


# ── Write ─────────────────────────────────────────────────────────────────────

def record_metric(
    period_key: str,
    metric_key: str,
    value: Any,
    *,
    agent: str,
    confidence: float = 0.5,
    summary: str | None = None,
) -> None:
    """Upsert a revenue metric for a period. Confidence reinforces on repeat writes.
    Never raises.
    """
    try:
        sb = get_supabase()
        existing = (
            sb.table("revenue_brain")
            .select("id,confidence")
            .eq("period_key", period_key)
            .eq("metric_key", metric_key)
            .limit(1)
            .execute()
        )
        met_val = value if isinstance(value, (dict, list)) else {"value": value}

        if existing.data:
            old_conf = float(existing.data[0].get("confidence") or 0.5)
            new_conf = min(1.0, old_conf + (1 - old_conf) * 0.15)
            (
                sb.table("revenue_brain")
                .update({
                    "metric_value": met_val,
                    "confidence":   round(new_conf, 3),
                    "source_agent": agent,
                    "summary":      summary,
                    "updated_at":   "now()",
                })
                .eq("period_key", period_key)
                .eq("metric_key", metric_key)
                .execute()
            )
        else:
            sb.table("revenue_brain").insert({
                "period_key":   period_key,
                "metric_key":   metric_key,
                "metric_value": met_val,
                "confidence":   round(max(0.0, min(1.0, confidence)), 3),
                "source_agent": agent,
                "summary":      summary,
            }).execute()

        log.debug("revenue brain write: %s/%s agent=%s", period_key, metric_key, agent)
    except Exception as e:  # noqa: BLE001
        log.warning("revenue brain write failed (%s/%s): %s", period_key, metric_key, e)


# ── Read ──────────────────────────────────────────────────────────────────────

def recall_metric(period_key: str, metric_key: str) -> dict[str, Any] | None:
    try:
        res = (
            get_supabase().table("revenue_brain")
            .select("period_key,metric_key,metric_value,confidence,source_agent,summary,updated_at")
            .eq("period_key", period_key)
            .eq("metric_key", metric_key)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception as e:  # noqa: BLE001
        log.warning("revenue brain recall failed (%s/%s): %s", period_key, metric_key, e)
        return None


def recall_value(period_key: str, metric_key: str, default: Any = None) -> Any:
    m = recall_metric(period_key, metric_key)
    return m["metric_value"] if m else default


def get_period_snapshot(period_key: str) -> dict[str, Any]:
    """All metrics for a given period."""
    try:
        res = (
            get_supabase().table("revenue_brain")
            .select("period_key,metric_key,metric_value,confidence,source_agent,summary,updated_at")
            .eq("period_key", period_key)
            .order("confidence", desc=True)
            .execute()
        )
        rows = res.data or []
        by_metric = {r["metric_key"]: r["metric_value"] for r in rows}
        return {
            "period_key": period_key,
            "metric_count": len(rows),
            "metrics": by_metric,
            "rows": rows,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("revenue brain period snapshot failed (%s): %s", period_key, e)
        return {"period_key": period_key, "metric_count": 0, "metrics": {}, "rows": []}


def get_revenue_intelligence() -> dict[str, Any]:
    """Full financial intelligence snapshot — all periods, all metrics.
    Used by Victoria and the Commander for strategic financial context.
    """
    try:
        res = (
            get_supabase().table("revenue_brain")
            .select("period_key,metric_key,metric_value,confidence,source_agent,summary,updated_at")
            .order("updated_at", desc=True)
            .execute()
        )
        rows = res.data or []

        # Group by period
        by_period: dict[str, dict] = {}
        for r in rows:
            pk = r["period_key"]
            by_period.setdefault(pk, {})[r["metric_key"]] = r["metric_value"]

        # Pull key signals for quick Commander read
        all_time   = by_period.get("all_time", {})
        rolling_30 = by_period.get("rolling_30d", {})

        ar   = all_time.get("ar_outstanding",   {})
        coll = all_time.get("collection_rate",  {})
        miss = all_time.get("missing_invoices", {})

        return {
            "total_metrics":         len(rows),
            "periods_tracked":       len(by_period),
            "ar_outstanding":        ar.get("amount", 0),
            "collection_rate_pct":   coll.get("rate_pct", 0),
            "missing_invoices":      miss.get("count", 0),
            "rolling_30d_revenue":   rolling_30.get("monthly_revenue", {}).get("total", 0),
            "by_period":             by_period,
            "rows":                  rows,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("get_revenue_intelligence failed: %s", e)
        return {
            "total_metrics": 0, "periods_tracked": 0,
            "ar_outstanding": 0, "collection_rate_pct": 0,
            "missing_invoices": 0, "rolling_30d_revenue": 0,
            "by_period": {}, "rows": [],
        }
