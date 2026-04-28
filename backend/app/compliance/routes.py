"""Compliance & Safety REST endpoints (Shield domain — steps 151-180).

Endpoints:
  POST /api/compliance/sweep              — trigger full daily sweep (step 151)
  POST /api/compliance/csa-refresh        — force CSA SAFER refresh (step 152)
  POST /api/compliance/safety-light       — recompute all safety lights (step 163)
  POST /api/compliance/compliance-score   — recompute composite scores (step 179)
  POST /api/compliance/dot-audit-prep     — DOT audit readiness report (step 172)

  GET  /api/compliance/events             — list shield_events
  GET  /api/compliance/scores             — list carrier compliance scores
  GET  /api/compliance/carriers/{id}/score — single carrier score

  GET  /api/compliance/insurance-alerts   — carriers with expiring insurance
  GET  /api/compliance/cdl-alerts         — drivers with expiring CDLs
  GET  /api/compliance/drug-tests         — drug test schedule

  GET  /api/compliance/inspections        — vehicle inspection records
  POST /api/compliance/inspections        — create/update inspection record

  GET  /api/compliance/ifta               — IFTA filing status
  GET  /api/compliance/ucr                — UCR registration status

  GET  /api/compliance/mvr                — MVR check records
  GET  /api/compliance/leases             — lease agreement records
"""
from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..api.deps import require_bearer
from ..supabase_client import get_supabase
from ..logging_service import get_logger
from .steps import (
    step_151_daily_sweep,
    step_152_csa_refresh,
    step_163_safety_light_update,
    step_172_dot_audit_prep,
    step_179_compliance_score,
)

router = APIRouter()
log = get_logger("3ll.compliance.routes")


# ── Pydantic models ───────────────────────────────────────────────────────────

class InspectionUpsert(BaseModel):
    carrier_id: UUID
    truck_id: str
    vin: str | None = None
    last_inspection: date | None = None
    due_date: date
    result: str = "not_performed"  # pass | fail | overdue | not_performed
    defects: list[str] | None = None
    sticker_expiry: date | None = None
    notes: str | None = None


class ShieldEventResolve(BaseModel):
    resolution_note: str | None = None


# ── Trigger endpoints ─────────────────────────────────────────────────────────

@router.post("/sweep", status_code=202)
def trigger_daily_sweep(
    carrier_id: str | None = None,
    _: str = Depends(require_bearer),
):
    """Trigger a full daily compliance sweep (step 151)."""
    cid = UUID(carrier_id) if carrier_id else None
    result = step_151_daily_sweep(cid, None, {})
    log.info("route /sweep triggered carriers=%d", result.get("carriers_checked", 0))
    return result


@router.post("/csa-refresh", status_code=202)
def trigger_csa_refresh(
    carrier_id: str | None = None,
    _: str = Depends(require_bearer),
):
    """Force FMCSA SAFER CSA refresh for all carriers or one (step 152)."""
    cid = UUID(carrier_id) if carrier_id else None
    return step_152_csa_refresh(cid, None, {})


@router.post("/safety-light", status_code=202)
def trigger_safety_light_update(
    carrier_id: str | None = None,
    _: str = Depends(require_bearer),
):
    """Recompute safety light for all carriers or one (step 163)."""
    cid = UUID(carrier_id) if carrier_id else None
    return step_163_safety_light_update(cid, None, {})


@router.post("/compliance-score", status_code=202)
def trigger_compliance_score(
    carrier_id: str | None = None,
    _: str = Depends(require_bearer),
):
    """Recompute composite compliance score for all carriers or one (step 179)."""
    cid = UUID(carrier_id) if carrier_id else None
    return step_179_compliance_score(cid, None, {})


@router.post("/dot-audit-prep/{carrier_id}", status_code=200)
def dot_audit_prep(carrier_id: UUID, _: str = Depends(require_bearer)):
    """Generate a DOT audit readiness report for a single carrier (step 172)."""
    result = step_172_dot_audit_prep(carrier_id, None, {})
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


