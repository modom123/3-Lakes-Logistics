"""Claude-powered contract scanner — 100-term logistics CLM extraction engine.

Implements the full CLM specification:
  - 100 master metadata terms across 7 operational categories
  - 20 contract class classifier (CON-01 through CON-20)
  - 9 targeted extraction prompts covering every document archetype
  - Auto-classify + auto-extract pipeline via classify_and_scan()

Supported file types: PDF, JPG, PNG, HEIC/HEIF (iPhone), WEBP, GIF.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from ..settings import get_settings

log = logging.getLogger("3ll.clm.scanner")

# ── Shared system prompt ──────────────────────────────────────────────────────

_SYSTEM = """You are a logistics contract analyst for 3 Lakes Logistics.
Extract structured variables from trucking documents. Always respond with a
single valid JSON object. Use null for any field not present in the document.
Use ISO 8601 dates (YYYY-MM-DD). Be precise with dollar amounts, percentages,
and locations. Do not invent or infer values not stated in the document."""

# ── Document classifier ───────────────────────────────────────────────────────

_CLASSIFY_SYSTEM = """You are a trucking document classifier. Identify the
document type and return ONLY a valid JSON object with one key "doc_type".
No explanation — only JSON."""

_CLASSIFY_PROMPT = """Classify this logistics document into exactly one of these types:

rate_confirmation        — spot rate confirmation, load tender, single-trip rate con (CON-04)
dedicated_lane_agreement — multi-week/month lane commitment with fixed volume (CON-05)
master_service_agreement — umbrella MSA governing all loads between shipper and 3PL/broker (CON-01)
broker_carrier_agreement — onboarding agreement between broker and asset carrier (CON-02)
shipper_carrier_agreement — direct shipper-carrier contract, routing guide (CON-03)
owner_operator_lease     — IC/owner-operator lease from logistics company to driver (CON-08)
freight_brokerage_terms  — broker's standard terms and conditions, boilerplate T&C (CON-09)
co_brokerage_agreement   — co-load or co-brokerage between two brokers (CON-12)
fuel_surcharge_addendum  — standalone FSC matrix or addendum to a base agreement (CON-13)
hazmat_transport_rider   — hazardous materials compliance addendum (CON-14)
cross_border_agreement   — US-Mexico or US-Canada cross-border logistics contract (CON-15)
intermodal_agreement     — intermodal interchange, rail/ocean container hauling (CON-06)
tpl_contract             — full 3PL outsourcing agreement, supply chain management (CON-07)
warehouse_bailment       — warehouse, cross-dock, or storage agreement (CON-10)
trailer_interchange_agreement — trailer swap/interchange between carriers (CON-11)
freight_forwarding_agreement  — multi-modal freight forwarding, house BOL (CON-16)
yard_management_contract      — dedicated yard switcher/spotter contract (CON-17)
logistics_tech_saas           — TMS/dispatch software or EDI/API license (CON-18)
cargo_claim_settlement        — post-dispute cargo claim settlement and release (CON-19)
nemt_contract                 — non-emergency medical transportation contract (CON-20)
bol                      — Bill of Lading
pod                      — Proof of Delivery / delivery receipt
invoice                  — freight invoice, carrier invoice, billing statement
w9                       — IRS W-9 tax form
insurance                — certificate of insurance, COI
compliance               — FMCSA authority, drug test, MVR, safety rating
other                    — none of the above

Return ONLY: {{"doc_type": "<type>"}}

