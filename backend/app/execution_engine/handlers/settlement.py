"""Phase 4 — Delivery & Settlement handlers (steps 91–120)."""
from __future__ import annotations

from datetime import datetime, timezone

from ...agents import scout, echo, settler, penny, nova, beacon, audit
from ...logging_service import get_logger, log_agent
from ...settings import get_settings

log = get_logger("3ll.execution.settlement")

_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


def _db():
    try:
        from ...supabase_client import get_supabase
        return get_supabase()
    except Exception:  # noqa: BLE001
        return None


def _load(load_id):
    if not load_id:
        return {}
    sb = _db()
    if not sb:
        return {}
    try:
        r = sb.table("loads").select("*").eq("id", load_id).maybe_single().execute()
        return r.data or {}
    except Exception:  # noqa: BLE001
        return {}


# ── Step 91: delivery.confirmed ───────────────────────────────────────────────

def h91_delivery_confirmed(carrier_id, contract_id, payload):
    load_id = payload.get("load_id")
    sb = _db()
    if sb and load_id:
        try:
            sb.table("loads").update({
                "status": "delivered",
                "delivered_at": _NOW(),
            }).eq("id", load_id).execute()
        except Exception:  # noqa: BLE001
            pass
    log_agent("orbit", "delivery_confirmed", carrier_id=str(carrier_id) if carrier_id else None,
              payload={"load_id": load_id}, result="delivered")
    return {"confirmed": True, "load_id": load_id, "delivered_at": _NOW()}


# ── Step 92: document_vault.upload_pod ───────────────────────────────────────

def h92_document_vault_upload_pod(carrier_id, contract_id, payload):
    load_id = payload.get("load_id")
    pod_url = payload.get("pod_url") or payload.get("doc_url")
    sb = _db()
    if not sb:
        return {"uploaded": False, "note": "supabase_not_configured"}
    try:
        sb.table("document_vault").insert({
            "carrier_id": str(carrier_id) if carrier_id else None,
            "contract_id": str(contract_id) if contract_id else None,
            "doc_type": "pod",
            "filename": f"pod_{load_id}.pdf" if load_id else "pod.pdf",
            "storage_path": pod_url or f"loads/{load_id}/pod.pdf",
            "scan_status": "pending",
        }).execute()
        if load_id and pod_url:
            sb.table("loads").update({"pod_url": pod_url}).eq("id", load_id).execute()
        return {"uploaded": True, "load_id": load_id, "pod_url": pod_url}
    except Exception as e:  # noqa: BLE001
        return {"uploaded": False, "error": str(e)}


# ── Step 93: scout.extract_pod ────────────────────────────────────────────────

def h93_scout_extract_pod(carrier_id, contract_id, payload):
    raw_text = payload.get("raw_text") or payload.get("pod_text")
    s = get_settings()
    if not raw_text or not s.anthropic_api_key:
        return {"extracted": scout.ocr_document(None), "confidence": 0.0,
                "note": "no_text_or_anthropic_not_configured"}
    try:
        from ...clm.scanner import scan_contract
        extracted, confidence, warnings = scan_contract(raw_text, "pod")
        log_agent("scout", "extract_pod", carrier_id=str(carrier_id) if carrier_id else None,
                  result=f"confidence={confidence}")
        return {"extracted": extracted, "confidence": confidence, "warnings": warnings}
    except Exception as e:  # noqa: BLE001
        return {"extracted": {}, "confidence": 0.0, "error": str(e)}


# ── Step 94: clm.link_pod_to_contract ────────────────────────────────────────

def h94_clm_link_pod_to_contract(carrier_id, contract_id, payload):
    if not contract_id:
        return {"linked": False, "reason": "no_contract_id"}
    extracted = payload.get("extracted") or {}
    sb = _db()
    if not sb:
        return {"linked": False, "note": "supabase_not_configured"}
    try:
        sb.table("contracts").update({
            "milestone_pct": 90,
            "updated_at": _NOW(),
        }).eq("id", str(contract_id)).execute()
        sb.table("contract_events").insert({
            "contract_id": str(contract_id),
            "event_type": "pod_linked",
            "actor": "execution_engine",
            "payload": {"delivery_date": extracted.get("delivery_date"),
                        "consignee": extracted.get("consignee_name")},
        }).execute()
        return {"linked": True, "contract_id": str(contract_id), "milestone_pct": 90}
    except Exception as e:  # noqa: BLE001
        return {"linked": False, "error": str(e)}


