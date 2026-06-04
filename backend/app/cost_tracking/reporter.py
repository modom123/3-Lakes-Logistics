"""Cost Reporter — generates cost summaries and emails weekly reports to Mark Odom.

Weekly reports fire every Monday at 09:30 UTC.
Budget alerts fire any time a service crosses its alert threshold.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from typing import Any

from ..logging_service import get_logger, log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase

log = get_logger("cost.reporter")

MARK_ODOM_EMAIL = "mark@3lakeslogistics.com"
IEBC_EMAIL = "info@3lakeslogistics.com"

# Services that have fixed monthly subscriptions (populated in DB via seed migration)
_KNOWN_SUBSCRIPTIONS: list[dict] = [
    {"service": "supabase",  "plan_name": "Pro",          "amount_usd": 25.00,  "billing_cycle": "monthly"},
    {"service": "render",    "plan_name": "Standard",     "amount_usd": 25.00,  "billing_cycle": "monthly"},
    {"service": "vercel",    "plan_name": "Pro",           "amount_usd": 20.00,  "billing_cycle": "monthly"},
    {"service": "anthropic", "plan_name": "API (usage)",  "amount_usd": 0.00,   "billing_cycle": "usage"},
    {"service": "twilio",    "plan_name": "Pay-as-you-go","amount_usd": 0.00,   "billing_cycle": "usage"},
    {"service": "bland_ai",  "plan_name": "Pay-as-you-go","amount_usd": 0.00,   "billing_cycle": "usage"},
    {"service": "airtable",  "plan_name": "Pro",           "amount_usd": 20.00,  "billing_cycle": "monthly"},
    {"service": "adobe_sign","plan_name": "Business",     "amount_usd": 34.99,  "billing_cycle": "monthly"},
    {"service": "postmark",  "plan_name": "10K/mo",       "amount_usd": 15.00,  "billing_cycle": "monthly"},
    {"service": "sendgrid",  "plan_name": "Essentials",   "amount_usd": 19.95,  "billing_cycle": "monthly"},
    {"service": "checkr",    "plan_name": "Pay-per-check","amount_usd": 0.00,   "billing_cycle": "usage"},
    {"service": "firebase",  "plan_name": "Blaze",        "amount_usd": 25.00,  "billing_cycle": "monthly"},
    {"service": "dat",       "plan_name": "Load Board",   "amount_usd": 149.00, "billing_cycle": "monthly"},
]


def _mtd_range() -> tuple[str, str]:
    """ISO timestamps for start and end of current month."""
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day = calendar.monthrange(now.year, now.month)[1]
    end = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
    return start.isoformat(), end.isoformat()


def get_mtd_summary() -> dict[str, Any]:
    """Return month-to-date API cost summary by service and category."""
    sb = get_supabase()
    start, end = _mtd_range()

    rows = (
        sb.table("cost_entries")
        .select("service,category,cost_usd,units,unit_type,recorded_at")
        .gte("recorded_at", start)
        .lte("recorded_at", end)
        .execute()
        .data or []
    )

    by_service: dict[str, float] = {}
    by_category: dict[str, float] = {}
    for r in rows:
        svc = r["service"]
        cat = r["category"]
        amt = float(r.get("cost_usd") or 0)
        by_service[svc] = round(by_service.get(svc, 0) + amt, 6)
        by_category[cat] = round(by_category.get(cat, 0) + amt, 6)

    api_total = round(sum(by_service.values()), 4)

    # Pull active subscriptions
    subs = (
        sb.table("cost_subscriptions")
        .select("service,plan_name,amount_usd,billing_cycle")
        .eq("active", True)
        .execute()
        .data or []
    )
    sub_total = round(sum(float(s.get("amount_usd") or 0) for s in subs), 2)

    return {
        "period": datetime.now(timezone.utc).strftime("%Y-%m"),
        "api_cost_usd": api_total,
        "subscription_cost_usd": sub_total,
        "total_cost_usd": round(api_total + sub_total, 2),
        "by_service": dict(sorted(by_service.items(), key=lambda x: -x[1])),
        "by_category": dict(sorted(by_category.items(), key=lambda x: -x[1])),
        "subscriptions": subs,
        "entry_count": len(rows),
    }


def get_budget_alerts() -> list[dict[str, Any]]:
    """Check cost_entries MTD against cost_budgets. Return list of alerts."""
    sb = get_supabase()
    start, _ = _mtd_range()

    budgets = (
        sb.table("cost_budgets")
        .select("*")
        .eq("active", True)
        .execute()
        .data or []
    )
    if not budgets:
        return []

    alerts: list[dict] = []
    for b in budgets:
        svc = b.get("service")
        cat = b.get("category")
        budget_amt = float(b.get("monthly_budget_usd") or 0)
        threshold_pct = int(b.get("alert_threshold_pct") or 80)

        q = sb.table("cost_entries").select("cost_usd").gte("recorded_at", start)
        if svc:
            q = q.eq("service", svc)
        elif cat:
            q = q.eq("category", cat)
        rows = q.execute().data or []
        spent = sum(float(r.get("cost_usd") or 0) for r in rows)
        pct_used = round(spent / budget_amt * 100, 1) if budget_amt else 0

        if pct_used >= threshold_pct:
            label = svc or cat or "unknown"
            alerts.append({
                "service_or_category": label,
                "budget_usd": budget_amt,
                "spent_usd": round(spent, 4),
                "pct_used": pct_used,
                "severity": "critical" if pct_used >= 100 else "warning",
            })

    return alerts


def _build_html_report(summary: dict, alerts: list[dict], period_label: str) -> str:
    api_cost = summary["api_cost_usd"]
    sub_cost = summary["subscription_cost_usd"]
    total = summary["total_cost_usd"]

    rows_service = ""
    for svc, amt in summary["by_service"].items():
        rows_service += f"<tr><td style='padding:4px 8px'>{svc}</td><td style='padding:4px 8px;text-align:right'>${amt:,.4f}</td></tr>\n"

    rows_cat = ""
    for cat, amt in summary["by_category"].items():
        rows_cat += f"<tr><td style='padding:4px 8px'>{cat}</td><td style='padding:4px 8px;text-align:right'>${amt:,.4f}</td></tr>\n"

    rows_sub = ""
    for s in summary["subscriptions"]:
        rows_sub += f"<tr><td style='padding:4px 8px'>{s['service']}</td><td style='padding:4px 8px'>{s.get('plan_name','')}</td><td style='padding:4px 8px;text-align:right'>${float(s.get('amount_usd',0)):,.2f}/mo</td></tr>\n"

    alert_html = ""
    if alerts:
        for a in alerts:
            color = "#c0392b" if a["severity"] == "critical" else "#e67e22"
            alert_html += (
                f"<li style='color:{color}'><strong>{a['service_or_category']}</strong>: "
                f"${a['spent_usd']:,.4f} of ${a['budget_usd']:,.2f} budget used ({a['pct_used']}%) — "
                f"{a['severity'].upper()}</li>\n"
            )
        alert_html = f"<h3 style='color:#c0392b'>⚠ Budget Alerts</h3><ul>{alert_html}</ul>"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>3 Lakes Logistics — Cost Report {period_label}</title></head>
<body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;padding:20px;color:#222">
  <div style="background:#1a1a2e;color:#fff;padding:20px;border-radius:8px;margin-bottom:20px">
    <h1 style="margin:0;font-size:22px">3 Lakes Logistics — Cost Report</h1>
    <p style="margin:4px 0 0;opacity:.8">Period: {period_label} &nbsp;|&nbsp; Prepared by IEBC Cost Monitor</p>
  </div>

  <div style="display:flex;gap:12px;margin-bottom:20px">
    <div style="flex:1;background:#f0f7ff;border-left:4px solid #2980b9;padding:16px;border-radius:4px">
      <div style="font-size:12px;color:#555;text-transform:uppercase">API & Usage</div>
      <div style="font-size:28px;font-weight:bold;color:#2980b9">${api_cost:,.2f}</div>
    </div>
    <div style="flex:1;background:#f0fff4;border-left:4px solid #27ae60;padding:16px;border-radius:4px">
      <div style="font-size:12px;color:#555;text-transform:uppercase">Subscriptions</div>
      <div style="font-size:28px;font-weight:bold;color:#27ae60">${sub_cost:,.2f}</div>
    </div>
    <div style="flex:1;background:#fff8f0;border-left:4px solid #e67e22;padding:16px;border-radius:4px">
      <div style="font-size:12px;color:#555;text-transform:uppercase">Total MTD</div>
      <div style="font-size:28px;font-weight:bold;color:#e67e22">${total:,.2f}</div>
    </div>
  </div>

  {alert_html}

  <h3>API Usage by Service</h3>
  <table style="width:100%;border-collapse:collapse;background:#fafafa">
    <thead><tr style="background:#e9ecef"><th style="padding:6px 8px;text-align:left">Service</th><th style="padding:6px 8px;text-align:right">Cost (USD)</th></tr></thead>
    <tbody>{rows_service}</tbody>
    <tfoot><tr style="font-weight:bold;border-top:2px solid #ddd"><td style="padding:6px 8px">Total API</td><td style="padding:6px 8px;text-align:right">${api_cost:,.4f}</td></tr></tfoot>
  </table>

  <h3>Cost by Category</h3>
  <table style="width:100%;border-collapse:collapse;background:#fafafa">
    <thead><tr style="background:#e9ecef"><th style="padding:6px 8px;text-align:left">Category</th><th style="padding:6px 8px;text-align:right">Cost (USD)</th></tr></thead>
    <tbody>{rows_cat}</tbody>
  </table>

  <h3>Active Subscriptions</h3>
  <table style="width:100%;border-collapse:collapse;background:#fafafa">
    <thead><tr style="background:#e9ecef">
      <th style="padding:6px 8px;text-align:left">Service</th>
      <th style="padding:6px 8px;text-align:left">Plan</th>
      <th style="padding:6px 8px;text-align:right">Cost</th>
    </tr></thead>
    <tbody>{rows_sub}</tbody>
    <tfoot><tr style="font-weight:bold;border-top:2px solid #ddd"><td style="padding:6px 8px" colspan="2">Monthly Subscription Total</td><td style="padding:6px 8px;text-align:right">${sub_cost:,.2f}</td></tr></tfoot>
  </table>

  <p style="margin-top:30px;font-size:12px;color:#888">
    Generated automatically by IEBC Cost Monitor &middot; 3 Lakes Logistics AI Platform<br>
    To adjust budgets or subscriptions: Eagle Eye → Cost Tracking → Budgets
  </p>
</body>
</html>"""


