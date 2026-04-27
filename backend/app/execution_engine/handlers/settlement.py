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
}
