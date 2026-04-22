"""Read models returned to the command center."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Carrier(BaseModel):
    id: str
    company_name: str
    dot_number: str | None = None
    mc_number: str | None = None
    phone: str | None = None
    email: str | None = None
    plan: str
    status: str
    subscription_status: str | None = None
    onboarded_at: datetime | None = None
    created_at: datetime


class FleetAsset(BaseModel):
    id: str
    carrier_id: str
    truck_id: str
    vin: str | None = None
    year: int | None = None
    make: str | None = None
    model: str | None = None
    trailer_type: str | None = None
    status: str
    last_hos_update: datetime | None = None
