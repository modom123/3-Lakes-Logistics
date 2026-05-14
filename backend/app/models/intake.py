"""Pydantic model for the 6-step intake form on index (7).html.

Field names match the form input IDs and the Supabase column names
exactly so oSub() → POST /api/carriers/intake round-trips cleanly.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


Plan = Literal["founders", "standard", "pro", "enterprise"]

_TRAILER_ALIASES = {
    "dry van": "dry_van", "dry_van": "dry_van", "dryvan": "dry_van", "van": "dry_van",
    "reefer": "reefer", "refrigerated": "reefer", "refer": "reefer",
    "flatbed": "flatbed", "flat bed": "flatbed", "step deck": "flatbed",
    "stepdeck": "flatbed", "step_deck": "flatbed",
    "flatbed/step deck": "flatbed", "flatbed / step deck": "flatbed",
    "box truck": "box_truck", "box_truck": "box_truck",
    "box 26": "box_truck", "box26": "box_truck", "box truck 26": "box_truck",
    "box truck 26' non cdl": "box_truck",
    "cargo van": "cargo_van", "cargo_van": "cargo_van",
    "tanker": "tanker", "hazmat": "tanker", "tanker_hazmat": "tanker",
    "tanker/hazmat": "tanker", "tanker / hazmat": "tanker",
    "hotshot": "hotshot", "hot shot": "hotshot", "hot-shot": "hotshot",
    "auto": "auto", "auto hauler": "auto", "car hauler": "auto",
    "auto carrier": "auto",
}
_ELD_ALIASES = {
    "motive": "motive", "keeptruckin": "motive",
    "samsara": "samsara", "geotab": "geotab", "omnitracs": "omnitracs",
}


def _norm_trailer(v: str | None) -> str:
    if not v:
        return "dry_van"
    k = v.strip().lower()
    return _TRAILER_ALIASES.get(k, "dry_van")


def _norm_eld(v: str | None) -> str:
    if not v:
        return "other"
    k = v.strip().lower()
    return _ELD_ALIASES.get(k, "other")


class CarrierIntake(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # --- Step 1: Company / Authority ---
    company_name: str = Field(min_length=2)
    legal_entity: str | None = None
    dot_number: str | None = None
    mc_number: str | None = None
    ein: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    years_in_business: int | None = None

    # Allow the form's `owner_phone` / `owner_email` alternates
    owner_phone: str | None = None
    owner_email: str | None = None
    address_city: str | None = None
    address_state: str | None = None
    address_zip: str | None = None

    # --- Step 2: Fleet asset (first truck at intake) ---
    truck_id: str | None = None
    vin: str | None = None
    year: int | None = None
    make: str | None = None
    model: str | None = None
    trailer_type: str = "dry_van"
    max_weight: int | None = None
    equipment_count: int = 1

    # --- Step 3: ELD / Telematics ---
    eld_provider: str = "other"
    eld_api_token: str | None = None
    eld_account_id: str | None = None

    @field_validator("trailer_type", mode="before")
    @classmethod
    def _normalize_trailer(cls, v):  # noqa: D401
        return _norm_trailer(v)

    @field_validator("eld_provider", mode="before")
    @classmethod
    def _normalize_eld(cls, v):  # noqa: D401
        return _norm_eld(v)

    # --- Step 4: Insurance / Compliance (Shield) ---
    insurance_carrier: str | None = None
    policy_number: str | None = None
    policy_expiry: str | None = None  # ISO date
    coi_upload_name: str | None = None
    bmc91_ack: bool = False
    mcs90_ack: bool = False
    safer_consent: bool = False
    csa_consent: bool = False
    clearinghouse_consent: bool = False
    psp_consent: bool = False

    # --- Step 4b: CDL / Driver License (Shield CDL monitoring) ---
    driver_name: str | None = None
    cdl_number: str | None = None
    cdl_state: str | None = None
    cdl_class: Literal["A", "B", "C"] | None = None
    cdl_expiry: str | None = None          # ISO date — triggers Shield step 157
    medical_card_expiry: str | None = None  # DOT physical (2-yr cycle)
    clearinghouse_enrolled: bool = False

    # --- Step 5: Banking (Settler) ---
    bank_routing: str | None = None   # last 4 stored; token kept in provider
    bank_account: str | None = None   # last 4 stored
    account_type: Literal["checking", "savings"] | None = None
    payee_name: str | None = None
    w9_upload_name: str | None = None

    # --- Step 6: Plan + e-sign ---
    plan: Plan = "founders"
    founders_truck_count: int = 1  # How many trucks for founders program (if plan == "founders")
    esign_name: str
    esign_ip: str | None = None
    esign_user_agent: str | None = None
    agreement_pdf_hash: str | None = None


class IntakeResponse(BaseModel):
    ok: bool
    carrier_id: str
    stripe_checkout_url: str | None = None
    next_step: str