Document:
{document_text}"""

# ── Required fields per document type ────────────────────────────────────────

_REQUIRED_FIELDS: dict[str, list[str]] = {
    "rate_confirmation":       ["broker_name", "rate_total", "origin_city", "destination_city", "pickup_date"],
    "dedicated_lane_agreement":["carrier_name", "broker_name", "base_linehaul_rate", "origin_city", "destination_city"],
    "master_service_agreement":["carrier_name", "broker_name", "payment_terms", "effective_date"],
    "broker_carrier_agreement":["broker_name", "carrier_name", "payment_terms"],
    "shipper_carrier_agreement":["shipper_name", "carrier_name", "payment_terms"],
    "owner_operator_lease":    ["carrier_name", "driver_name", "effective_date"],
    "freight_brokerage_terms": ["broker_name", "payment_terms"],
    "co_brokerage_agreement":  ["broker_name", "carrier_name", "effective_date"],
    "fuel_surcharge_addendum": ["broker_name", "fsc_matrix"],
    "hazmat_transport_rider":  ["carrier_name", "hazmat_class", "cargo_liability_cap"],
    "cross_border_agreement":  ["carrier_name", "broker_name", "governing_law_jurisdiction"],
    "intermodal_agreement":    ["carrier_name", "intermodal_authorization"],
    "tpl_contract":            ["carrier_name", "broker_name", "effective_date", "payment_terms"],
    "warehouse_bailment":      ["carrier_name", "shipper_name", "effective_date"],
    "trailer_interchange_agreement": ["carrier_name", "trailer_interchange_cap"],
    "freight_forwarding_agreement":  ["broker_name", "effective_date"],
    "yard_management_contract":      ["carrier_name", "shipper_name", "dedicated_equipment_quota"],
    "logistics_tech_saas":           ["broker_name", "api_edi_standards", "effective_date"],
    "cargo_claim_settlement":        ["carrier_name", "cargo_liability_cap", "execution_date"],
    "nemt_contract":                 ["carrier_name", "otd_target_pct", "effective_date"],
    "bol":     ["bol_number", "shipper_name", "consignee_legal_name", "commodity"],
    "pod":     ["load_number", "consignee_legal_name", "delivery_date"],
    "invoice": ["invoice_number", "total_amount_due", "carrier_name"],
}

# ── Extraction prompts ────────────────────────────────────────────────────────
# Each prompt targets the fields most likely present in that document class.
# All prompts use the same 100-term field name vocabulary from the CLM spec.

_RATE_CONF_PROMPT = """Extract all variables from this rate confirmation / load tender / dedicated lane rate sheet.

Return JSON (null for absent fields):

carrier_name, carrier_mc, carrier_dot, scac_code,
broker_name, broker_mc, shipper_name, consignee_legal_name,
tpl_identifier, subcontractor_permissible,
load_number, commodity, weight_lbs, equipment_type, equipment_type_restrictions,
trailer_number, seal_number, pieces, freight_class,
origin_address, origin_city, origin_state, origin_zip,
destination_address, destination_city, destination_state, destination_zip,
execution_date, pickup_date, delivery_date, spot_quote_validity_period,
base_linehaul_rate, rate_total, rate_per_mile,
fuel_surcharge, fsc_matrix (object: {{eia_basis, per_gallon_bracket, pct_add}} or null),
detention_rate_per_hour, free_time_pickup_hours, free_time_delivery_hours,
layover_fee, tonu_fee, lumper_fee_cap, multi_stop_drop_premium,
congestion_surcharge, hazmat_premium, liftgate_service_fee,
high_value_cargo_surcharge, reconsignment_fee,
accessorial_charges (array of {{type, amount}}),
payment_terms, quick_pay_discount_rate, late_payment_penalty_rate,
factoring_allowed,
spot_tendering_response_window_min, dedicated_equipment_quota,
eld_data_sharing_consent, tracking_ping_frequency_min,
drop_and_hook_consent, cross_docking_permissible,
blind_shipment_protection, intermodal_authorization,
cargo_liability_cap, cgl_limit, auto_liability_limit, workers_comp_mandate,
insurance_required,
hazmat, hazmat_class,
temperature_deviation_threshold, pre_cooling_verification,
slc_indicator, seal_integrity_protocol, broken_seal_liability_presumption,
comingling_restrictions, contaminated_cargo_destruction,
fmcsa_safety_rating_mandate, carb_compliance_required, fsma_mandate,
ctpat_certification_required, driver_background_check_required,
drug_alcohol_clearinghouse_compliance, safety_equipment_mandate,
equipment_age_ceiling_years, incident_notification_sla_min,
governing_law_jurisdiction, force_majeure, force_majeure_notice_deadline,
dispute_resolution, mandatory_arbitration,
team_required, special_instructions,
extra (object for any fields not listed above)

