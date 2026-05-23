"""Pydantic models for Broker Registry, EDI, and REST integration."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ── Broker core ───────────────────────────────────────────────────────────────

class BrokerIntake(BaseModel):
    """Submitted by a new broker applying to work with 3LL."""
    mc_number: str
    dot_number: str | None = None
    company_name: str
    dba_name: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    payment_terms: str = "Net-30"
    quick_pay_discount_pct: float | None = None
    factoring_allowed: bool = True
    cargo_liability_minimum: float | None = None
    notes: str | None = None


class BrokerOut(BaseModel):
    id: UUID
    mc_number: str
    dot_number: str | None
    company_name: str
    dba_name: str | None
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    city: str | None
    state: str | None
    payment_terms: str | None
    quick_pay_discount_pct: float | None
    factoring_allowed: bool | None
    api_type: str | None
    status: str
    scorecard_score: float | None
    avg_pay_days: float | None
    on_time_pay_pct: float | None
    dispute_rate_pct: float | None
    total_loads: int | None
    total_revenue: float | None
    last_load_at: datetime | None
    onboarded_at: datetime | None
    created_at: datetime


class BrokerUpdate(BaseModel):
    company_name: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    payment_terms: str | None = None
    quick_pay_discount_pct: float | None = None
    factoring_allowed: bool | None = None
    cargo_liability_minimum: float | None = None
    notes: str | None = None
    status: str | None = None


class BrokerStatusUpdate(BaseModel):
    status: str  # pending | active | suspended | blacklisted


# ── EDI integration config ────────────────────────────────────────────────────

class BrokerEDIConfig(BaseModel):
    """Set EDI parameters for a broker."""
    edi_partner_id: str = Field(..., description="ISA06 sender ID, e.g. 'CHROBINSON'")
    edi_qualifier: str = Field(default="02", description="ISA05 qualifier (02=SCAC, 01=DUNS)")


class BrokerRESTConfig(BaseModel):
    """Set REST API parameters for a broker."""
    rest_endpoint: str
    rest_api_key: str = Field(..., description="Plain key — stored encrypted server-side")


# ── EDI transaction models ─────────────────────────────────────────────────────

class EDI204LoadTender(BaseModel):
    """Parsed EDI 204 Motor Carrier Load Tender."""
    transaction_set: str = "204"
    interchange_id: str | None = None
    broker_mc: str | None = None
    load_number: str
    equipment_type: str | None = None
    weight_lbs: float | None = None
    commodity: str | None = None
    hazmat: bool = False
    origin_city: str | None = None
    origin_state: str | None = None
    origin_zip: str | None = None
    pickup_date: str | None = None
    destination_city: str | None = None
    destination_state: str | None = None
    destination_zip: str | None = None
    delivery_date: str | None = None
    rate_total: float | None = None
    payment_terms: str | None = None
    special_instructions: str | None = None
    raw_edi: str | None = None


class EDI990Response(BaseModel):
    """EDI 990 Response to Load Tender."""
    transaction_set: str = "990"
    interchange_id: str
    load_number: str
    response_code: str  # "A" = Accept, "D" = Decline, "C" = Conditional


class EDI214StatusUpdate(BaseModel):
    """EDI 214 Shipment Status Message (3LL → Broker)."""
    transaction_set: str = "214"
    load_number: str
    status_code: str  # X3=Pickup, D1=Delivered, etc.
    status_datetime: str
    city: str | None = None
    state: str | None = None
    driver_name: str | None = None


class EDI210Invoice(BaseModel):
    """EDI 210 Motor Carrier Freight Details and Invoice (3LL → Broker)."""
    transaction_set: str = "210"
    load_number: str
    invoice_number: str
    invoice_date: str
    linehaul_amount: float
    fuel_surcharge: float = 0.0
    detention_amount: float = 0.0
    total_amount: float
    payment_terms: str | None = None


class EDIInboundRequest(BaseModel):
    """Raw EDI payload received from a broker."""
    raw_edi: str
    broker_mc: str | None = None
    edi_partner_id: str | None = None


class EDILogOut(BaseModel):
    id: UUID
    broker_id: UUID | None
    direction: str
    transaction_set: str
    interchange_id: str | None
    load_number: str | None
    status: str
    error_detail: str | None
    created_at: datetime


# ── Broker agreement ──────────────────────────────────────────────────────────

class BrokerAgreementOut(BaseModel):
    id: UUID
    broker_id: UUID
    doc_id: UUID | None
    contract_id: UUID | None
    agreement_type: str
    effective_date: date | None
    expiration_date: date | None
    auto_renew: bool
    status: str
    created_at: datetime


# ── REST connector: Uber Freight ──────────────────────────────────────────────

class UberFreightLoad(BaseModel):
    """Normalized Uber Freight load from their REST API."""
    external_load_id: str
    broker_mc: str = "UF_BROKER"
    origin_city: str | None = None
    origin_state: str | None = None
    destination_city: str | None = None
    destination_state: str | None = None
    pickup_date: str | None = None
    delivery_date: str | None = None
    rate_total: float | None = None
    equipment_type: str | None = None
    weight_lbs: float | None = None
    commodity: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
