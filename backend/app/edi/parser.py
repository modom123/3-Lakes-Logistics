"""X12 EDI parser — handles 204, 990, 214, 210 transaction sets.

X12 structure:
  ISA  — Interchange Control Header       (fixed-width, 106 chars)
  GS   — Functional Group Header
  ST   — Transaction Set Header
  ...  — Segment data
  SE   — Transaction Set Trailer
  GE   — Functional Group Trailer
  IEA  — Interchange Control Trailer

Each segment is delimited by * (element) and ~ (segment terminator).
"""
from __future__ import annotations

import re
from typing import Any

from ..logging_service import get_logger
from ..models.broker import EDI204LoadTender

log = get_logger("3ll.edi.parser")


def parse_edi(raw: str) -> dict[str, Any]:
    """Parse raw X12 EDI string and return structured dict.

    Returns:
        {
          "transaction_set": "204" | "990" | "214" | "210",
          "interchange_id": str,
          "sender_id": str,
          "data": dict,    # transaction-specific parsed fields
        }
    """
    raw = raw.strip().replace("\n", "").replace("\r", "")

    # Detect element delimiter from ISA (position 3) and segment terminator (last char of ISA)
    elem_delim = raw[3] if len(raw) > 3 else "*"
    # Segment terminator is right after ISA segment (position 105 in standard ISA)
    seg_term = "~"
    for ch in ("~", "|", "^"):
        if ch in raw:
            seg_term = ch
            break

    segments = [s.strip() for s in raw.split(seg_term) if s.strip()]

    result: dict[str, Any] = {
        "transaction_set": None,
        "interchange_id": None,
        "sender_id": None,
        "data": {},
        "raw": raw,
    }

    isa = None
    gs = None
    st = None
    current_loop = None
    stops: list[dict] = []
    current_stop: dict | None = None

    for seg in segments:
        elems = seg.split(elem_delim)
        tag = elems[0].strip().upper()

        if tag == "ISA":
            if len(elems) >= 14:
                result["sender_id"]     = elems[6].strip()
                result["interchange_id"] = elems[13].strip() if len(elems) > 13 else None
            isa = elems

        elif tag == "GS":
            gs = elems

        elif tag == "ST":
            ts_id = elems[1].strip() if len(elems) > 1 else None
            result["transaction_set"] = ts_id
            st = elems

        # ── EDI 204: Load Tender ───────────────────────────────────────────────
        elif tag == "B2" and result["transaction_set"] == "204":
            # B2*SCAC*Load#*...*...*EquipType
            d = result["data"]
            d["load_number"]    = elems[2].strip() if len(elems) > 2 else None
            d["equipment_type"] = elems[8].strip() if len(elems) > 8 else None

        elif tag == "L11" and result["transaction_set"] == "204":
            # L11*BrokerMC*MC — reference number
            if len(elems) > 2 and elems[2].strip().upper() in ("MC", "BR"):
                result["data"]["broker_mc"] = elems[1].strip()

        elif tag == "AT5" and result["transaction_set"] == "204":
            # AT5*commodity description
            result["data"]["commodity"] = elems[1].strip() if len(elems) > 1 else None

        elif tag == "S1" and result["transaction_set"] == "204":
            # S1*stop_seq
            current_stop = {"stop_type": None, "city": None, "state": None, "zip": None, "date": None}
            stops.append(current_stop)

        elif tag == "S5" and result["transaction_set"] == "204":
            # S5*1*CL (or PU/SO/DE) — stop function
            if current_stop and len(elems) > 2:
                current_stop["stop_type"] = elems[2].strip()

        elif tag == "N3" and current_stop is not None:
            # N3*address
            current_stop["address"] = elems[1].strip() if len(elems) > 1 else None

        elif tag == "N4" and current_stop is not None:
            # N4*city*state*zip
            if len(elems) > 1:
                current_stop["city"]  = elems[1].strip()
            if len(elems) > 2:
                current_stop["state"] = elems[2].strip()
            if len(elems) > 3:
                current_stop["zip"]   = elems[3].strip()

        elif tag == "G62" and current_stop is not None:
            # G62*10*20240115 — pickup/delivery date
            if len(elems) > 2:
                current_stop["date"] = _parse_date(elems[2].strip())

        elif tag == "OID" and result["transaction_set"] == "204":
            # OID — order/rate info
            d = result["data"]
            if len(elems) > 7:
                try:
                    d["rate_total"] = float(elems[7])
                except (ValueError, IndexError):
                    pass
            if len(elems) > 4:
                try:
                    d["weight_lbs"] = float(elems[4])
                except (ValueError, IndexError):
                    pass

        elif tag == "NTE" and result["transaction_set"] == "204":
            result["data"]["special_instructions"] = elems[2].strip() if len(elems) > 2 else None

        # ── EDI 990: Response to Load Tender ──────────────────────────────────
        elif tag == "B1" and result["transaction_set"] == "990":
            result["data"]["load_number"]    = elems[2].strip() if len(elems) > 2 else None
            result["data"]["response_code"]  = elems[3].strip() if len(elems) > 3 else None

        # ── EDI 214: Shipment Status ───────────────────────────────────────────
        elif tag == "B10" and result["transaction_set"] == "214":
            result["data"]["load_number"]    = elems[1].strip() if len(elems) > 1 else None

        elif tag == "AT7" and result["transaction_set"] == "214":
            result["data"]["status_code"]    = elems[1].strip() if len(elems) > 1 else None
            result["data"]["status_datetime"] = _parse_date(elems[3].strip()) if len(elems) > 3 else None

        # ── EDI 210: Freight Invoice ───────────────────────────────────────────
        elif tag == "B3" and result["transaction_set"] == "210":
            result["data"]["invoice_number"] = elems[2].strip() if len(elems) > 2 else None
            result["data"]["invoice_date"]   = _parse_date(elems[5].strip()) if len(elems) > 5 else None
            try:
                result["data"]["total_amount"] = float(elems[7]) if len(elems) > 7 else None
            except ValueError:
                pass
            result["data"]["load_number"]    = elems[9].strip() if len(elems) > 9 else None

    # Resolve stop list into origin/destination for 204
    if result["transaction_set"] == "204" and stops:
        for s in stops:
            st_type = (s.get("stop_type") or "").upper()
            if st_type in ("PU", "CL") and not result["data"].get("origin_city"):
                result["data"]["origin_city"]  = s.get("city")
                result["data"]["origin_state"] = s.get("state")
                result["data"]["origin_zip"]   = s.get("zip")
                result["data"]["pickup_date"]  = s.get("date")
            elif st_type in ("SO", "DE") and not result["data"].get("destination_city"):
                result["data"]["destination_city"]  = s.get("city")
                result["data"]["destination_state"] = s.get("state")
                result["data"]["destination_zip"]   = s.get("zip")
                result["data"]["delivery_date"]     = s.get("date")

    return result


def parse_204(raw: str) -> EDI204LoadTender:
    """Parse EDI 204 and return typed LoadTender model."""
    parsed = parse_edi(raw)
    d = parsed.get("data", {})
    return EDI204LoadTender(
        interchange_id       = parsed.get("interchange_id"),
        broker_mc            = d.get("broker_mc") or parsed.get("sender_id"),
        load_number          = d.get("load_number") or "UNKNOWN",
        equipment_type       = d.get("equipment_type"),
        weight_lbs           = d.get("weight_lbs"),
        commodity            = d.get("commodity"),
        origin_city          = d.get("origin_city"),
        origin_state         = d.get("origin_state"),
        origin_zip           = d.get("origin_zip"),
        pickup_date          = d.get("pickup_date"),
        destination_city     = d.get("destination_city"),
        destination_state    = d.get("destination_state"),
        destination_zip      = d.get("destination_zip"),
        delivery_date        = d.get("delivery_date"),
        rate_total           = d.get("rate_total"),
        special_instructions = d.get("special_instructions"),
        raw_edi              = raw,
    )


def _parse_date(s: str) -> str | None:
    """Convert YYYYMMDD → YYYY-MM-DD."""
    if not s or len(s) < 8:
        return s
    try:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    except Exception:
        return s