Document:
{document_text}"""


_AGREEMENT_PROMPT = """Extract all variables from this carrier/broker/shipper agreement or master service contract.
This includes MSAs, broker-carrier agreements, shipper-carrier agreements, 3PL contracts,
freight brokerage T&C, co-brokerage agreements, and similar legal frameworks.

Return JSON covering all 100 CLM master metadata terms (null for absent):

# Category 1 — Entity Identification
carrier_name, carrier_mc, carrier_dot, scac_code,
broker_name, broker_mc, broker_address,
shipper_name, consignee_legal_name,
tpl_identifier, subcontractor_permissible, guarantor_entity,

# Category 2 — Dates
execution_date, effective_date, expiration_date,
auto_renewal_notice_days, termination_for_convenience_days,
claims_filing_time_bar_days, overcharge_dispute_window_days,
spot_quote_validity_period, rate_amendment_frequency_cap,
force_majeure_notice_deadline,

# Category 3 — Financial
base_linehaul_rate, rate_per_mile,
fsc_matrix (object: {{eia_basis, per_gallon_bracket, pct_add}} or null),
detention_rate_per_hour, layover_fee, tonu_fee, lumper_fee_cap,
multi_stop_drop_premium, congestion_surcharge, hazmat_premium,
liftgate_service_fee, high_value_cargo_surcharge, reconsignment_fee,
payment_terms, quick_pay_discount_rate, late_payment_penalty_rate,
factoring_allowed, double_brokering_prohibited,
accessorial_charges (array of {{type, amount}}),

# Category 4 — Operational Dispatch
origin_geofence_radius, destination_geofence_radius,
free_time_pickup_hours, free_time_delivery_hours,
min_tender_acceptance_rate_pct, spot_tendering_response_window_min,
dedicated_equipment_quota, equipment_type, equipment_type_restrictions,
eld_data_sharing_consent, tracking_ping_frequency_min,
max_continuous_driving_hours,
cross_docking_permissible, drop_and_hook_consent,
blind_shipment_protection, intermodal_authorization,

# Category 5 — Liability & Insurance
cargo_liability_cap, cgl_limit, auto_liability_limit, workers_comp_mandate,
temperature_deviation_threshold, pre_cooling_verification,
moisture_humidity_tolerance_pct,
inherent_vice_exclusion, act_of_god_exemption,
slc_indicator, seal_integrity_protocol, broken_seal_liability_presumption,
comingling_restrictions, salvage_rights_allocation,
deductible_allocation_responsibility, waiver_of_subrogation,
indemnification_scope, pollution_liability_rider,
trailer_interchange_cap, contaminated_cargo_destruction,

# Category 6 — SLAs & Compliance
otd_target_pct, otp_target_pct, service_level_failure_fine,
consecutive_rejection_default_trigger,
fmcsa_safety_rating_mandate, driver_background_check_required,
drug_alcohol_clearinghouse_compliance, carb_compliance_required,
ctpat_certification_required, fsma_mandate,
safety_equipment_mandate, equipment_age_ceiling_years,
incident_notification_sla_min, qbr_requirement, cap_response_window_days,

# Category 7 — Governance
governing_law_jurisdiction, dispute_resolution_forum,
mandatory_arbitration, mediation_prerequisite_days,
prevailing_party_fee_shifting, confidentiality_scope,
non_solicitation_window, back_solicitation_liquidated_damages,
severability_clause, assignment_restrictions, esign_binding_consent,
api_edi_standards, entirety_of_agreement,
language_prevalence, sovereign_immunity_waiver,
auto_renew, termination_notice_days,
force_majeure, force_majeure_notice_deadline,
special_instructions,
extra (object for any fields not listed above)

