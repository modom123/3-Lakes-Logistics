"""Revenue Brain API — financial pattern and period intelligence.

GET  /api/revenue/brain              — full financial intelligence snapshot
GET  /api/revenue/brain/{period}     — all metrics for one period (e.g. '2026-05')
GET  /api/revenue/brain/{period}/{metric} — specific metric
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..agents import revenue_brain as rb
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


@router.get("/revenue/brain")
def revenue_intelligence() -> dict:
    """Full Revenue Brain snapshot — all periods and metrics. Commander + Victoria read this."""
    intel = rb.get_revenue_intelligence()
    return {"ok": True, **intel}


@router.get("/revenue/brain/{period_key}")
def period_snapshot(period_key: str) -> dict:
    """All financial metrics for a specific period key (e.g. 'all_time', '2026-05')."""
    snap = rb.get_period_snapshot(period_key)
    if snap["metric_count"] == 0:
        raise HTTPException(404, f"No revenue data for period '{period_key}'")
    return {"ok": True, **snap}


@router.get("/revenue/brain/{period_key}/{metric_key}")
def single_metric(period_key: str, metric_key: str) -> dict:
    """Single metric for a period."""
    m = rb.recall_metric(period_key, metric_key)
    if not m:
        raise HTTPException(404, f"No metric '{metric_key}' for period '{period_key}'")
    return {"ok": True, **m}
