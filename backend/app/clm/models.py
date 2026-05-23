"""Pydantic models for Contract Lifecycle Management.

ExtractedContractVars implements all 100 master metadata terms from the
logistics CLM specification, organized into 7 operational categories.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ExtractedContractVars(BaseModel):
    """All 100 master metadata terms for logistics contract extraction.

    Fields are grouped into the 7 categories from the CLM specification.
    Legacy field aliases are preserved for backward compatibility.
    """

    # ── Category 1: Carrier & Entity Identification (001–010) ─────────────────
    carrier_name: str | None = None          # 001 carrier_legal_name
    shipper_name: str | None = None          # 002 shipper_legal_name
    broker_name: str | None = None           # 003 broker_legal_name
    dot_number: str | None = None            # 004 DOT Number
    mc_number: str | None = None             # 005 MC Number (also broker_mc)
    broker_mc: str | None = None             # 005 alias used throughout codebase
    scac_code: str | None = None             # 006 Standard Carrier Alpha Code
    consignee_legal_name: str | None = None  # 007 Consignee
    tpl_identifier: str | None = None        # 008 3PL identifier
    subcontractor_permissible: bool | None = None  # 009
    guarantor_entity: str | None = None      # 010

    # ── Category 2: Temporal & Effective Dates (011–020) ──────────────────────
    execution_date: str | None = None        # 011 date contract signed
    effective_date: str | None = None        # 012 rates/commitments go live
    expiration_date: str | None = None       # 013 contract end date
    auto_renewal_notice_days: int | None = None       # 014
    termination_for_convenience_days: int | None = None  # 015
    termination_notice_days: int | None = None        # 015 legacy alias
    claims_filing_time_bar_days: int | None = None    # 016 e.g. 9 months from delivery
    overcharge_dispute_window_days: int | None = None # 017 e.g. 180 days
    spot_quote_validity_period: str | None = None     # 018 hours/days
    rate_amendment_frequency_cap: str | None = None   # 019 e.g. "quarterly"
    force_majeure_notice_deadline: str | None = None  # 020
    # Load-level dates (not in 100-term spec but critical for rate cons / BOLs)
    pickup_date: str | None = None
    delivery_date: str | None = None

    # ── Category 3: Rate & Financial Metrics (021–035) ────────────────────────
    base_linehaul_rate: float | None = None  # 021 $/mile or flat lane fee
    rate_total: float | None = None          # 021 total linehaul (alias)
    rate_per_mile: float | None = None       # 021 per-mile rate (alias)
    fsc_matrix: dict | None = None           # 022 FSC index object {eia_basis, brackets}
    fuel_surcharge: float | None = None      # 022 flat FSC amount (alias)
    detention_rate_per_hour: float | None = None  # 023
    detention_rate: float | None = None      # 023 legacy alias
    layover_fee: float | None = None         # 024
    tonu_fee: float | None = None            # 025 Truck Order Not Used
    tonu: float | None = None                # 025 legacy alias
    lumper_fee_cap: float | None = None      # 026
    lumper_fee: float | None = None          # 026 legacy alias
    multi_stop_drop_premium: float | None = None  # 027
    congestion_surcharge: float | None = None     # 028
    hazmat_premium: float | None = None      # 029
    liftgate_service_fee: float | None = None     # 030
    high_value_cargo_surcharge: float | None = None  # 031
    reconsignment_fee: float | None = None   # 032
    payment_terms: str | None = None         # 033 e.g. "Net-30"
    payment_terms_window: str | None = None  # 033 alias
    quick_pay_discount_rate: float | None = None  # 034 % e.g. 2.0
    quick_pay_discount_pct: float | None = None   # 034 legacy alias
    late_payment_penalty_rate: float | None = None  # 035 %/month
    factoring_allowed: bool | None = None    # financial — factoring permitted
    accessorial_charges: list[dict] = Field(default_factory=list)

    # ── Category 4: Operational & Automated Dispatch Parameters (036–050) ─────
    origin_geofence_radius: float | None = None       # 036 feet/meters
    destination_geofence_radius: float | None = None  # 037 feet/meters
    free_time_pickup_hours: float | None = None       # 038
    free_time_delivery_hours: float | None = None     # 039
    min_tender_acceptance_rate_pct: float | None = None   # 040 SLA %
    spot_tendering_response_window_min: int | None = None # 041 minutes
    dedicated_equipment_quota: int | None = None      # 042 trucks/week
    equipment_type: str | None = None                 # 043 e.g. "53ft Dry Van"
    equipment_type_restrictions: str | None = None    # 043 full restrictions text
    eld_data_sharing_consent: bool | None = None      # 044
    tracking_ping_frequency_min: int | None = None    # 045 minutes
    max_continuous_driving_hours: float | None = None # 046 HOS limit
    cross_docking_permissible: bool | None = None     # 047
    drop_and_hook_consent: bool | None = None         # 048
    blind_shipment_protection: bool | None = None     # 049
    intermodal_authorization: bool | None = None      # 050
    # Load-level operational fields
    load_number: str | None = None
    commodity: str | None = None
    weight_lbs: float | None = None
    team_required: bool | None = None
    special_instructions: str | None = None
    trailer_number: str | None = None
    seal_number: str | None = None

    # ── Category 5: Liability, Cargo & Insurance Bounds (051–070) ─────────────
    cargo_liability_cap: float | None = None        # 051 $/shipment
    insurance_required: float | None = None         # 051 legacy alias
    cgl_limit: float | None = None                  # 052 commercial general liability
    auto_liability_limit: float | None = None       # 053 vehicular coverage
    workers_comp_mandate: bool | None = None        # 054
    temperature_deviation_threshold: str | None = None  # 055 e.g. "34–38°F"
    pre_cooling_verification: bool | None = None    # 056
    moisture_humidity_tolerance_pct: float | None = None  # 057
    inherent_vice_exclusion: bool | None = None     # 058
    act_of_god_exemption: bool | None = None        # 059
    force_majeure: bool | None = None               # 059 legacy alias
    slc_indicator: bool | None = None               # 060 Shippers Load & Count
    seal_integrity_protocol: str | None = None      # 061
    broken_seal_liability_presumption: bool | None = None  # 062
    comingling_restrictions: str | None = None      # 063
    salvage_rights_allocation: str | None = None    # 064 "carrier" | "shipper"
    deductible_allocation_responsibility: str | None = None  # 065
    waiver_of_subrogation: bool | None = None       # 066
    indemnification_scope: str | None = None        # 067 "Limited"|"Intermediate"|"Broad"
    pollution_liability_rider: float | None = None  # 068 coverage amount
    trailer_interchange_cap: float | None = None    # 069
    contaminated_cargo_destruction: bool | None = None  # 070
    # Cargo-level fields (BOL / POD)
    hazmat: bool | None = None
    hazmat_class: str | None = None
    pieces: int | None = None
    freight_class: str | None = None

    # ── Category 6: Service Levels & Compliance SLAs (071–085) ───────────────
    otd_target_pct: float | None = None             # 071 on-time delivery %
    otp_target_pct: float | None = None             # 072 on-time pickup %
    service_level_failure_fine: float | None = None # 073 $/missed appointment
    consecutive_rejection_default_trigger: int | None = None  # 074
    fmcsa_safety_rating_mandate: str | None = None  # 075 e.g. "Satisfactory"
    driver_background_check_required: bool | None = None  # 076
    drug_alcohol_clearinghouse_compliance: bool | None = None  # 077
    carb_compliance_required: bool | None = None    # 078
    ctpat_certification_required: bool | None = None  # 079
    fsma_mandate: bool | None = None                # 080
    safety_equipment_mandate: str | None = None     # 081 PPE requirements
    equipment_age_ceiling_years: int | None = None  # 082
    incident_notification_sla_min: int | None = None  # 083
    qbr_requirement: bool | None = None             # 084 quarterly review
    cap_response_window_days: int | None = None     # 085 corrective action plan

    # ── Category 7: Governance, Legal & Systems Integration (086–100) ─────────
    governing_law_jurisdiction: str | None = None   # 086 state/federal
    governing_law_state: str | None = None          # 086 legacy alias
    dispute_resolution_forum: str | None = None     # 087 city/county/state
    dispute_resolution: str | None = None           # 087 legacy alias
    mandatory_arbitration: bool | None = None       # 088
    mediation_prerequisite_days: int | None = None  # 089
    prevailing_party_fee_shifting: bool | None = None  # 090
    confidentiality_scope: str | None = None        # 091 "Mutual"|"One-Way"|"Multi-Party"
    non_solicitation_window: str | None = None      # 092 e.g. "12 months"
    back_solicitation_liquidated_damages: float | None = None  # 093
    severability_clause: bool | None = None         # 094
    assignment_restrictions: bool | None = None     # 095
    esign_binding_consent: bool | None = None       # 096
    api_edi_standards: str | None = None            # 097 e.g. "EDI 204, 214, 210"
    entirety_of_agreement: bool | None = None       # 098
    language_prevalence: str | None = None          # 099
    sovereign_immunity_waiver: bool | None = None   # 100
    # Broker agreement extras
    auto_renew: bool | None = None
    double_brokering_prohibited: bool | None = None
    cargo_liability_minimum: float | None = None
    # BOL / POD extras
    bol_number: str | None = None
    pro_number: str | None = None
    driver_name: str | None = None
    shipper_address: str | None = None
    consignee_address: str | None = None
    signature_shipper: str | None = None
    signature_driver: str | None = None
    signature_consignee: str | None = None
    actual_pickup_time: str | None = None
    actual_delivery_time: str | None = None
    condition_on_arrival: str | None = None
    exceptions_noted: str | None = None
    pieces_delivered: int | None = None
    weight_delivered: float | None = None
    delivery_time: str | None = None

    # ── Locations (shared across types) ───────────────────────────────────────
    origin_address: str | None = None
    origin_city: str | None = None
    origin_state: str | None = None
    origin_zip: str | None = None
    destination_address: str | None = None
    destination_city: str | None = None
    destination_state: str | None = None
    destination_zip: str | None = None

    # ── Overflow ──────────────────────────────────────────────────────────────
    extra: dict[str, Any] = Field(default_factory=dict)


# ── Invoice models ────────────────────────────────────────────────────────────

class InvoiceLineItem(BaseModel):
    description: str | None = None
    quantity: float | None = None
    unit_price: float | None = None
    amount: float | None = None


class InvoiceExtractedVars(BaseModel):
    """AI-extracted variables from a freight invoice."""
    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    bill_to_name: str | None = None
    bill_to_address: str | None = None
    bill_to_city: str | None = None
    bill_to_state: str | None = None
    bill_to_zip: str | None = None
    remit_to_name: str | None = None
    remit_to_address: str | None = None
    remit_to_city: str | None = None
    remit_to_state: str | None = None
    remit_to_zip: str | None = None
    carrier_name: str | None = None
    carrier_mc: str | None = None
    carrier_dot: str | None = None
    broker_name: str | None = None
    broker_mc: str | None = None
    load_number: str | None = None
    bol_number: str | None = None
    pro_number: str | None = None
    origin_city: str | None = None
    origin_state: str | None = None
    destination_city: str | None = None
    destination_state: str | None = None
    pickup_date: str | None = None
    delivery_date: str | None = None
    line_items: list[InvoiceLineItem] = Field(default_factory=list)
    linehaul_amount: float | None = None
    fuel_surcharge: float | None = None
    detention_amount: float | None = None
    lumper_fee: float | None = None
    tonu_amount: float | None = None
    accessorial_charges: list[dict] = Field(default_factory=list)
    subtotal: float | None = None
    tax_amount: float | None = None
    total_amount_due: float | None = None
    amount_paid: float | None = None
    balance_due: float | None = None
    payment_terms: str | None = None
    quick_pay_discount_pct: float | None = None
    factoring_company: str | None = None
    factoring_notice: bool | None = None
    bank_name: str | None = None
    bank_routing: str | None = None
    bank_account: str | None = None
    check_payable_to: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


# ── Request / Response models ─────────────────────────────────────────────────

class ContractIn(BaseModel):
    carrier_id: UUID | None = None
    contract_type: str = "rate_confirmation"
    raw_text: str | None = None
    document_url: str | None = None


class ContractOut(BaseModel):
    id: UUID
    carrier_id: UUID | None
    contract_type: str
    status: str
    extracted_vars: dict[str, Any]
    counterparty_name: str | None
    rate_total: float | None
    rate_per_mile: float | None
    origin_city: str | None
    destination_city: str | None
    pickup_date: date | None
    delivery_date: date | None
    payment_terms: str | None
    milestone_pct: int
    gl_posted: bool
    auto_approved: bool
    flagged_for_review: bool
    created_at: datetime


class ContractScanRequest(BaseModel):
    raw_text: str
    contract_type: str = "rate_confirmation"
    carrier_id: UUID | None = None


class ContractScanResponse(BaseModel):
    contract_id: UUID
    extracted_vars: ExtractedContractVars
    confidence_score: float
    fields_extracted: int
    warnings: list[str] = Field(default_factory=list)


class ContractMilestoneUpdate(BaseModel):
    milestone_pct: int = Field(ge=0, le=100)
    notes: str | None = None


# ── Email inbound ─────────────────────────────────────────────────────────────

class EmailAttachment(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
    storage_path: str | None = None
    doc_type_guess: str | None = None


class EmailInboundParsed(BaseModel):
    message_id: str
    from_address: str
    subject: str
    received_at: datetime
    attachments: list[EmailAttachment] = Field(default_factory=list)
    body_preview: str | None = None


# ── Rate benchmark ────────────────────────────────────────────────────────────

class RateBenchmarkRequest(BaseModel):
    origin_state: str
    destination_state: str
    equipment_type: str = "dry_van"
    rate_per_mile: float


class RateBenchmarkResult(BaseModel):
    origin_state: str
    destination_state: str
    equipment_type: str
    submitted_rate_per_mile: float
    market_avg_per_mile: float
    market_low_per_mile: float
    market_high_per_mile: float
    variance_pct: float
    assessment: str


# ── Broker blacklist ──────────────────────────────────────────────────────────

class BrokerBlacklistEntry(BaseModel):
    broker_mc: str
    broker_name: str | None = None
    reason: str
    added_by: str = "commander"


class BrokerBlacklistOut(BaseModel):
    id: UUID
    broker_mc: str
    broker_name: str | None
    reason: str
    added_by: str
    added_at: datetime


# ── Broker scorecard ──────────────────────────────────────────────────────────

class BrokerScorecardOut(BaseModel):
    id: UUID
    broker_mc: str
    broker_name: str | None
    total_loads: int
    avg_pay_days: float | None
    on_time_pay_pct: float | None
    dispute_rate_pct: float | None
    avg_rate_per_mile: float | None
    volume_discount_tier: str
    last_updated_at: datetime


# ── Disputes ──────────────────────────────────────────────────────────────────

class DisputeCreate(BaseModel):
    contract_id: UUID
    carrier_id: UUID | None = None
    dispute_type: str
    expected_amount: float
    paid_amount: float
    notes: str | None = None


class DisputeOut(BaseModel):
    id: UUID
    contract_id: UUID
    carrier_id: UUID | None
    dispute_type: str
    expected_amount: float | None
    paid_amount: float | None
    variance_amount: float | None
    status: str
    opened_at: datetime
    escalated_at: datetime | None
    resolved_at: datetime | None
    notes: str | None
    resolution_notes: str | None


class DisputeResolve(BaseModel):
    resolution_notes: str
    paid_amount: float | None = None


# ── CLM Analytics ─────────────────────────────────────────────────────────────

class CLMAnalyticsOut(BaseModel):
    id: UUID
    period_date: date
    total_contracts: int
    total_revenue: float
    avg_rate_per_mile: float | None
    avg_payment_days: float | None
    dispute_count: int
    dispute_rate_pct: float | None
    factored_count: int
    auto_approved_pct: float | None
    computed_at: datetime


# ── Contract export ───────────────────────────────────────────────────────────

class ContractExportOut(BaseModel):
    contract_id: UUID
    contract_type: str
    status: str
    counterparty_name: str | None
    rate_total: float | None
    origin_city: str | None
    destination_city: str | None
    milestone_pct: int
    extracted_vars: dict[str, Any]
    events: list[dict[str, Any]]
    documents: list[dict[str, Any]]
    exported_at: datetime
