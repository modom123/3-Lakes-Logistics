"""Quinn Mercer — Broker Operations & Documentation.

Every brokered load needs two docs before money moves:
  1. Rate Confirmation (RC) — carrier signs before pickup
  2. Freight Invoice — shipper pays after delivery

Quinn generates both, tracks signing status, submits to factoring,
and flags anything overdue. She's the paper trail that makes the
broker division legally clean and cash-flow positive.

Actions via run(payload):
  generate_rc       — create a rate confirmation for a brokered load
  generate_invoice  — create a freight invoice to the shipper
  submit_factoring  — mark an invoice as factored, record advance
  docs_queue        — all pending RCs + unpaid invoices
  division_summary  — high-level broker division KPIs
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase


def _next_rc_number(db) -> str:
    seq = db.rpc("nextval", {"seq_name": "broker_rc_seq"}).execute()
    n = (seq.data or [1])[0] if isinstance(seq.data, list) else 1
    return f"3LL-RC-{date.today().year}-{str(n).zfill(4)}"


def _next_inv_number(db) -> str:
    seq = db.rpc("nextval", {"seq_name": "broker_inv_seq"}).execute()
    n = (seq.data or [1])[0] if isinstance(seq.data, list) else 1
    return f"3LL-INV-{date.today().year}-{str(n).zfill(4)}"


def generate_rc(payload: dict) -> dict:
    """Generate a rate confirmation for a brokered load."""
    load_id = payload.get("load_id")
    if not load_id:
        return {"agent": "quinn", "status": "error", "error": "load_id required"}

    db = get_supabase()

    # Pull load data
    load = (db.table("brokered_loads")
            .select("*")
            .eq("id", load_id)
            .single()
            .execute()).data

    if not load:
        return {"agent": "quinn", "status": "error", "error": "load not found"}

    # Check for existing RC
    existing = (db.table("broker_rate_confirmations")
                .select("id,rc_number,status")
                .eq("load_id", load_id)
                .not_.eq("status", "void")
                .execute()).data or []
    if existing:
        return {
            "agent": "quinn", "action": "generate_rc",
            "status": "already_exists",
            "rc_number": existing[0]["rc_number"],
            "rc_id": existing[0]["id"],
        }

    buy_rate   = float(load.get("buy_rate") or 0)
    miles      = int(load.get("miles") or 0)
    rate_pm    = round(buy_rate / miles, 2) if miles else None
    origin     = f"{load.get('origin_city','')}, {load.get('origin_state','')}"
    dest       = f"{load.get('dest_city','')}, {load.get('dest_state','')}"

    rc_num = f"3LL-RC-{date.today().year}-{str(date.today().toordinal())[-4:]}"

    row = {
        "load_id":       load_id,
        "rc_number":     rc_num,
        "status":        "pending",
        "shipper_name":  load.get("shipper_name") or load.get("broker_name"),
        "carrier_name":  load.get("covering_carrier_name"),
        "carrier_mc":    load.get("covering_carrier_mc"),
        "driver_phone":  load.get("covering_driver_phone"),
        "origin":        origin,
        "destination":   dest,
        "pickup_date":   load.get("pickup_date"),
        "delivery_date": load.get("delivery_date"),
        "commodity":     load.get("commodity"),
        "weight_lbs":    load.get("weight_lbs"),
        "trailer_type":  load.get("trailer_type"),
        "agreed_rate":   buy_rate,
        "rate_per_mile": rate_pm,
    }

    result = db.table("broker_rate_confirmations").insert(row).execute()
    rc_id = (result.data or [{}])[0].get("id") if result.data else None

    log_agent("quinn", "generate_rc", payload={"load_id": load_id},
              result=f"rc={rc_num} rate=${buy_rate:.0f}")
    return {
        "agent": "quinn",
        "action": "generate_rc",
        "status": "created",
        "rc_id": rc_id,
        "rc_number": rc_num,
        "carrier": row["carrier_name"],
        "agreed_rate": buy_rate,
        "lane": f"{origin} → {dest}",
        "pickup_date": row["pickup_date"],
    }


def generate_invoice(payload: dict) -> dict:
    """Generate a freight invoice to the shipper after delivery."""
    load_id    = payload.get("load_id")
    shipper_id = payload.get("shipper_id")
    if not load_id:
        return {"agent": "quinn", "status": "error", "error": "load_id required"}

    db = get_supabase()
    load = (db.table("brokered_loads")
            .select("*")
            .eq("id", load_id)
            .single()
            .execute()).data

    if not load:
        return {"agent": "quinn", "status": "error", "error": "load not found"}

    sell_rate   = float(load.get("sell_rate") or 0)
    fuel_charge = float(payload.get("fuel_surcharge") or 0)
    other       = float(payload.get("other_charges") or 0)
    total       = sell_rate + fuel_charge + other
    due_days    = int(payload.get("net_days") or 30)
    due_date    = (date.today() + timedelta(days=due_days)).isoformat()

    inv_num = f"3LL-INV-{date.today().year}-{str(date.today().toordinal())[-4:]}"

    row = {
        "load_id":       load_id,
        "shipper_id":    shipper_id,
        "invoice_number": inv_num,
        "status":        "draft",
        "invoice_date":  date.today().isoformat(),
        "due_date":      due_date,
        "line_freight":  sell_rate,
        "line_fuel":     fuel_charge,
        "line_other":    other,
        "total_due":     total,
        "notes":         payload.get("notes"),
    }

    result = db.table("broker_invoices").insert(row).execute()
    inv_id = (result.data or [{}])[0].get("id") if result.data else None

    # Advance load to 'delivered' if not already
    if load.get("status") not in ("delivered", "settled"):
        db.table("brokered_loads").update({"status": "delivered"}).eq("id", load_id).execute()

    log_agent("quinn", "generate_invoice", payload={"load_id": load_id},
              result=f"inv={inv_num} total=${total:.0f} due={due_date}")
    return {
        "agent": "quinn",
        "action": "generate_invoice",
        "status": "created",
        "invoice_id": inv_id,
        "invoice_number": inv_num,
        "total_due": total,
        "due_date": due_date,
        "sell_rate": sell_rate,
        "fuel_surcharge": fuel_charge,
    }


def submit_factoring(payload: dict) -> dict:
    """Mark an invoice as factored — record the advance and fee."""
    invoice_id = payload.get("invoice_id")
    fee_pct    = float(payload.get("fee_pct") or 2.5)
    if not invoice_id:
        return {"agent": "quinn", "status": "error", "error": "invoice_id required"}

    db  = get_supabase()
    inv = (db.table("broker_invoices").select("total_due").eq("id", invoice_id).single().execute()).data or {}
    total = float(inv.get("total_due") or 0)
    fee   = round(total * fee_pct / 100, 2)
    advance = round(total - fee, 2)

    db.table("broker_invoices").update({
        "status":       "factored",
        "factored":     True,
        "factor_fee_pct": fee_pct,
        "factor_advance": advance,
        "factored_at":  datetime.now(timezone.utc).isoformat(),
    }).eq("id", invoice_id).execute()

    log_agent("quinn", "submit_factoring", payload={"invoice_id": invoice_id},
              result=f"advance=${advance:.0f} fee=${fee:.0f} ({fee_pct}%)")
    return {
        "agent": "quinn",
        "action": "submit_factoring",
        "status": "factored",
        "invoice_id": invoice_id,
        "total_due": total,
        "factor_fee": fee,
        "advance_received": advance,
        "fee_pct": fee_pct,
    }


def docs_queue(payload: dict) -> dict:
    """All pending RCs and unpaid invoices — Quinn's daily work queue."""
    db = get_supabase()

    pending_rcs = (
        db.table("broker_rate_confirmations")
        .select("id,rc_number,load_id,carrier_name,agreed_rate,pickup_date,status,created_at")
        .in_("status", ["pending", "sent"])
        .order("pickup_date")
        .limit(30)
        .execute()
    ).data or []

    unpaid_invs = (
        db.table("broker_invoices")
        .select("id,invoice_number,load_id,shipper_id,total_due,due_date,status,invoice_date")
        .in_("status", ["draft", "sent", "overdue"])
        .order("due_date")
        .limit(30)
        .execute()
    ).data or []

    today = date.today().isoformat()
    overdue_invs = [i for i in unpaid_invs if i.get("due_date") and i["due_date"] < today]
    total_ar = sum(float(i.get("total_due") or 0) for i in unpaid_invs)

    log_agent("quinn", "docs_queue", result=f"rcs={len(pending_rcs)} invoices={len(unpaid_invs)} overdue={len(overdue_invs)}")
    return {
        "agent": "quinn",
        "action": "docs_queue",
        "pending_rcs": len(pending_rcs),
        "unpaid_invoices": len(unpaid_invs),
        "overdue_invoices": len(overdue_invs),
        "total_accounts_receivable": round(total_ar, 2),
        "rcs": pending_rcs,
        "invoices": unpaid_invs,
    }


