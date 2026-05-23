"""Broker registry — CRUD + onboarding + integration config.

Endpoints
─────────
  POST   /api/brokers/intake          Register a new broker (pending → approval)
  GET    /api/brokers                 List all brokers with filters
  GET    /api/brokers/{broker_id}     Broker detail + agreements + EDI log
  PATCH  /api/brokers/{broker_id}     Update contact/financial fields
  PATCH  /api/brokers/{broker_id}/status   Approve / suspend / blacklist
  POST   /api/brokers/{broker_id}/approve  Shortcut: pending → active + fire onboarding
  POST   /api/brokers/{broker_id}/edi-config   Set EDI partner ID / qualifier
  POST   /api/brokers/{broker_id}/rest-config  Set REST endpoint + API key
  GET    /api/brokers/{broker_id}/agreements   Broker agreements from vault
  GET    /api/brokers/{broker_id}/edi-log      Recent EDI transactions
  GET    /api/brokers/scorecard/top            Top brokers by scorecard score
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..logging_service import get_logger
from ..models.broker import (
    BrokerEDIConfig, BrokerIntake, BrokerOut,
    BrokerRESTConfig, BrokerStatusUpdate, BrokerUpdate,
)
from ..supabase_client import get_supabase
from .deps import require_bearer

log = get_logger("3ll.brokers")
router = APIRouter(dependencies=[Depends(require_bearer)])


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_broker_or_404(broker_id: str) -> dict:
    res = get_supabase().table("brokers").select("*").eq("id", broker_id).maybe_single().execute()
    if not res.data:
        raise HTTPException(404, "broker not found")
    return res.data


# ── Intake ────────────────────────────────────────────────────────────────────

@router.post("/intake", status_code=status.HTTP_201_CREATED)
def broker_intake(payload: BrokerIntake) -> dict:
    """New broker application — stored as 'pending' until approved."""
    sb = get_supabase()

    existing = sb.table("brokers").select("id, status").eq("mc_number", payload.mc_number).maybe_single().execute()
    if existing.data:
        return {
            "ok": False,
            "broker_id": existing.data["id"],
            "status": existing.data["status"],
            "message": "broker already registered",
        }

    row = {
        "mc_number":               payload.mc_number,
        "dot_number":              payload.dot_number,
        "company_name":            payload.company_name,
        "dba_name":                payload.dba_name,
        "contact_name":            payload.contact_name,
        "contact_email":           payload.contact_email,
        "contact_phone":           payload.contact_phone,
        "address":                 payload.address,
        "city":                    payload.city,
        "state":                   payload.state,
        "zip":                     payload.zip,
        "payment_terms":           payload.payment_terms,
        "quick_pay_discount_pct":  payload.quick_pay_discount_pct,
        "factoring_allowed":       payload.factoring_allowed,
        "cargo_liability_minimum": payload.cargo_liability_minimum,
        "notes":                   payload.notes,
        "status":                  "pending",
        "api_type":                "manual",
    }

    res = sb.table("brokers").insert(row).execute()
    broker_id = res.data[0]["id"]
    log.info("broker_intake mc=%s id=%s", payload.mc_number, broker_id)
    return {"ok": True, "broker_id": broker_id, "status": "pending"}


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("/")
def list_brokers(
    status_filter: str | None = Query(default=None, alias="status"),
    api_type: str | None = None,
    state: str | None = None,
    limit: int = 200,
) -> dict:
    sb = get_supabase()
    q = sb.table("brokers").select("*").order("scorecard_score", desc=True, nullsfirst=False).limit(limit)
    if status_filter:
        q = q.eq("status", status_filter)
    if api_type:
        q = q.eq("api_type", api_type)
    if state:
        q = q.eq("state", state)
    res = q.execute()
    return {"count": len(res.data or []), "items": res.data or []}


@router.get("/scorecard/top")
def top_brokers(limit: int = 20) -> dict:
    """Top brokers by composite scorecard score (set by Marcus Webb daily)."""
    sb = get_supabase()
    res = (
        sb.table("brokers")
        .select("id, company_name, mc_number, scorecard_score, avg_pay_days, on_time_pay_pct, dispute_rate_pct, total_loads, total_revenue, status")
        .eq("status", "active")
        .order("scorecard_score", desc=True, nullsfirst=False)
        .limit(limit)
        .execute()
    )
    return {"count": len(res.data or []), "items": res.data or []}


# ── Detail ─────────────────────────────────────────────────────────────────────

@router.get("/{broker_id}")
def get_broker(broker_id: str) -> dict:
    broker = _get_broker_or_404(broker_id)
    sb = get_supabase()

    agreements = sb.table("broker_agreements").select("*").eq("broker_id", broker_id).order("created_at", desc=True).execute()
    edi_log = sb.table("broker_edi_log").select("id, direction, transaction_set, load_number, status, created_at").eq("broker_id", broker_id).order("created_at", desc=True).limit(50).execute()

    return {
        **broker,
        "agreements": agreements.data or [],
        "recent_edi": edi_log.data or [],
    }


# ── Update ────────────────────────────────────────────────────────────────────

@router.patch("/{broker_id}")
def update_broker(broker_id: str, payload: BrokerUpdate) -> dict:
    _get_broker_or_404(broker_id)
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update:
        return {"ok": True, "message": "nothing to update"}
    get_supabase().table("brokers").update(update).eq("id", broker_id).execute()
    log.info("broker_update id=%s fields=%s", broker_id, list(update.keys()))
    return {"ok": True, "broker_id": broker_id, "updated": list(update.keys())}


@router.patch("/{broker_id}/status")
def update_broker_status(broker_id: str, payload: BrokerStatusUpdate) -> dict:
    valid = {"pending", "active", "suspended", "blacklisted"}
    if payload.status not in valid:
        raise HTTPException(400, f"status must be one of {valid}")
    _get_broker_or_404(broker_id)
    get_supabase().table("brokers").update({"status": payload.status}).eq("id", broker_id).execute()
    log.info("broker_status id=%s → %s", broker_id, payload.status)
    return {"ok": True, "broker_id": broker_id, "status": payload.status}


@router.post("/{broker_id}/approve")
def approve_broker(broker_id: str) -> dict:
    """Move a pending broker to active and stamp onboarded_at."""
    _get_broker_or_404(broker_id)
    now = datetime.now(timezone.utc).isoformat()
    get_supabase().table("brokers").update({
        "status": "active",
        "onboarded_at": now,
    }).eq("id", broker_id).execute()
    log.info("broker_approved id=%s", broker_id)
    return {"ok": True, "broker_id": broker_id, "status": "active", "onboarded_at": now}


# ── Integration config ────────────────────────────────────────────────────────

@router.post("/{broker_id}/edi-config")
def set_edi_config(broker_id: str, cfg: BrokerEDIConfig) -> dict:
    """Configure EDI partner ID for a broker (enables inbound 204 matching)."""
    _get_broker_or_404(broker_id)
    get_supabase().table("brokers").update({
        "api_type":       "edi",
        "edi_partner_id": cfg.edi_partner_id,
        "edi_qualifier":  cfg.edi_qualifier,
    }).eq("id", broker_id).execute()
    log.info("broker_edi_config id=%s partner=%s", broker_id, cfg.edi_partner_id)
    return {"ok": True, "broker_id": broker_id, "api_type": "edi", "edi_partner_id": cfg.edi_partner_id}


@router.post("/{broker_id}/rest-config")
def set_rest_config(broker_id: str, cfg: BrokerRESTConfig) -> dict:
    """Configure REST API endpoint for a broker (enables load polling)."""
    _get_broker_or_404(broker_id)
    import hashlib, base64
    key_enc = base64.b64encode(cfg.rest_api_key.encode()).decode()
    get_supabase().table("brokers").update({
        "api_type":          "rest",
        "rest_endpoint":     cfg.rest_endpoint,
        "rest_api_key_enc":  key_enc,
    }).eq("id", broker_id).execute()
    log.info("broker_rest_config id=%s endpoint=%s", broker_id, cfg.rest_endpoint)
    return {"ok": True, "broker_id": broker_id, "api_type": "rest"}


# ── Agreements ────────────────────────────────────────────────────────────────

@router.get("/{broker_id}/agreements")
def broker_agreements(broker_id: str) -> dict:
    _get_broker_or_404(broker_id)
    res = get_supabase().table("broker_agreements").select("*").eq("broker_id", broker_id).order("created_at", desc=True).execute()
    return {"count": len(res.data or []), "items": res.data or []}


# ── EDI log ───────────────────────────────────────────────────────────────────

@router.get("/{broker_id}/edi-log")
def broker_edi_log(broker_id: str, limit: int = 100) -> dict:
    _get_broker_or_404(broker_id)
    res = (
        get_supabase().table("broker_edi_log")
        .select("*")
        .eq("broker_id", broker_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"count": len(res.data or []), "items": res.data or []}