# ── Step 95: clm.trigger_invoice ──────────────────────────────────────────────

def h95_clm_trigger_invoice(carrier_id, contract_id, payload):
    if not contract_id:
        return {"triggered": False, "reason": "no_contract_id"}
    try:
        from ...clm.engine import trigger_invoice
        contract = trigger_invoice(contract_id)
        return {"triggered": True, "contract_id": str(contract_id),
                "rate_total": contract.get("rate_total"),
                "payment_terms": contract.get("payment_terms")}
    except Exception as e:  # noqa: BLE001
        return {"triggered": False, "error": str(e)}


# ── Step 96: echo.missing_doc_check ──────────────────────────────────────────

def h96_echo_missing_doc_check(carrier_id, contract_id, payload):
    load_id = payload.get("load_id")
    pod_uploaded = payload.get("uploaded", False) or bool(payload.get("pod_url"))
    if pod_uploaded:
        return {"nudge_sent": False, "reason": "pod_already_uploaded"}
    s = get_settings()
    driver_phone = payload.get("driver_phone")
    msg = f"Reminder: POD required for load {payload.get('load_number','unknown')}. Please upload in the driver app."
    if s.twilio_account_sid and s.twilio_auth_token and driver_phone:
        try:
            from twilio.rest import Client  # type: ignore
            Client(s.twilio_account_sid, s.twilio_auth_token).messages.create(
                body=msg, from_=s.twilio_from_number, to=driver_phone)
            return {"nudge_sent": True, "to": driver_phone, "load_id": load_id}
        except Exception as e:  # noqa: BLE001
            return {"nudge_sent": False, "error": str(e)}
    return {"nudge_sent": False, "note": "twilio_not_configured", "would_send": msg}


# ── Step 97: settler.calc_driver_pay ──────────────────────────────────────────

def h97_settler_calc_driver_pay(carrier_id, contract_id, payload):
    load_id = payload.get("load_id")
    ld = _load(load_id) if load_id else {}
    rate_total = float(ld.get("rate_total") or payload.get("rate_total") or 0)
    driver_pct = float(payload.get("driver_pct") or 0.75)
    gross_pay = round(rate_total * driver_pct, 2)
    return {
        "driver_code": payload.get("driver_code") or ld.get("driver_code"),
        "load_id": load_id,
        "rate_total": rate_total,
        "driver_pct": driver_pct,
        "gross_pay": gross_pay,
    }


# ── Step 98: settler.fuel_deduction ──────────────────────────────────────────

def h98_settler_fuel_deduction(carrier_id, contract_id, payload):
    gross_pay = float(payload.get("gross_pay") or 0)
    fuel_cost = float(payload.get("fuel_amount") or payload.get("fuel_cost") or 0)
    after_fuel = round(gross_pay - fuel_cost, 2)
    return {
        "gross_pay": gross_pay,
        "fuel_deduction": fuel_cost,
        "pay_after_fuel": after_fuel,
    }


# ── Step 99: settler.escrow_check ────────────────────────────────────────────

def h99_settler_escrow_check(carrier_id, contract_id, payload):
    sb = _db()
    escrow_balance = 0.0
    escrow_applied = 0.0
    if sb and carrier_id:
        try:
            r = sb.table("banking_accounts").select("escrow_balance").eq(
                "carrier_id", str(carrier_id)).maybe_single().execute()
            escrow_balance = float((r.data or {}).get("escrow_balance") or 0)
        except Exception:  # noqa: BLE001
            pass
    pay_after_fuel = float(payload.get("pay_after_fuel") or payload.get("gross_pay") or 0)
    return {
        "escrow_balance": escrow_balance,
        "escrow_applied": escrow_applied,
        "pay_after_escrow": round(pay_after_fuel - escrow_applied, 2),
    }


# ── Step 100: settler.lumper_reimbursement ────────────────────────────────────