# ── Shield events ─────────────────────────────────────────────────────────────

@router.get("/events")
def list_shield_events(
    carrier_id: str | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    unresolved_only: bool = False,
    limit: int = 200,
    _: str = Depends(require_bearer),
):
    sb = get_supabase()
    q = sb.table("shield_events").select("*")
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    if event_type:
        q = q.eq("event_type", event_type)
    if severity:
        q = q.eq("severity", severity)
    if unresolved_only:
        q = q.is_("resolved_at", "null")
    return q.order("created_at", desc=True).limit(min(limit, 1000)).execute().data


@router.patch("/events/{event_id}/resolve", status_code=200)
def resolve_shield_event(
    event_id: str,
    body: ShieldEventResolve,
    _: str = Depends(require_bearer),
):
    from datetime import datetime, timezone
    sb = get_supabase()
    event = sb.table("shield_events").select("id").eq("id", event_id).limit(1).execute().data
    if not event:
        raise HTTPException(404, "Shield event not found")
    sb.table("shield_events").update({
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "payload": {"resolution_note": body.resolution_note},
    }).eq("id", event_id).execute()
    return {"resolved": True, "event_id": event_id}


# ── Compliance scores ─────────────────────────────────────────────────────────

@router.get("/scores")
def list_compliance_scores(
    safety_light: str | None = None,
    min_score: float | None = None,
    limit: int = 200,
    _: str = Depends(require_bearer),
):
    sb = get_supabase()
    q = sb.table("carrier_compliance_scores").select("*")
    if safety_light:
        q = q.eq("safety_light", safety_light)
    if min_score is not None:
        q = q.gte("composite_score", min_score)
    return q.order("composite_score").limit(min(limit, 1000)).execute().data


@router.get("/carriers/{carrier_id}/score")
def get_carrier_score(carrier_id: UUID, _: str = Depends(require_bearer)):
    sb = get_supabase()
    res = sb.table("carrier_compliance_scores").select("*").eq(
        "carrier_id", str(carrier_id)
    ).single().execute()
    if not res.data:
        raise HTTPException(404, "No compliance score found for this carrier")
    return res.data


# ── Insurance alerts ──────────────────────────────────────────────────────────

@router.get("/insurance-alerts")
def list_insurance_alerts(
    days: int = 30,
    _: str = Depends(require_bearer),
):
    """Return carriers with insurance expiring within {days} days."""
    sb = get_supabase()
    today = date.today()
    threshold = (today + timedelta(days=days)).isoformat()
    return (
        sb.table("insurance_compliance")
        .select("carrier_id,insurance_carrier,policy_number,policy_expiry,safety_light")
        .lte("policy_expiry", threshold)
        .gte("policy_expiry", today.isoformat())
        .order("policy_expiry")
        .execute()
        .data
    )


# ── CDL alerts ────────────────────────────────────────────────────────────────

@router.get("/cdl-alerts")
def list_cdl_alerts(
    carrier_id: str | None = None,
    status: str | None = None,
    days: int = 30,
    _: str = Depends(require_bearer),
):
    """Return drivers with CDLs expiring within {days} days."""
    sb = get_supabase()
    today = date.today()
    threshold = (today + timedelta(days=days)).isoformat()
    q = (
        sb.table("driver_cdl")
        .select("carrier_id,driver_id,driver_name,cdl_expiry,cdl_status,endorsements")
        .lte("cdl_expiry", threshold)
    )
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    if status:
        q = q.eq("cdl_status", status)
    return q.order("cdl_expiry").limit(500).execute().data


# ── Drug tests ────────────────────────────────────────────────────────────────