def division_summary(payload: dict) -> dict:
    """High-level broker division KPIs — the number Rex looks at every morning."""
    db = get_supabase()

    loads = (db.table("brokered_loads")
             .select("id,gross_margin,sell_rate,status,created_at")
             .execute()).data or []

    shippers = (db.table("broker_shippers")
                .select("id,status,total_revenue")
                .execute()).data or []

    inv = (db.table("broker_invoices")
           .select("id,total_due,status,factored")
           .execute()).data or []

    today = date.today().isoformat()
    this_month_start = date.today().replace(day=1).isoformat()

    ytd_margin   = sum(float(l.get("gross_margin") or 0) for l in loads)
    month_loads  = [l for l in loads if (l.get("created_at") or "") >= this_month_start]
    month_margin = sum(float(l.get("gross_margin") or 0) for l in month_loads)
    active_shippers = len([s for s in shippers if s.get("status") == "active"])
    total_ar     = sum(float(i.get("total_due") or 0) for i in inv if i.get("status") not in ("paid", "factored"))
    open_loads   = len([l for l in loads if l.get("status") not in ("settled", "cancelled")])

    log_agent("quinn", "division_summary", result=f"ytd_margin=${ytd_margin:.0f} shippers={active_shippers}")
    return {
        "agent": "quinn",
        "action": "division_summary",
        "ytd_gross_margin":    round(ytd_margin, 2),
        "month_gross_margin":  round(month_margin, 2),
        "total_loads":         len(loads),
        "open_positions":      open_loads,
        "active_shippers":     active_shippers,
        "prospect_shippers":   len([s for s in shippers if s.get("status") == "prospect"]),
        "total_ar":            round(total_ar, 2),
        "loads_this_month":    len(month_loads),
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action", "docs_queue")
    if action == "generate_rc":
        return generate_rc(payload)
    if action == "generate_invoice":
        return generate_invoice(payload)
    if action == "submit_factoring":
        return submit_factoring(payload)
    if action == "docs_queue":
        return docs_queue(payload)
    if action == "division_summary":
        return division_summary(payload)
    return {"agent": "quinn", "status": "error", "error": f"unknown action: {action}",
            "valid_actions": ["generate_rc", "generate_invoice", "submit_factoring", "docs_queue", "division_summary"]}