def h100_settler_lumper_reimbursement(carrier_id, contract_id, payload):
    lumper_amount = float(payload.get("lumper_amount") or 0)
    lumper_approved = payload.get("approved", lumper_amount > 0)
    pay_after_escrow = float(payload.get("pay_after_escrow") or payload.get("gross_pay") or 0)
    lumper_add = lumper_amount if lumper_approved else 0.0
    return {
        "lumper_amount": lumper_amount,
        "lumper_approved": lumper_approved,
        "lumper_added": lumper_add,
        "pay_after_lumper": round(pay_after_escrow + lumper_add, 2),
    }


# ── Step 101: settler.detention_add ──────────────────────────────────────────

def h101_settler_detention_add(carrier_id, contract_id, payload):
    detention_accrued = float(payload.get("accrued") or payload.get("detention_accrued") or 0)
    pay_after_lumper = float(payload.get("pay_after_lumper") or payload.get("gross_pay") or 0)
    return {
        "detention_accrued": detention_accrued,
        "detention_added": detention_accrued,
        "pay_after_detention": round(pay_after_lumper + detention_accrued, 2),
    }


# ── Step 102: settler.advance_deduct ─────────────────────────────────────────

def h102_settler_advance_deduct(carrier_id, contract_id, payload):
    fuel_advance = float(payload.get("fuel_advance") or payload.get("advance_amount") or 0)
    pay_after_detention = float(payload.get("pay_after_detention") or payload.get("gross_pay") or 0)
    return {
        "advance_deducted": fuel_advance,
        "pay_after_advance": round(pay_after_detention - fuel_advance, 2),
    }


# ── Step 103: settler.net_pay_calc ───────────────────────────────────────────

def h103_settler_net_pay_calc(carrier_id, contract_id, payload):
    gross = float(payload.get("gross_pay") or 0)
    fuel_ded = float(payload.get("fuel_deduction") or 0)
    escrow = float(payload.get("escrow_applied") or 0)
    lumper = float(payload.get("lumper_added") or 0)
    detention = float(payload.get("detention_added") or 0)
    advance = float(payload.get("advance_deducted") or 0)
    net = round(gross - fuel_ded - escrow - advance + lumper + detention, 2)
    sb = _db()
    if sb and payload.get("load_id"):
        try:
            sb.table("loads").update({"driver_net_pay": net}).eq(
                "id", payload["load_id"]).execute()
        except Exception:  # noqa: BLE001
            pass
    return {
        "gross_pay": gross, "fuel_deduction": fuel_ded, "escrow_applied": escrow,
        "lumper_added": lumper, "detention_added": detention,
        "advance_deducted": advance, "net_pay": net,
        "driver_code": payload.get("driver_code"),
    }


# ── Step 104: penny.load_margin ───────────────────────────────────────────────

def h104_penny_load_margin(carrier_id, contract_id, payload):
    rate = float(payload.get("rate_total") or 0)
    net_pay = float(payload.get("net_pay") or 0)
    fuel = float(payload.get("fuel_cost") or payload.get("fuel_deduction") or 0)
    detention = float(payload.get("detention_added") or 0)
    lumper = float(payload.get("lumper_added") or 0)
    total_cost = net_pay + fuel - detention - lumper
    margin = round(rate - total_cost, 2)
    margin_pct = round((margin / rate * 100), 2) if rate else 0
    miles = float(payload.get("miles") or 1)
    log_agent("penny", "load_margin", carrier_id=str(carrier_id) if carrier_id else None,
              result=f"margin=${margin} ({margin_pct}%)")
    return {
        "rate_total": rate, "total_cost": round(total_cost, 2),
        "gross_margin": margin, "margin_pct": margin_pct,
        "revenue_per_mile": round(rate / miles, 4) if miles else None,
    }


# ── Step 105: settler.ach_initiate ────────────────────────────────────────────

