"""Earnings Aggregator — Aggregates a light fleet driver's earnings across platforms.

Reads from the light_vehicle_trips table (source, rate_total, driver_payout,
completed_at) and groups results by platform/source.

Functions:
  get_earnings           totals for a driver for a given period
  get_platform_breakdown per-platform trip count + gross/net + color
  get_weekly_trend       last N weeks with gross per week
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase

_NAME = "earnings_aggregator"

# Platform color codes
_PLATFORM_COLORS: dict[str, str] = {
    "3lakes":      "#3b82f6",
    "curri":       "#16a34a",
    "roadie":      "#b45309",
    "amazon_flex": "#d97706",
    "spark":       "#0891b2",
    "doordash":    "#dc2626",
    "goshare":     "#7c3aed",
    "internal":    "#3b82f6",
}

_DRIVER_PAYOUT_RATE = 0.85  # fallback when driver_payout is null


# ── Helpers ───────────────────────────────────────────────────────────────────

def _db():
    try:
        return get_supabase()
    except Exception:  # noqa: BLE001
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _period_start(period: str) -> datetime:
    """Return the UTC start datetime for the given period label."""
    now = _now()
    if period == "week":
        # Monday of the current week
        start = now - timedelta(days=now.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "ytd":
        return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    # Default: current week
    start = now - timedelta(days=now.weekday())
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def _week_start(weeks_ago: int = 0) -> datetime:
    """Return Monday 00:00 UTC for 'weeks_ago' weeks back."""
    now = _now()
    monday = now - timedelta(days=now.weekday()) - timedelta(weeks=weeks_ago)
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def _fetch_trips(driver_id: str, since: datetime) -> list[dict]:
    """Fetch completed trips for a driver since the given datetime."""
    sb = _db()
    if not sb:
        return []
    try:
        rows = (
            sb.table("light_vehicle_trips")
            .select("id,source,rate_total,driver_payout,completed_at")
            .eq("driver_id", driver_id)
            .eq("status", "completed")
            .gte("completed_at", since.isoformat())
            .execute()
        ).data or []
        return rows
    except Exception as e:  # noqa: BLE001
        log_agent(_NAME, "fetch_trips_error", error=str(e)[:200])
        return []


def _net_payout(trip: dict) -> float:
    """Return net payout for a single trip, estimating if driver_payout is null."""
    payout = trip.get("driver_payout")
    if payout is not None:
        return float(payout)
    gross = trip.get("rate_total") or 0.0
    return round(float(gross) * _DRIVER_PAYOUT_RATE, 2)


# ── Core functions ─────────────────────────────────────────────────────────────

def get_earnings(driver_id: str, period: str = "week") -> dict[str, Any]:
    """
    Return aggregated earnings totals for a driver over the given period.

    period: 'week' (current Mon-Sun), 'month' (current calendar month),
            'ytd' (Jan 1 to now)

    Returns:
      {
        "period": str,
        "period_start": str,   # ISO datetime
        "total_trips": int,
        "gross": float,        # sum of rate_total
        "net": float,          # sum of driver_payout (estimated where null)
        "platforms": list[str] # unique platforms active in the period
      }
    """
    since = _period_start(period)
    trips = _fetch_trips(driver_id, since)

    gross = sum(float(t.get("rate_total") or 0) for t in trips)
    net   = sum(_net_payout(t) for t in trips)
    platforms = list({t.get("source") or "unknown" for t in trips})

    return {
        "period":       period,
        "period_start": since.isoformat(),
        "total_trips":  len(trips),
        "gross":        round(gross, 2),
        "net":          round(net, 2),
        "platforms":    platforms,
    }


def get_platform_breakdown(driver_id: str, period: str = "week") -> list[dict[str, Any]]:
    """
    Return per-platform breakdown for a driver over the given period.

    Returns a list of:
      {
        "platform": str,
        "trips": int,
        "gross": float,
        "net": float,
        "color": str   # hex color for the platform
      }
    sorted by gross descending.
    """
    since = _period_start(period)
    trips = _fetch_trips(driver_id, since)

    # Aggregate by platform
    agg: dict[str, dict] = {}
    for t in trips:
        platform = t.get("source") or "unknown"
        if platform not in agg:
            agg[platform] = {"trips": 0, "gross": 0.0, "net": 0.0}
        agg[platform]["trips"] += 1
        agg[platform]["gross"] += float(t.get("rate_total") or 0)
        agg[platform]["net"]   += _net_payout(t)

    breakdown = [
        {
            "platform": platform,
            "trips":    data["trips"],
            "gross":    round(data["gross"], 2),
            "net":      round(data["net"], 2),
            "color":    _PLATFORM_COLORS.get(platform, "#6b7280"),
        }
        for platform, data in agg.items()
    ]

    breakdown.sort(key=lambda x: x["gross"], reverse=True)
    return breakdown


def get_weekly_trend(driver_id: str, weeks: int = 4) -> list[dict[str, Any]]:
    """
    Return the last N complete + current weeks with gross earnings per week.

    Returns a list of N dicts (oldest first):
      {
        "week_start": str,   # ISO date string (Monday)
        "week_label": str,   # e.g. "May 19"
        "trips": int,
        "gross": float,
        "net": float,
      }
    """
    # Fetch trips covering the entire lookback window
    oldest_start = _week_start(weeks - 1)
    trips = _fetch_trips(driver_id, oldest_start)

    # Build one bucket per week
    trend: list[dict] = []
    for w in range(weeks - 1, -1, -1):  # oldest → newest
        wstart = _week_start(w)
        wend   = wstart + timedelta(weeks=1)

        week_trips = [
            t for t in trips
            if t.get("completed_at")
            and wstart.isoformat() <= t["completed_at"] < wend.isoformat()
        ]

        gross = sum(float(t.get("rate_total") or 0) for t in week_trips)
        net   = sum(_net_payout(t) for t in week_trips)

        trend.append({
            "week_start": wstart.date().isoformat(),
            "week_label": wstart.strftime("%b %-d"),
            "trips":      len(week_trips),
            "gross":      round(gross, 2),
            "net":        round(net, 2),
        })

    return trend
