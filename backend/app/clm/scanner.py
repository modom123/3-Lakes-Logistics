"""Claude-powered contract scanner and variable extractor.

Uses claude-sonnet-4-6 to extract 100+ structured variables from any logistics
document: rate confirmations, BOLs, PODs, and broker agreements.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from ..settings import get_settings

log = logging.getLogger("3ll.clm.scanner")

_SYSTEM = """You are a logistics contract analyst for 3 Lakes Logistics.
Extract structured variables from trucking documents: rate confirmations, BOLs,
PODs, and broker agreements. Always respond with a single valid JSON object.
Use null for any field not present. Use ISO 8601 dates (YYYY-MM-DD).
Be precise with dollar amounts and locations."""

_RATE_CONF_PROMPT = """Extract all variables from this rate confirmation / load tender.

Return JSON with these fields (null if absent):
broker_name, broker_mc, shipper_name, carrier_name,
load_number, commodity, weight_lbs, equipment_type,
origin_address, origin_city, origin_state, origin_zip,
destination_address, destination_city, destination_state, destination_zip,
pickup_date (YYYY-MM-DD), delivery_date (YYYY-MM-DD),
rate_total (number), rate_per_mile (number), fuel_surcharge (number),
detention_rate ($/hr number), lumper_fee (number), tonu (number),
payment_terms (string e.g. "Net-30"), factoring_allowed (true/false),
accessorial_charges (array of {{type, amount}}),
insurance_required (number — minimum cargo insurance amount),
hazmat (true/false), team_required (true/false),
special_instructions (string),
extra (object for any additional variables not listed above)

Document:
{document_text}"""

_BOL_PROMPT = """Extract all variables from this Bill of Lading (BOL).

Return JSON with these fields (null if absent):
bol_number, pro_number, shipper_name, shipper_address,
consignee_name, consignee_address, carrier_name, carrier_mc, driver_name,
pickup_date (YYYY-MM-DD), delivery_date (YYYY-MM-DD),
commodity, weight_lbs, pieces, freight_class, seal_number, trailer_number,
special_instructions, hazmat (true/false), hazmat_class,
signature_shipper, signature_driver, signature_consignee,
actual_pickup_time, actual_delivery_time,
extra (any additional fields)

Document:
{document_text}"""

_POD_PROMPT = """Extract all variables from this Proof of Delivery (POD).

Return JSON with these fields (null if absent):
load_number, bol_number, carrier_name, driver_name,
consignee_name, consignee_address, delivery_date (YYYY-MM-DD), delivery_time,
condition_on_arrival (string), exceptions_noted (string),
signature_consignee, signature_driver,
pieces_delivered, weight_delivered,
extra (any additional fields)

Document:
{document_text}"""

_BROKER_AGREEMENT_PROMPT = """Extract all variables from this Carrier-Broker Agreement.

Return JSON with these fields (null if absent):
broker_name, broker_mc, broker_address, carrier_name, carrier_mc, carrier_dot,
effective_date (YYYY-MM-DD), expiration_date (YYYY-MM-DD),
payment_terms, quick_pay_discount_pct,
cargo_liability_minimum, factoring_allowed (true/false),
double_brokering_prohibited (true/false), force_majeure (true/false),
dispute_resolution (string), governing_law_state, auto_renew (true/false),
termination_notice_days (number),
extra (any additional fields)

Document:
{document_text}"""

_REQUIRED_FIELDS: dict[str, list[str]] = {
    "rate_confirmation": ["broker_name", "rate_total", "origin_city", "destination_city", "pickup_date"],
    "bol": ["bol_number", "shipper_name", "consignee_name", "commodity"],
    "pod": ["load_number", "consignee_name", "delivery_date"],
    "broker_agreement": ["broker_name", "carrier_name", "payment_terms"],
}

_PROMPTS: dict[str, str] = {
    "rate_confirmation": _RATE_CONF_PROMPT,
    "bol": _BOL_PROMPT,
    "pod": _POD_PROMPT,
    "broker_agreement": _BROKER_AGREEMENT_PROMPT,
}


def scan_contract(
    raw_text: str,
    contract_type: str = "rate_confirmation",
) -> tuple[dict[str, Any], float, list[str]]:
    """Extract structured variables from a contract document using Claude.

    Returns (extracted_vars, confidence_score 0-1, warnings list).
    """
    s = get_settings()
    client = anthropic.Anthropic(api_key=s.anthropic_api_key)

    prompt_template = _PROMPTS.get(contract_type, _RATE_CONF_PROMPT)
    user_prompt = prompt_template.format(document_text=raw_text[:50_000])

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
        )
        content = message.content[0].text.strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        extracted: dict[str, Any] = json.loads(content)
    except json.JSONDecodeError as exc:
        log.warning("CLM scanner JSON parse failed: %s", exc)
        extracted = {}
    except Exception as exc:  # noqa: BLE001
        log.error("CLM scanner Claude API error: %s", exc)
        extracted = {}

    required = _REQUIRED_FIELDS.get(contract_type, [])
    warnings = [f"Missing required field: {f}" for f in required if not extracted.get(f)]

    non_null = sum(
        1 for v in extracted.values()
        if v is not None and v != {} and v != []
    )
    confidence = round(non_null / max(len(extracted), 1), 2)

    return extracted, confidence, warnings