Document:
{document_text}"""


_BOL_PROMPT = """Extract all variables from this Bill of Lading (BOL).

Return JSON (null for absent fields):
bol_number, pro_number, load_number,
shipper_name, shipper_address, shipper_address, origin_city, origin_state, origin_zip,
consignee_legal_name, consignee_address, destination_city, destination_state, destination_zip,
carrier_name, carrier_mc, carrier_dot, scac_code,
driver_name, trailer_number, seal_number,
pickup_date, delivery_date, actual_pickup_time, actual_delivery_time,
commodity, weight_lbs, pieces, freight_class, equipment_type,
hazmat, hazmat_class,
slc_indicator, seal_integrity_protocol, broken_seal_liability_presumption,
comingling_restrictions, blind_shipment_protection,
temperature_deviation_threshold, pre_cooling_verification,
contaminated_cargo_destruction,
signature_shipper, signature_driver, signature_consignee,
special_instructions, team_required,
extra (any additional fields)

Document:
{document_text}"""


_POD_PROMPT = """Extract all variables from this Proof of Delivery (POD) or delivery receipt.

Return JSON (null for absent fields):
load_number, bol_number, pro_number,
carrier_name, driver_name,
consignee_legal_name, consignee_address, destination_city, destination_state,
delivery_date, delivery_time, actual_delivery_time,
pieces_delivered, weight_delivered,
condition_on_arrival, exceptions_noted,
broken_seal_liability_presumption, slc_indicator,
signature_consignee, signature_driver,
extra (any additional fields)

Document:
{document_text}"""


_INVOICE_PROMPT = """Extract all variables from this freight invoice or carrier billing statement.

Return JSON (null for absent fields):
invoice_number, invoice_date, due_date,
bill_to_name, bill_to_address, bill_to_city, bill_to_state, bill_to_zip,
remit_to_name, remit_to_address, remit_to_city, remit_to_state, remit_to_zip,
carrier_name, carrier_mc, carrier_dot,
broker_name, broker_mc,
load_number, bol_number, pro_number,
origin_city, origin_state, destination_city, destination_state,
pickup_date, delivery_date,
line_items (array of {{description, quantity, unit_price, amount}}),
base_linehaul_rate, fuel_surcharge, detention_rate_per_hour,
layover_fee, tonu_fee, lumper_fee_cap,
congestion_surcharge, liftgate_service_fee, hazmat_premium,
reconsignment_fee, multi_stop_drop_premium,
accessorial_charges (array of {{type, amount}}),
subtotal, tax_amount, total_amount_due, amount_paid, balance_due,
payment_terms, quick_pay_discount_rate, late_payment_penalty_rate,
factoring_allowed, factoring_company, factoring_notice,
bank_name, bank_routing, bank_account, check_payable_to,
overcharge_dispute_window_days,
extra (any additional fields)

Document:
{document_text}"""


_OWNER_OPERATOR_LEASE_PROMPT = """Extract all variables from this Independent Contractor / Owner-Operator Lease agreement.

Return JSON (null for absent fields):
carrier_name, carrier_mc, carrier_dot, scac_code,
driver_name, driver_mc, driver_dot,
execution_date, effective_date, expiration_date,
equipment_type, equipment_type_restrictions, trailer_number,
equipment_age_ceiling_years,
base_linehaul_rate, rate_per_mile, fuel_surcharge,
detention_rate_per_hour, layover_fee, tonu_fee,
payment_terms, quick_pay_discount_rate, factoring_allowed,
escrow_amount, insurance_deduction_pct,
auto_liability_limit, cargo_liability_cap, workers_comp_mandate,
eld_data_sharing_consent, tracking_ping_frequency_min,
max_continuous_driving_hours,
fmcsa_safety_rating_mandate, driver_background_check_required,
drug_alcohol_clearinghouse_compliance, carb_compliance_required,
safety_equipment_mandate,
governing_law_jurisdiction, dispute_resolution_forum,
mandatory_arbitration, assignment_restrictions,
termination_for_convenience_days, severability_clause,
esign_binding_consent, entirety_of_agreement,
subcontractor_permissible,
force_majeure, special_instructions,
extra (any additional fields)

