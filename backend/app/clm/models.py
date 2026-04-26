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
