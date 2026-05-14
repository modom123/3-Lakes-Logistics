"""Load transformer — normalize loads from DAT, email, and other sources to Supabase schema."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any


def transform_dat_load(dat_load: dict) -> dict:
    """Transform DAT API load response to Supabase loads table schema.

    DAT API response typically includes:
    - equipment, origin, destination, miles, weight, rate info, etc.
    """
    return {
        "load_number": dat_load.get("equipment"),  # DAT uses equipment as load identifier
        "source": "dat",
        "source_id": str(dat_load.get("id")),
        "status": "booked",
        "origin_city": dat_load.get("origin", {}).get("city"),
        "origin_state": dat_load.get("origin", {}).get("state"),
        "origin_address": dat_load.get("origin", {}).get("address"),
        "dest_city": dat_load.get("destination", {}).get("city"),
        "dest_state": dat_load.get("destination", {}).get("state"),
        "dest_address": dat_load.get("destination", {}).get("address"),
        "commodity": dat_load.get("commodity_type"),
        "weight": Decimal(str(dat_load.get("weight", 0))),
        "miles": Decimal(str(dat_load.get("miles", 0))),
        "rate_total": Decimal(str(dat_load.get("rate", 0))),
        "gross_rate": Decimal(str(dat_load.get("rate", 0))),
        "pickup_at": dat_load.get("pickup_at", datetime.utcnow().isoformat()),
        "delivery_at": dat_load.get("delivery_at"),
        "broker_name": dat_load.get("broker_name"),
        "broker_phone": dat_load.get("broker_phone"),
        "shipper_name": dat_load.get("shipper_name"),
        "shipper_phone": dat_load.get("shipper_phone"),
        "equipment_type": dat_load.get("equipment_type"),
        "special_instructions": dat_load.get("notes"),
    }


def transform_rate_confirmation_email(
    email_data: dict,
    extracted_fields: dict | None = None,
) -> dict:
    """Transform rate confirmation email extraction to loads table schema."""
    extracted_fields = extracted_fields or {}

    return {
        "load_number": extracted_fields.get("load_number"),
        "source": "email",
        "status": "booked",
        "origin_city": extracted_fields.get("origin_city"),
        "origin_state": extracted_fields.get("origin_state"),
        "origin_address": extracted_fields.get("origin_address"),
        "dest_city": extracted_fields.get("dest_city"),
        "dest_state": extracted_fields.get("dest_state"),
        "dest_address": extracted_fields.get("dest_address"),
        "commodity": extracted_fields.get("commodity"),
        "weight": _safe_decimal(extracted_fields.get("weight")),
        "miles": _safe_decimal(extracted_fields.get("miles")),
        "rate_total": _safe_decimal(extracted_fields.get("rate")),
        "gross_rate": _safe_decimal(extracted_fields.get("gross_rate")),
        "pickup_at": extracted_fields.get("pickup_date"),
        "delivery_at": extracted_fields.get("delivery_date"),
        "broker_name": extracted_fields.get("broker_name") or email_data.get("from_email"),
        "broker_phone": extracted_fields.get("broker_phone"),
        "shipper_name": extracted_fields.get("shipper_name"),
        "shipper_phone": extracted_fields.get("shipper_phone"),
        "equipment_type": extracted_fields.get("equipment_type"),
        "special_instructions": extracted_fields.get("notes"),
        "rate_confirmed_at": datetime.utcnow().isoformat(),
        "rate_confirmation_notes": email_data.get("subject"),
    }


def _safe_decimal(value: Any) -> Decimal | None:
    """Safely convert value to Decimal, return None if invalid."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ValueError, TypeError):
        return None