Document:
{document_text}"""


_HAZMAT_RIDER_PROMPT = """Extract all variables from this HazMat transport rider, compliance addendum, or dangerous goods agreement.

Return JSON (null for absent fields):
carrier_name, carrier_mc, carrier_dot,
broker_name, broker_mc, shipper_name,
effective_date, expiration_date,
hazmat, hazmat_class, hazmat_premium,
cargo_liability_cap, pollution_liability_rider, cgl_limit, auto_liability_limit,
temperature_deviation_threshold, pre_cooling_verification,
contaminated_cargo_destruction,
ctpat_certification_required, carb_compliance_required,
fmcsa_safety_rating_mandate,
equipment_type, equipment_type_restrictions,
seal_integrity_protocol, broken_seal_liability_presumption,
incident_notification_sla_min,
governing_law_jurisdiction, dispute_resolution_forum,
force_majeure, special_instructions,
extra (any additional fields)

Document:
{document_text}"""


_FUEL_SURCHARGE_ADDENDUM_PROMPT = """Extract all variables from this fuel surcharge addendum or FSC matrix document.

Return JSON (null for absent fields):
broker_name, broker_mc, carrier_name, carrier_mc,
effective_date, expiration_date,
fsc_matrix (object: {{
  eia_basis: "EIA Weekly Retail On-Highway Diesel",
  brackets: [{{min_price, max_price, surcharge_pct}}],
  adjustment_frequency: "weekly"|"monthly"
}}),
fuel_surcharge,
rate_amendment_frequency_cap,
base_linehaul_rate, rate_per_mile,
payment_terms, governing_law_jurisdiction,
extra (any additional fields)

Document:
{document_text}"""


_CARGO_CLAIM_PROMPT = """Extract all variables from this cargo claim settlement and release document.

Return JSON (null for absent fields):
carrier_name, carrier_mc, carrier_dot,
shipper_name, consignee_legal_name, broker_name,
load_number, bol_number, pro_number,
execution_date, delivery_date,
commodity, weight_lbs, pieces,
cargo_liability_cap, deductible_allocation_responsibility,
salvage_rights_allocation, waiver_of_subrogation,
settlement_amount, paid_amount, balance_due,
payment_terms,
inherent_vice_exclusion, act_of_god_exemption,
slc_indicator, broken_seal_liability_presumption,
contaminated_cargo_destruction,
release_scope, release_effective_date,
governing_law_jurisdiction, dispute_resolution_forum,
mandatory_arbitration, severability_clause,
entirety_of_agreement, esign_binding_consent,
special_instructions,
extra (any additional fields)

Document:
{document_text}"""


_CROSS_BORDER_PROMPT = """Extract all variables from this cross-border logistics agreement (US-Mexico or US-Canada).

Return JSON (null for absent fields):
carrier_name, carrier_mc, carrier_dot, scac_code,
broker_name, broker_mc, shipper_name, consignee_legal_name,
tpl_identifier,
execution_date, effective_date, expiration_date,
origin_city, origin_state, destination_city, destination_state,
base_linehaul_rate, rate_per_mile, fuel_surcharge,
detention_rate_per_hour, payment_terms, quick_pay_discount_rate,
cargo_liability_cap, cgl_limit, auto_liability_limit,
hazmat, hazmat_class, hazmat_premium,
ctpat_certification_required, carb_compliance_required, fsma_mandate,
customs_broker_required, incoterms, currency,
border_crossing_point, drayage_provider,
equipment_type, equipment_type_restrictions,
governing_law_jurisdiction, language_prevalence,
dispute_resolution_forum, mandatory_arbitration,
sovereign_immunity_waiver, cross_border_permit,
force_majeure, special_instructions,
extra (any additional fields)

