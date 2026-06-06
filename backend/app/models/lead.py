from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Lead(BaseModel):
    id: str | None = None
    source: str = "manual"
    source_ref: str | None = None
    business_name: str | None = None
    company_name: str | None = None
    dot_number: str | None = None
    mc_number: str | None = None
    contact_name: str | None = None
    contact_title: str | None = None
    phone: str | None = None
    phone_number: str | None = None
    email: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    fleet_size: int | None = None
    equipment_type: str | None = None
    equipment_types: list[str] | None = None
    score: int | None = None
    stage: str = "new"
    status: str | None = None
    dot_age_days: int | None = None
    owner_agent: str | None = None
    last_touch_at: datetime | None = None
    next_touch_at: datetime | None = None
    do_not_contact: bool = False
