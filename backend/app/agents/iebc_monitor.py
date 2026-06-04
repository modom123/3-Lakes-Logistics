"""IEBC Cost Monitor — tracks system operating costs and reports to Mark Odom.

The IEBC (Internal Enterprise Business Control) cost team monitors:
  · API usage costs  — Anthropic, Bland AI, Twilio, OpenRouter, Google, Checkr
  · Subscription fees — Supabase, Render, Vercel, DAT, Airtable, etc.
  · Budget health    — fires alerts when services approach/exceed monthly caps
  · Weekly reports   — every Monday, sends a full cost breakdown to Mark Odom

Scheduled runs:
  Daily  08:45 UTC — budget check + alerts
  Monday 09:30 UTC — full weekly cost report → mark@3lakeslogistics.com
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..logging_service import get_logger, log_agent
from ..cost_tracking.reporter import get_mtd_summary, get_budget_alerts, send_report

log = get_logger("iebc.monitor")


def run_budget_check() -> dict[str, Any]:
    """Check budgets and fire alerts for over-threshold services."""
    alerts = get_budget_alerts()

    critical = [a for a in alerts if a["severity"] == "critical"]
    warnings = [a for a in alerts if a["severity"] == "warning"]

    result = {
        "agent": "iebc_monitor",
        "action": "budget_check",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alerts_total": len(alerts),
        "critical": len(critical),
        "warnings": len(warnings),
        "details": alerts,
    }

    if critical:
        msg = ", ".join(f"{a['service_or_category']} {a['pct_used']}%" for a in critical)
        log.error("IEBC BUDGET CRITICAL: %s", msg)
    elif warnings:
        msg = ", ".join(f"{a['service_or_category']} {a['pct_used']}%" for a in warnings)
        log.warning("IEBC BUDGET WARNING: %s", msg)
    else:
        log.info("IEBC budget check: all services within budget")

    log_agent(
        "iebc_monitor",
        "budget_check",
        payload={"threshold_check": True},
        result=f"critical={len(critical)} warnings={len(warnings)} total_alerts={len(alerts)}",
        error=f"OVER BUDGET: {[a['service_or_category'] for a in critical]}" if critical else None,
    )

    return result


def run_weekly_report() -> dict[str, Any]:
    """Generate and send the weekly cost report to Mark Odom and IEBC team."""
    log.info("IEBC: generating weekly cost report")

    summary = get_mtd_summary()
    alerts = get_budget_alerts()
    period_label = datetime.now(timezone.utc).strftime("%Y-%m (Week of %b %d)")

    send_result = send_report(summary, alerts, period_label=period_label)

    result = {
        "agent": "iebc_monitor",
        "action": "weekly_report",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "period": summary["period"],
        "total_cost_usd": summary["total_cost_usd"],
        "api_cost_usd": summary["api_cost_usd"],
        "subscription_cost_usd": summary["subscription_cost_usd"],
        "alerts_count": len(alerts),
        "email_sent": send_result.get("sent", False),
        "recipients": send_result.get("recipients", []),
    }

    log_agent(
        "iebc_monitor",
        "weekly_report",
        payload={"period": summary["period"]},
        result=(
            f"total=${summary['total_cost_usd']:.2f} "
            f"api=${summary['api_cost_usd']:.2f} "
            f"subs=${summary['subscription_cost_usd']:.2f} "
            f"alerts={len(alerts)} "
            f"sent={send_result.get('sent', False)}"
        ),
    )

    return result


def run(payload: dict[str, Any]) -> dict[str, Any]:
    """Entry point — dispatch based on payload action or default to budget check."""
    action = payload.get("action", "budget_check")
    if action == "weekly_report":
        return run_weekly_report()
    return run_budget_check()