Document:
{document_text}"""


# ── Prompt routing table ──────────────────────────────────────────────────────
# Maps every CON class + legacy type → extraction prompt

_PROMPTS: dict[str, str] = {
    # Load-level documents
    "rate_confirmation":        _RATE_CONF_PROMPT,
    "dedicated_lane_agreement": _RATE_CONF_PROMPT,
    "spot_rate_confirmation":   _RATE_CONF_PROMPT,
    # Agreement / governance documents
    "master_service_agreement": _AGREEMENT_PROMPT,
    "broker_carrier_agreement": _AGREEMENT_PROMPT,
    "broker_agreement":         _AGREEMENT_PROMPT,   # legacy
    "shipper_carrier_agreement":_AGREEMENT_PROMPT,
    "tpl_contract":             _AGREEMENT_PROMPT,
    "freight_brokerage_terms":  _AGREEMENT_PROMPT,
    "co_brokerage_agreement":   _AGREEMENT_PROMPT,
    "intermodal_agreement":     _AGREEMENT_PROMPT,
    "warehouse_bailment":       _AGREEMENT_PROMPT,
    "trailer_interchange_agreement": _AGREEMENT_PROMPT,
    "freight_forwarding_agreement":  _AGREEMENT_PROMPT,
    "yard_management_contract":      _AGREEMENT_PROMPT,
    "logistics_tech_saas":           _AGREEMENT_PROMPT,
    "nemt_contract":                 _AGREEMENT_PROMPT,
    # Specialized documents
    "owner_operator_lease":     _OWNER_OPERATOR_LEASE_PROMPT,
    "hazmat_transport_rider":   _HAZMAT_RIDER_PROMPT,
    "fuel_surcharge_addendum":  _FUEL_SURCHARGE_ADDENDUM_PROMPT,
    "cargo_claim_settlement":   _CARGO_CLAIM_PROMPT,
    "cross_border_agreement":   _CROSS_BORDER_PROMPT,
    # Transactional documents
    "bol":     _BOL_PROMPT,
    "pod":     _POD_PROMPT,
    "invoice": _INVOICE_PROMPT,
}

_KNOWN_TYPES = frozenset(_PROMPTS.keys())


# ── Classifier ────────────────────────────────────────────────────────────────

def classify_document_type(raw_text: str) -> str:
    """Identify the logistics document class from text using Claude.

    Returns one of the 20+ CON class types or legacy types.
    Falls back to "rate_confirmation" on error.
    """
    s = get_settings()
    client = anthropic.Anthropic(api_key=s.anthropic_api_key)

    prompt = _CLASSIFY_PROMPT.format(document_text=raw_text[:8_000])
    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=64,
            system=_CLASSIFY_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        result = json.loads(text)
        doc_type = str(result.get("doc_type", "rate_confirmation")).lower().strip()
        log.info("classify_document_type → %s", doc_type)
        return doc_type if doc_type in _KNOWN_TYPES else "rate_confirmation"
    except Exception as exc:
        log.warning("classify_document_type failed: %s — defaulting to rate_confirmation", exc)
        return "rate_confirmation"


def classify_and_scan(
    raw_text: str,
    hint: str | None = None,
) -> tuple[str, dict[str, Any], float, list[str]]:
    """Classify a document type then extract all variables.

    If hint is a known type, skips classification.
    Returns (detected_type, extracted_vars, confidence, warnings).
    """
    contract_type = hint if hint and hint in _KNOWN_TYPES else classify_document_type(raw_text)
    extracted, confidence, warnings = scan_contract(raw_text, contract_type)
    return contract_type, extracted, confidence, warnings


# ── Core extractor ────────────────────────────────────────────────────────────

def scan_contract(
    raw_text: str,
    contract_type: str = "rate_confirmation",
) -> tuple[dict[str, Any], float, list[str]]:
    """Extract structured variables from contract text using Claude.

    Returns (extracted_vars dict, confidence_score 0-1, warnings list).
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

        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        extracted: dict[str, Any] = json.loads(content)
    except json.JSONDecodeError as exc:
        log.warning("CLM scanner JSON parse failed: %s", exc)
        extracted = {}
    except Exception as exc:
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