def h105_settler_ach_initiate(carrier_id, contract_id, payload):
    net_pay = float(payload.get("net_pay") or 0)
    driver_code = payload.get("driver_code")
    if net_pay <= 0:
        return {"initiated": False, "reason": "zero_or_negative_pay"}
    sb = _db()
    bank = {}
    if sb and carrier_id:
        try:
            r = sb.table("banking_accounts").select(
                "bank_routing,bank_account,payee_name,verified_at"
            ).eq("carrier_id", str(carrier_id)).maybe_single().execute()
            bank = r.data or {}
        except Exception:  # noqa: BLE001
            pass
    if not bank.get("verified_at"):
        return {"initiated": False, "reason": "bank_not_verified", "net_pay": net_pay}
    log_agent("settler", "ach_initiate", carrier_id=str(carrier_id) if carrier_id else None,
              payload={"amount": net_pay, "driver": driver_code}, result="initiated")
    return {
        "initiated": True, "net_pay": net_pay, "driver_code": driver_code,
        "payee_name": bank.get("payee_name"),
        "ach_status": "pending", "initiated_at": _NOW(),
        "note": "ACH via Stripe Treasury / banking_accounts — wire live key to complete",
    }


# ── Step 106: nova.settlement_email ──────────────────────────────────────────

def h106_nova_settlement_email(carrier_id, contract_id, payload):
    s = get_settings()
    driver_email = payload.get("driver_email")
    net_pay = payload.get("net_pay", 0)
    load_number = payload.get("load_number")
    if not driver_email:
        return {"sent": False, "reason": "no_driver_email"}
    body = (
        f"Settlement Statement — Load {load_number}\n\n"
        f"Gross Pay:      ${payload.get('gross_pay', 0):.2f}\n"
        f"Fuel Deduction: -${payload.get('fuel_deduction', 0):.2f}\n"
        f"Advance:        -${payload.get('advance_deducted', 0):.2f}\n"
        f"Lumper:         +${payload.get('lumper_added', 0):.2f}\n"
        f"Detention:      +${payload.get('detention_added', 0):.2f}\n"
        f"{'─'*35}\n"
        f"Net Pay:        ${net_pay:.2f}\n\n"
        f"— 3 Lakes Logistics"
    )
    if s.postmark_server_token:
        try:
            from postmarker.core import PostmarkClient  # type: ignore
            PostmarkClient(server_token=s.postmark_server_token).emails.send(
                From=s.postmark_from_email, To=driver_email,
                Subject=f"Settlement — Load {load_number} — ${net_pay:.2f}",
                TextBody=body)
            return {"sent": True, "to": driver_email, "net_pay": net_pay}
        except Exception as e:  # noqa: BLE001
            return {"sent": False, "error": str(e)}
    return {"sent": False, "note": "postmark_not_configured", "would_send_to": driver_email}


# ── Step 107: factoring.submit_invoice ────────────────────────────────────────

def h107_factoring_submit_invoice(carrier_id, contract_id, payload):
    rate_total = payload.get("rate_total", 0)
    factoring_company = payload.get("factoring_company") or "generic"
    return {
        "submitted": True,
        "factoring_company": factoring_company,
        "invoice_amount": rate_total,
        "submitted_at": _NOW(),
        "note": f"Wire {factoring_company} API credentials to go live",
    }


# ── Step 108: factoring.track_payment ────────────────────────────────────────

def h108_factoring_track_payment(carrier_id, contract_id, payload):
    sb = _db()
    payment_status = payload.get("payment_status", "pending")
    paid_amount = float(payload.get("paid_amount") or 0)
    if sb and contract_id and payment_status == "paid":
        try:
            sb.table("contracts").update({
                "milestone_pct": 100, "revenue_recognized": True, "updated_at": _NOW()
            }).eq("id", str(contract_id)).execute()
        except Exception:  # noqa: BLE001
            pass
    return {
        "payment_status": payment_status,
        "paid_amount": paid_amount,
        "tracked_at": _NOW(),
    }


# ── Step 109: clm.mark_gl_posted ─────────────────────────────────────────────

def h109_clm_mark_gl_posted(carrier_id, contract_id, payload):
    if not contract_id:
        return {"posted": False, "reason": "no_contract_id"}
    sb = _db()
    if not sb:
        return {"posted": False, "note": "supabase_not_configured"}
    try:
        sb.table("contracts").update({
            "gl_posted": True, "updated_at": _NOW()
        }).eq("id", str(contract_id)).execute()
        sb.table("contract_events").insert({
            "contract_id": str(contract_id),
            "event_type": "gl_posted",
            "actor": "execution_engine",
            "payload": {"margin": payload.get("gross_margin"),
                        "rate_total": payload.get("rate_total")},
        }).execute()
        return {"posted": True, "contract_id": str(contract_id)}
    except Exception as e:  # noqa: BLE001
        return {"posted": False, "error": str(e)}


