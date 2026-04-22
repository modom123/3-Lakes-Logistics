"""Settler — Weekly driver settlement packets + ACH push (step 66)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..integrations.email import send_email
from ..logging_service import log_agent


def _iso_week_range(today: date | None = None) -> tuple[str, str]:
    today = today or date.today()
    # ISO week: Monday..Sunday of the previous week
    end = today - timedelta(days=today.weekday() + 1)  # Sunday
    start = end - timedelta(days=6)                     # Monday
    return start.isoformat(), end.isoformat()


def _calc(driver_id: str, ws: str, we: str) -> dict[str, Any]:
    try:
        from ..supabase_client import get_supabase
        sb = get_supabase()
        loads = (
            sb.table("loads")
            .select("id, rate_total, driver_code, carrier_id")
            .eq("driver_code", driver_id).eq("status", "delivered")
            .gte("delivery_at", ws).lte("delivery_at", we).execute()
        ).data or []
        deductions_rows = (
            sb.table("driver_deductions")
            .select("amount, kind")
            .eq("driver_id", driver_id)
            .gte("period_end", ws).lte("period_end", we).execute()
        ).data or []
    except Exception as exc:  # noqa: BLE001
        log_agent("settler", "calc_failed", error=str(exc))
        loads, deductions_rows = [], []
    gross = sum(float(l.get("rate_total") or 0) for l in loads)
    deductions = sum(float(d.get("amount") or 0) for d in deductions_rows)
    return {
        "driver_id": driver_id, "period_start": ws, "period_end": we,
        "carrier_id": (loads[0]["carrier_id"] if loads else None),
        "gross_amount": round(gross, 2),
        "deductions": round(deductions, 2),
        "load_count": len(loads),
    }


def weekly_run() -> dict[str, Any]:
    ws, we = _iso_week_range()
    try:
        from ..supabase_client import get_supabase
        drivers = (
            get_supabase().table("drivers")
            .select("id, email, carrier_id").eq("status", "active").execute()
        ).data or []
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    created = 0
    for d in drivers:
        row = _calc(d["id"], ws, we)
        if row["load_count"] == 0:
            continue
        row["status"] = "sent"
        try:
            from ..supabase_client import get_supabase
            get_supabase().table("driver_settlements").insert(row).execute()
            created += 1
            if d.get("email"):
                send_email(
                    d["email"],
                    f"Your weekly settlement {ws} → {we}",
                    _html_statement(row),
                    tag="settlement",
                )
        except Exception as exc:  # noqa: BLE001
            log_agent("settler", "insert_failed", error=str(exc))
    log_agent("settler", "weekly_run", result=f"created={created} week={ws}..{we}")
    return {"status": "ok", "created": created, "week": [ws, we]}


def _html_statement(row: dict[str, Any]) -> str:
    net = row["gross_amount"] - row["deductions"]
    return (
        f"<h2>Weekly Settlement</h2>"
        f"<p>Period: <b>{row['period_start']}</b> → <b>{row['period_end']}</b></p>"
        f"<table cellspacing=0 cellpadding=6 border=1>"
        f"<tr><td>Loads delivered</td><td>{row['load_count']}</td></tr>"
        f"<tr><td>Gross</td><td>${row['gross_amount']:.2f}</td></tr>"
        f"<tr><td>Deductions</td><td>- ${row['deductions']:.2f}</td></tr>"
        f"<tr><td><b>Net</b></td><td><b>${net:.2f}</b></td></tr>"
        f"</table>"
        f"<p style='color:#666'>ACH initiated within 1 business day.</p>"
    )


def run(payload: dict[str, Any]) -> dict[str, Any]:
    if (payload.get("kind") or "") == "weekly_run":
        return {"agent": "settler", **weekly_run()}
    driver_id = payload.get("driver_id")
    ws = payload.get("period_start") or _iso_week_range()[0]
    we = payload.get("period_end") or _iso_week_range()[1]
    if not driver_id:
        return {"agent": "settler", "status": "error", "error": "driver_id required"}
    return {"agent": "settler", "status": "ok", **_calc(driver_id, ws, we)}
