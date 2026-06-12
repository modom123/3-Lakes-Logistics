"""Checkr webhook receiver — POST /api/webhooks/checkr

Checkr sends events when a background report changes status.
We listen for:
  report.completed   → adjudicate and approve or deny the driver
  report.suspended   → deny the driver immediately

Checkr webhook docs: https://docs.checkr.com/reference/webhooks
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase

log = logging.getLogger("3ll.webhooks.checkr")
router = APIRouter()

# Checkr adjudication thresholds
# 'clear' → approve | 'consider' → human review (we auto-deny for now) | 'suspended' → deny
_APPROVE_STATUSES = {"clear"}
_DENY_STATUSES    = {"consider", "suspended", "dispute"}


def _find_driver_by_candidate(sb, candidate_id: str) -> dict | None:
    try:
        r = (
            sb.table("light_vehicle_drivers")
            .select("*")
            .eq("checkr_candidate_id", candidate_id)
            .maybe_single()
            .execute()
        )
        return r.data
    except Exception:  # noqa: BLE001
        return None


def _find_driver_by_invitation(sb, invitation_id: str) -> dict | None:
    try:
        r = (
            sb.table("light_vehicle_drivers")
            .select("*")
            .eq("checkr_invitation_id", invitation_id)
            .maybe_single()
            .execute()
        )
        return r.data
    except Exception:  # noqa: BLE001
        return None


@router.post("/webhooks/checkr")
async def checkr_webhook(
    request: Request,
    x_checkr_signature: str | None = Header(None),
) -> dict[str, Any]:
    body = await request.body()
    s = get_settings()

    # Verify signature
    if s.checkr_webhook_secret:
        from ..agents.checkr_client import verify_webhook
        if not verify_webhook(body, x_checkr_signature, s.checkr_webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid Checkr webhook signature")

    try:
        event = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event.get("type") or ""
    data       = event.get("data") or {}
    report     = data.get("object") or data  # Checkr wraps payload in data.object

    report_id    = report.get("id") or ""
    candidate_id = report.get("candidate_id") or ""
    status       = report.get("status") or ""       # 'clear' | 'consider' | 'suspended'
    adjudication = report.get("adjudication") or ""  # may already be set

    log_agent("checkr_webhook", event_type, payload={
        "report_id": report_id, "candidate_id": candidate_id, "status": status
    })

    sb = get_supabase()

    # Find the driver record — try candidate_id first (most reliable)
    driver = _find_driver_by_candidate(sb, candidate_id)

    # Fallback: match by MVR report_id
    if not driver and report_id:
        try:
            r = (sb.table("light_vehicle_drivers").select("*")
                 .eq("checkr_report_id", report_id).maybe_single().execute())
            driver = r.data
        except Exception:  # noqa: BLE001
            pass

    # Fallback: match by criminal bg_report_id (non-NEMT flow)
    if not driver and report_id:
        try:
            r = (sb.table("light_vehicle_drivers").select("*")
                 .eq("checkr_bg_report_id", report_id).maybe_single().execute())
            driver = r.data
        except Exception:  # noqa: BLE001
            pass

    if not driver:
        log.warning("Checkr webhook: no driver for candidate_id=%s report_id=%s", candidate_id, report_id)
        return {"ok": True, "action": "no_matching_driver"}

    driver_id = str(driver["id"])

    # Link candidate_id to driver row if not already set
    if candidate_id and not driver.get("checkr_candidate_id"):
        try:
            sb.table("light_vehicle_drivers").update({
                "checkr_candidate_id": candidate_id,
            }).eq("id", driver_id).execute()
        except Exception:  # noqa: BLE001
            pass

    # Determine which report type fired based on which report_id column matched
    is_bg_report = (driver.get("checkr_bg_report_id") == report_id)
    is_mvr_report = (driver.get("checkr_report_id") == report_id)
    report_label = "background" if is_bg_report else "mvr_or_combined"

    # Persist the resolved status back to the correct column
    now_iso = report.get("completed_at") or ""
    _status_col  = "background_check_status" if is_bg_report else "mvr_status"
    _checked_col = "background_checked_at"   if is_bg_report else "mvr_checked_at"

    # ── Route on event type ───────────────────────────────────────────────────
    if event_type in ("report.completed", "report.updated", "report.suspended") or \
            status in _APPROVE_STATUSES | _DENY_STATUSES:
        from ..agents import maya

        effective_status = adjudication if adjudication else status

        # Always write the resolved status back to the driver row
        resolved = "clear" if effective_status in _APPROVE_STATUSES else "flagged"
        try:
            update: dict = {
                _status_col:  resolved,
                _checked_col: now_iso or None,
            }
            # combined basic report (NEMT) — update both columns
            if is_mvr_report and driver.get("checkr_package") == "basic":
                update["background_check_status"] = resolved
                update["background_checked_at"]   = now_iso or None
            sb.table("light_vehicle_drivers").update(update).eq("id", driver_id).execute()
        except Exception:  # noqa: BLE001
            pass

        if effective_status in _APPROVE_STATUSES:
            result = maya.approve_driver(driver_id, report_id)
            log.info("Driver approved via Checkr %s: driver_id=%s", report_label, driver_id)
            return {"ok": True, "action": "driver_approved", "report_type": report_label, **result}

        if effective_status in _DENY_STATUSES:
            result = maya.deny_driver(driver_id, f"checkr_{effective_status}", report_id)
            log.info("Driver denied via Checkr %s: driver_id=%s status=%s", report_label, driver_id, effective_status)
            return {"ok": True, "action": "driver_denied", "report_type": report_label, **result}

    return {"ok": True, "action": "no_op", "event": event_type, "status": status}