# ── Step 110: penny.update_mtd_kpis ──────────────────────────────────────────

def h110_penny_update_mtd_kpis(carrier_id, contract_id, payload):
    rate = float(payload.get("rate_total") or 0)
    margin = float(payload.get("gross_margin") or 0)
    miles = float(payload.get("miles") or 1)
    sb = _db()
    if sb and carrier_id:
        try:
            r = sb.table("active_carriers").select(
                "mtd_gross,mtd_loads,mtd_miles"
            ).eq("id", str(carrier_id)).maybe_single().execute()
            cur = r.data or {}
            sb.table("active_carriers").update({
                "mtd_gross": round(float(cur.get("mtd_gross") or 0) + rate, 2),
                "mtd_loads": int(cur.get("mtd_loads") or 0) + 1,
                "mtd_miles": int(cur.get("mtd_miles") or 0) + int(miles),
                "mtd_updated_at": _NOW(),
            }).eq("id", str(carrier_id)).execute()
        except Exception:  # noqa: BLE001
            pass
    log_agent("penny", "update_mtd_kpis", carrier_id=str(carrier_id) if carrier_id else None,
              result=f"rate={rate} margin={margin}")
    return {
        "updated": True, "rate_total": rate, "gross_margin": margin,
        "rpm": round(rate / miles, 4) if miles else None,
    }


# ── Step 111: fleet.status_available ─────────────────────────────────────────

def h111_fleet_status_available(carrier_id, contract_id, payload):
    truck_id = payload.get("truck_id")
    if not truck_id:
        return {"updated": False, "reason": "no_truck_id"}
    sb = _db()
    if sb:
        try:
            sb.table("fleet_assets").update({
                "status": "available", "current_load_id": None
            }).eq("truck_id", truck_id).execute()
        except Exception:  # noqa: BLE001
            pass
    return {"updated": True, "truck_id": truck_id, "status": "available"}


# ── Step 112: dispatch.next_load_offer ────────────────────────────────────────

def h112_dispatch_next_load_offer(carrier_id, contract_id, payload):
    truck_id = payload.get("truck_id")
    dest_city = payload.get("dest_city")
    dest_state = payload.get("dest_state")
    sb = _db()
    nearby_loads = []
    if sb and dest_state:
        try:
            rows = sb.table("loads").select(
                "id,load_number,origin_city,origin_state,dest_city,dest_state,rate_total"
            ).eq("status", "booked").eq("origin_state", dest_state).limit(5).execute().data or []
            nearby_loads = rows
        except Exception:  # noqa: BLE001
            pass
    return {
        "truck_id": truck_id,
        "current_location": f"{dest_city},{dest_state}",
        "nearby_loads": nearby_loads,
        "loads_found": len(nearby_loads),
    }


# ── Step 113: audit.settlement_audit ─────────────────────────────────────────

def h113_audit_settlement_audit(carrier_id, contract_id, payload):
    net_pay = float(payload.get("net_pay") or 0)
    gross_pay = float(payload.get("gross_pay") or 0)
    rate_total = float(payload.get("rate_total") or 0)
    issues = []
    if gross_pay > rate_total:
        issues.append("driver_gross_exceeds_rate")
    if net_pay < 0:
        issues.append("negative_net_pay")
    if rate_total > 0 and (gross_pay / rate_total) > 0.90:
        issues.append("driver_pct_above_90pct")
    return {
        "audit_passed": not issues,
        "issues": issues,
        "net_pay": net_pay,
        "gross_pay": gross_pay,
        "rate_total": rate_total,
    }


# ── Step 114: beacon.update_load_history ──────────────────────────────────────

def h114_beacon_update_load_history(carrier_id, contract_id, payload):
    sb = _db()
    if sb and payload.get("load_id"):
        try:
            sb.table("loads").update({
                "margin": payload.get("gross_margin"),
                "margin_pct": payload.get("margin_pct"),
                "history_updated_at": _NOW(),
            }).eq("id", payload["load_id"]).execute()
        except Exception:  # noqa: BLE001
            pass
    log_agent("beacon", "update_load_history", carrier_id=str(carrier_id) if carrier_id else None,
              result=f"load={payload.get('load_id')}")
    return {"updated": True, "load_id": payload.get("load_id"),
            "gross_margin": payload.get("gross_margin")}


