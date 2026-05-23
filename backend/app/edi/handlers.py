"""EDI inbound handler — routes parsed transactions to CLM and dispatch.

Flow:
  EDI 204 received → parse → log to broker_edi_log
                            → create rate confirmation in contracts table
                            → fire_clm_workflow() on the new contract
                            → return 990 Accept
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..logging_service import get_logger
from ..supabase_client import get_supabase
from .parser import parse_204, parse_edi

log = get_logger("3ll.edi.handler")


def handle_inbound_edi(raw_edi: str, broker_mc: str | None = None,
                       edi_partner_id: str | None = None) -> dict[str, Any]:
    """Parse inbound EDI, log it, and route to CLM.

    Returns:
        {
          "ok": bool,
          "transaction_set": str,
          "load_number": str | None,
          "contract_id": str | None,
          "outbound_990": str | None,   # ready-to-send 990 EDI string
          "message": str,
        }
    """
    sb = get_supabase()

    try:
        parsed = parse_edi(raw_edi)
    except Exception as exc:
        log.error("edi_parse_error: %s", exc)
        return {"ok": False, "message": f"parse error: {exc}"}

    ts = parsed.get("transaction_set")
    sender_id = edi_partner_id or parsed.get("sender_id")
    data = parsed.get("data", {})

    # Resolve broker_id from partner ID or broker_mc
    broker_id = _resolve_broker_id(sb, broker_mc, sender_id)

    # Log to broker_edi_log
    log_row = {
        "broker_id":       broker_id,
        "direction":       "inbound",
        "transaction_set": ts,
        "interchange_id":  parsed.get("interchange_id"),
        "load_number":     data.get("load_number"),
        "raw_edi":         raw_edi[:5000],  # cap size
        "parsed_data":     data,
        "status":          "received",
    }
    log_res = sb.table("broker_edi_log").insert(log_row).execute()
    log_id = log_res.data[0]["id"] if log_res.data else None

    result: dict[str, Any] = {
        "ok": True,
        "transaction_set": ts,
        "load_number": data.get("load_number"),
        "contract_id": None,
        "outbound_990": None,
        "message": f"received {ts}",
    }

    # ── EDI 204: Load Tender ───────────────────────────────────────────────────
    if ts == "204":
        contract_id, err = _process_204(sb, parsed, broker_id, broker_mc or parsed.get("sender_id"))
        if contract_id:
            result["contract_id"] = contract_id
            result["message"] = f"204 processed → contract {contract_id}"
            # Build 990 Accept
            from .generator import build_990
            from ..models.broker import EDI990Response
            partner_id = edi_partner_id or parsed.get("sender_id") or "BROKER"
            result["outbound_990"] = build_990(
                EDI990Response(
                    interchange_id=parsed.get("interchange_id") or "0",
                    load_number=data.get("load_number") or "0",
                    response_code="A",
                ),
                partner_id=partner_id,
            )
            # Update log status
            if log_id:
                sb.table("broker_edi_log").update({
                    "status":      "processed",
                    "contract_id": contract_id,
                }).eq("id", log_id).execute()
        else:
            result["ok"] = False
            result["message"] = f"204 failed: {err}"
            if log_id:
                sb.table("broker_edi_log").update({
                    "status":       "failed",
                    "error_detail": err,
                }).eq("id", log_id).execute()

    return result


def _process_204(sb, parsed: dict, broker_id: str | None,
                 broker_mc: str | None) -> tuple[str | None, str | None]:
    """Create a contract record from a parsed EDI 204."""
    try:
        data = parsed.get("data", {})
        load_number = data.get("load_number")
        if not load_number:
            return None, "missing load_number in 204"

        extracted_vars = {
            "load_number":        load_number,
            "broker_mc":          broker_mc,
            "equipment_type":     data.get("equipment_type"),
            "weight_lbs":         data.get("weight_lbs"),
            "commodity":          data.get("commodity"),
            "origin_city":        data.get("origin_city"),
            "origin_state":       data.get("origin_state"),
            "origin_zip":         data.get("origin_zip"),
            "destination_city":   data.get("destination_city"),
            "destination_state":  data.get("destination_state"),
            "destination_zip":    data.get("destination_zip"),
            "pickup_date":        data.get("pickup_date"),
            "delivery_date":      data.get("delivery_date"),
            "rate_total":         data.get("rate_total"),
            "payment_terms":      data.get("payment_terms"),
            "special_instructions": data.get("special_instructions"),
            "api_edi_standards":  "EDI 204",
        }

        # Resolve carrier_id from broker_id if possible
        contract_row = {
            "contract_type":    "rate_confirmation",
            "status":           "extracted",
            "source":           "edi_204",
            "counterparty_name": broker_mc or "EDI Broker",
            "load_number":      load_number,
            "extracted_vars":   extracted_vars,
            "rate_total":       data.get("rate_total"),
            "confidence_score": 0.95,   # EDI is machine-structured → high confidence
            "auto_approved":    False,
            "flagged_for_review": False,
            "milestone_pct":    0,
            "gl_posted":        False,
        }
        if data.get("origin_city"):
            contract_row["origin_city"] = data["origin_city"]
        if data.get("destination_city"):
            contract_row["destination_city"] = data["destination_city"]

        res = sb.table("contracts").insert(contract_row).execute()
        if not res.data:
            return None, "contract insert failed"

        contract_id = res.data[0]["id"]
        log.info("edi_204 contract_created load=%s contract=%s", load_number, contract_id)

        # Fire CLM workflow steps 124-131
        try:
            from ..triggers import fire_clm_workflow
            fire_clm_workflow(contract_id, carrier_id=None)
        except Exception as exc:
            log.warning("edi_204 clm_workflow fire failed: %s", exc)

        return contract_id, None

    except Exception as exc:
        log.error("_process_204 failed: %s", exc)
        return None, str(exc)


def _resolve_broker_id(sb, broker_mc: str | None, sender_id: str | None) -> str | None:
    """Look up broker UUID by MC number or EDI partner ID."""
    if broker_mc:
        res = sb.table("brokers").select("id").eq("mc_number", broker_mc).maybe_single().execute()
        if res.data:
            return res.data["id"]
    if sender_id:
        res = sb.table("brokers").select("id").eq("edi_partner_id", sender_id).maybe_single().execute()
        if res.data:
            return res.data["id"]
    return None
