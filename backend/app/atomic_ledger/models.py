"""Pydantic models for the Atomic Ledger event store."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AtomicEvent(BaseModel):
    event_type: str
    event_source: str
    tenant_id: UUID | None = None
    logistics_payload: dict[str, Any] = Field(default_factory=dict)
    financial_payload: dict[str, Any] = Field(default_factory=dict)
    compliance_payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AtomicEventOut(AtomicEvent):
    id: UUID
    created_at: datetime