# ── Step 115: atomic_ledger.settlement ───────────────────────────────────────

def h115_atomic_ledger_settlement(carrier_id, contract_id, payload):
    try:
        from ...atomic_ledger.service import write_event
        from ...atomic_ledger.models import AtomicEvent
        write_event(AtomicEvent(
            event_type="settlement.complete",
            event_source="execution_engine.step_115",
            logistics_payload={
                "load_id": payload.get("load_id"),
                "load_number": payload.get("load_number"),
                "driver_code": payload.get("driver_code"),
                "truck_id": payload.get("truck_id"),
            },
            financial_payload={
                "rate_total": payload.get("rate_total"),
                "gross_pay": payload.get("gross_pay"),
                "net_pay": payload.get("net_pay"),
                "gross_margin": payload.get("gross_margin"),
                "margin_pct": payload.get("margin_pct"),
                "gl_posted": payload.get("gl_posted", False),
            },
            compliance_payload={
                "carrier_id": str(carrier_id) if carrier_id else None,
                "audit_passed": payload.get("audit_passed", True),
            },
        ))
        return {"logged": True}
    except Exception as e:  # noqa: BLE001
        return {"logged": False, "error": str(e)}


# ── Step 116: driver.performance_score ───────────────────────────────────────

def h116_driver_performance_score(carrier_id, contract_id, payload):
    driver_code = payload.get("driver_code")
    on_time = payload.get("on_time", True)
    pod_uploaded = payload.get("uploaded", True)
    damage = payload.get("damage_reported", False)
    score_delta = 0
    score_delta += 5 if on_time else -10
    score_delta += 2 if pod_uploaded else -5
    score_delta += -15 if damage else 0
    sb = _db()
    if sb and driver_code:
        try:
            r = sb.table("driver_hos_status").select("performance_score").eq(
                "driver_id", driver_code).maybe_single().execute()
            current = float((r.data or {}).get("performance_score") or 75)
            new_score = max(0, min(100, current + score_delta))
            sb.table("driver_hos_status").update(
                {"performance_score": new_score}
            ).eq("driver_id", driver_code).execute()
        except Exception:  # noqa: BLE001
            new_score = 75 + score_delta
    else:
        new_score = 75 + score_delta
    return {"driver_code": driver_code, "score_delta": score_delta,
            "new_score": max(0, min(100, new_score))}


# ── Step 117: carrier.revenue_update ─────────────────────────────────────────

def h117_carrier_revenue_update(carrier_id, contract_id, payload):
    if not carrier_id:
        return {"updated": False}
    rate = float(payload.get("rate_total") or 0)
    sb = _db()
    if sb:
        try:
            r = sb.table("active_carriers").select("ytd_revenue").eq(
                "id", str(carrier_id)).maybe_single().execute()
            ytd = float((r.data or {}).get("ytd_revenue") or 0)
            sb.table("active_carriers").update({
                "ytd_revenue": round(ytd + rate, 2), "revenue_updated_at": _NOW()
            }).eq("id", str(carrier_id)).execute()
        except Exception:  # noqa: BLE001
            pass
    return {"updated": True, "carrier_id": str(carrier_id), "added": rate}


# ── Step 118: nova.broker_invoice_email ──────────────────────────────────────

def h118_nova_broker_invoice_email(carrier_id, contract_id, payload):
    s = get_settings()
    broker_email = payload.get("broker_email")
    rate_total = payload.get("rate_total", 0)
    load_number = payload.get("load_number")
    if not broker_email:
        return {"sent": False, "reason": "no_broker_email"}
    body = (f"Invoice + POD Package — Load {load_number}\n\n"
            f"Amount Due: ${rate_total}\n"
            f"Payment Terms: {payload.get('payment_terms','Net-30')}\n"
            f"POD: {payload.get('pod_url','attached')}\n\n"
            f"— 3 Lakes Logistics Billing")
    if s.postmark_server_token:
        try:
            from postmarker.core import PostmarkClient  # type: ignore
            PostmarkClient(server_token=s.postmark_server_token).emails.send(
                From=s.postmark_from_email, To=broker_email,
                Subject=f"Invoice #{load_number} — ${rate_total}",
                TextBody=body)
            return {"sent": True, "to": broker_email, "amount": rate_total}
        except Exception as e:  # noqa: BLE001
            return {"sent": False, "error": str(e)}
    return {"sent": False, "note": "postmark_not_configured", "would_send_to": broker_email}


