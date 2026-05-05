"""Pydantic models for Contract Lifecycle Management."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ExtractedContractVars(BaseModel):
    """AI-extracted variables from a scanned contract document."""
    # Parties
    broker_name: str | None = None
    broker_mc: str | None = None
    shipper_name: str | None = None
    carrier_name: str | None = None

    # Load identity
    load_number: str | None = None
    commodity: str | None = None
    weight_lbs: float | None = None
    equipment_type: str | None = None

    # Locations
    origin_address: str | None = None
    origin_city: str | None = None
    origin_state: str | None = None
    origin_zip: str | None = None
    destination_address: str | None = None
    destination_city: str | None = None
    destination_state: str | None = None
    destination_zip: str | None = None

    # Dates
    pickup_date: str | None = None
    delivery_date: str | None = None

    # Financials
    rate_total: float | None = None
    rate_per_mile: float | None = None
    fuel_surcharge: float | None = None
    detention_rate: float | None = None
    lumper_fee: float | None = None
    tonu: float | None = None
    payment_terms: str | None = None
    factoring_allowed: bool | None = None
    accessorial_charges: list[dict] = Field(default_factory=list)

    # Compliance
    insurance_required: float | None = None
    hazmat: bool | None = None
    team_required: bool | None = None
    force_majeure: bool | None = None
    special_instructions: str | None = None

    # Broker agreement extras
    governing_law_state: str | None = None
    auto_renew: bool | None = None
    termination_notice_days: int | None = None
    dispute_resolution: str | None = None

    # Overflow for any additional variables Claude finds
    extra: dict[str, Any] = Field(default_factory=dict)


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


# ── Email inbound parsing ────────────────────────────────────────────────────

class EmailAttachment(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
    storage_path: str | None = None
    doc_type_guess: str | None = None  # rate_conf | bol | pod | broker_agreement


class EmailInboundParsed(BaseModel):
    message_id: str
    from_address: str
    subject: str
    received_at: datetime
    attachments: list[EmailAttachment] = Field(default_factory=list)
    body_preview: str | None = None


# ── Rate benchmark ───────────────────────────────────────────────────────────

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
    assessment: str  # below_market | at_market | above_market


# ── Broker blacklist ─────────────────────────────────────────────────────────

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


# ── Broker scorecard ─────────────────────────────────────────────────────────

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


# ── Disputes ─────────────────────────────────────────────────────────────────

class DisputeCreate(BaseModel):
    contract_id: UUID
    carrier_id: UUID | None = None
    dispute_type: str  # short_pay | no_pay | rate_variance | damage | detention_denied
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