@router.get("/drug-tests")
def list_drug_tests(
    carrier_id: str | None = None,
    test_type: str | None = None,
    completed: bool | None = None,
    limit: int = 200,
    _: str = Depends(require_bearer),
):
    sb = get_supabase()
    q = sb.table("drug_test_schedule").select("*")
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    if test_type:
        q = q.eq("test_type", test_type)
    if completed is True:
        q = q.not_.is_("completed_at", "null")
    elif completed is False:
        q = q.is_("completed_at", "null")
    return q.order("scheduled_at").limit(min(limit, 1000)).execute().data


# ── Vehicle inspections ───────────────────────────────────────────────────────

@router.get("/inspections")
def list_inspections(
    carrier_id: str | None = None,
    result: str | None = None,
    overdue_only: bool = False,
    _: str = Depends(require_bearer),
):
    sb = get_supabase()
    q = sb.table("vehicle_inspections").select("*")
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    if result:
        q = q.eq("result", result)
    if overdue_only:
        q = q.lt("due_date", date.today().isoformat()).neq("result", "pass")
    return q.order("due_date").limit(1000).execute().data


@router.post("/inspections", status_code=201)
def upsert_inspection(body: InspectionUpsert, _: str = Depends(require_bearer)):
    sb = get_supabase()
    row = body.model_dump()
    row["carrier_id"] = str(row["carrier_id"])
    row["due_date"] = str(row["due_date"]) if row.get("due_date") else None
    row["last_inspection"] = str(row["last_inspection"]) if row.get("last_inspection") else None
    row["sticker_expiry"] = str(row["sticker_expiry"]) if row.get("sticker_expiry") else None

    existing = (
        sb.table("vehicle_inspections").select("id")
        .eq("carrier_id", row["carrier_id"]).eq("truck_id", row["truck_id"])
        .limit(1).execute().data
    )
    if existing:
        sb.table("vehicle_inspections").update(row).eq(
            "carrier_id", row["carrier_id"]
        ).eq("truck_id", row["truck_id"]).execute()
        return {"action": "updated", **row}
    res = sb.table("vehicle_inspections").insert(row).execute()
    return {"action": "created", **res.data[0]}


# ── IFTA filings ──────────────────────────────────────────────────────────────

@router.get("/ifta")
def list_ifta(
    carrier_id: str | None = None,
    status: str | None = None,
    quarter: str | None = None,
    _: str = Depends(require_bearer),
):
    sb = get_supabase()
    q = sb.table("ifta_filings").select("*")
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    if status:
        q = q.eq("status", status)
    if quarter:
        q = q.eq("quarter", quarter)
    return q.order("due_date").limit(1000).execute().data


# ── UCR registrations ─────────────────────────────────────────────────────────

@router.get("/ucr")
def list_ucr(
    carrier_id: str | None = None,
    status: str | None = None,
    reg_year: int | None = None,
    _: str = Depends(require_bearer),
):
    sb = get_supabase()
    q = sb.table("ucr_registrations").select("*")
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    if status:
        q = q.eq("status", status)
    if reg_year:
        q = q.eq("reg_year", reg_year)
    return q.order("reg_year", desc=True).limit(1000).execute().data


# ── MVR checks ────────────────────────────────────────────────────────────────

@router.get("/mvr")
def list_mvr(
    carrier_id: str | None = None,
    overdue_only: bool = False,
    _: str = Depends(require_bearer),
):
    sb = get_supabase()
    q = sb.table("mvr_checks").select("*")
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    if overdue_only:
        q = q.lt("next_due", date.today().isoformat())
    return q.order("next_due").limit(1000).execute().data


# ── Lease agreements ──────────────────────────────────────────────────────────

@router.get("/leases")
def list_leases(
    carrier_id: str | None = None,
    status: str | None = None,
    _: str = Depends(require_bearer),
):
    sb = get_supabase()
    q = sb.table("lease_agreements").select("*")
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    if status:
        q = q.eq("status", status)
    return q.order("end_date").limit(1000).execute().data