# ── Step 119: dispute.check_variance ─────────────────────────────────────────

def h119_dispute_check_variance(carrier_id, contract_id, payload):
    expected = float(payload.get("rate_total") or 0)
    paid = float(payload.get("paid_amount") or 0)
    if not expected:
        return {"variance": False, "reason": "no_expected_amount"}
    variance = round(abs(expected - paid), 2)
    pct = round(variance / expected * 100, 2) if expected else 0
    has_variance = variance > 0.01
    sb = _db()
    if sb and has_variance and contract_id:
        try:
            sb.table("contract_events").insert({
                "contract_id": str(contract_id),
                "event_type": "payment_variance",
                "actor": "execution_engine",
                "payload": {"expected": expected, "paid": paid,
                            "variance": variance, "variance_pct": pct},
            }).execute()
        except Exception:  # noqa: BLE001
            pass
    return {"variance": has_variance, "expected": expected, "paid": paid,
            "variance_amount": variance, "variance_pct": pct}


# ── Step 120: settlement.complete ────────────────────────────────────────────

def h120_settlement_complete(carrier_id, contract_id, payload):
    load_id = payload.get("load_id")
    sb = _db()
    if sb and load_id:
        try:
            sb.table("loads").update({"status": "closed"}).eq("id", load_id).execute()
        except Exception:  # noqa: BLE001
            pass
    if sb and contract_id:
        try:
            sb.table("contracts").update({
                "status": "executed", "milestone_pct": 100,
                "revenue_recognized": True, "updated_at": _NOW(),
            }).eq("id", str(contract_id)).execute()
        except Exception:  # noqa: BLE001
            pass
    try:
        from ...atomic_ledger.service import write_event
        from ...atomic_ledger.models import AtomicEvent
        write_event(AtomicEvent(
            event_type="settlement.workflow_complete",
            event_source="execution_engine.step_120",
            logistics_payload={"load_id": load_id, "load_number": payload.get("load_number")},
            financial_payload={"net_pay": payload.get("net_pay"),
                               "gross_margin": payload.get("gross_margin"),
                               "rate_total": payload.get("rate_total")},
            compliance_payload={"gl_posted": payload.get("gl_posted", False),
                                "audit_passed": payload.get("audit_passed", True)},
        ))
    except Exception as e:  # noqa: BLE001
        log.warning("atomic_ledger write failed at step 120: %s", e)
    return {"settlement_complete": True, "load_id": load_id,
            "contract_id": str(contract_id) if contract_id else None,
            "completed_at": _NOW()}


SETTLEMENT_HANDLERS: dict = {
    91:  h91_delivery_confirmed,
    92:  h92_document_vault_upload_pod,
    93:  h93_scout_extract_pod,
    94:  h94_clm_link_pod_to_contract,
    95:  h95_clm_trigger_invoice,
    96:  h96_echo_missing_doc_check,
    97:  h97_settler_calc_driver_pay,
    98:  h98_settler_fuel_deduction,
    99:  h99_settler_escrow_check,
    100: h100_settler_lumper_reimbursement,
    101: h101_settler_detention_add,
    102: h102_settler_advance_deduct,
    103: h103_settler_net_pay_calc,
    104: h104_penny_load_margin,
    105: h105_settler_ach_initiate,
    106: h106_nova_settlement_email,
    107: h107_factoring_submit_invoice,
    108: h108_factoring_track_payment,
    109: h109_clm_mark_gl_posted,
    110: h110_penny_update_mtd_kpis,
    111: h111_fleet_status_available,
    112: h112_dispatch_next_load_offer,
    113: h113_audit_settlement_audit,
    114: h114_beacon_update_load_history,
    115: h115_atomic_ledger_settlement,
    116: h116_driver_performance_score,
    117: h117_carrier_revenue_update,
    118: h118_nova_broker_invoice_email,
    119: h119_dispute_check_variance,
    120: h120_settlement_complete,
}