def send_report(
    summary: dict,
    alerts: list[dict],
    *,
    period_label: str | None = None,
    recipients: list[str] | None = None,
) -> dict:
    """Generate and send the HTML cost report via Postmark."""
    s = get_settings()
    period_label = period_label or summary.get("period", datetime.now(timezone.utc).strftime("%Y-%m"))
    to_list = recipients or [MARK_ODOM_EMAIL, IEBC_EMAIL]
    html = _build_html_report(summary, alerts, period_label)
    subject = f"3 Lakes Logistics — Cost Report {period_label}"

    result: dict[str, Any] = {"sent": False, "recipients": to_list, "period": period_label}

    if not s.postmark_server_token:
        result["note"] = "postmark_not_configured"
        log.warning("cost report: postmark not configured, skipping email")
        return result

    try:
        from postmarker.core import PostmarkClient  # type: ignore
        client = PostmarkClient(server_token=s.postmark_server_token)
        for addr in to_list:
            client.emails.send(
                From=s.postmark_from_email,
                To=addr,
                Subject=subject,
                HtmlBody=html,
                MessageStream="outbound",
            )
        result["sent"] = True
        log.info("cost report sent to %s", to_list)
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        log.error("cost report send failed: %s", exc)

    # Store report record
    try:
        get_supabase().table("cost_reports").insert({
            "report_period": period_label,
            "report_type": "weekly",
            "total_cost_usd": summary["total_cost_usd"],
            "breakdown": {
                "by_service": summary["by_service"],
                "by_category": summary["by_category"],
                "api_cost_usd": summary["api_cost_usd"],
                "subscription_cost_usd": summary["subscription_cost_usd"],
            },
            "budget_status": {"alerts_count": len(alerts)},
            "alerts": alerts,
            "sent_to": to_list,
            "sent_at": datetime.now(timezone.utc).isoformat() if result["sent"] else None,
        }).execute()
    except Exception as exc:  # noqa: BLE001
        log.warning("cost_reports insert failed: %s", exc)

    return result
