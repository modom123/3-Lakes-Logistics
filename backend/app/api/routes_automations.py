"""Automation health monitoring — tracks all background jobs and integration status."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from ..logging_service import get_logger
from ..supabase_client import get_supabase
from .deps import require_bearer

log = get_logger("automations.routes")
router = APIRouter(dependencies=[require_bearer()])


class AutomationStatusUpdate(BaseModel):
    status: str  # ok | warning | failed
    error_message: Optional[str] = None
    duration_ms: Optional[int] = None
    items_processed: Optional[int] = None
    affected_carriers: Optional[int] = None


@router.get("")
async def list_automations(
    status_filter: Optional[str] = Query(None, alias="status"),
) -> dict:
    """List all automations and their current health status.

    Status: ok, warning, failed
    """
    try:
        sb = get_supabase()

        query = sb.table("automation_health").select("*")

        if status_filter:
            query = query.eq("status", status_filter)

        result = query.order("service_name").execute()

        # Format response
        automations = []
        for auto in result.data or []:
            last_run = auto.get("last_check_at")
            if last_run:
                # Format last_run as human-readable
                last_check = datetime.fromisoformat(last_run)
                now = datetime.now(timezone.utc)
                delta = (now - last_check.replace(tzinfo=timezone.utc)).total_seconds()

                if delta < 60:
                    last_run_str = f"{int(delta)}s ago"
                elif delta < 3600:
                    last_run_str = f"{int(delta/60)}m ago"
                elif delta < 86400:
                    last_run_str = f"{int(delta/3600)}h ago"
                else:
                    last_run_str = f"{int(delta/86400)}d ago"
            else:
                last_run_str = "never"

            automations.append({
                "id": auto.get("id"),
                "name": auto.get("display_name"),
                "service_name": auto.get("service_name"),
                "status": auto.get("status"),
                "last_run": last_run_str,
                "last_check_at": auto.get("last_check_at"),
                "last_success_at": auto.get("last_success_at"),
                "error_message": auto.get("error_message"),
                "error_count": auto.get("error_count", 0),
                "consecutive_failures": auto.get("consecutive_failures", 0),
                "affected_carriers": auto.get("affected_carriers"),
                "run_interval_seconds": auto.get("run_interval_seconds"),
                "last_run_duration_ms": auto.get("last_run_duration_ms"),
            })

        return {
            "ok": True,
            "count": len(automations),
            "data": automations,
        }
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to list automations: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.get("/{service_name}")
async def get_automation(service_name: str) -> dict:
    """Get automation status and recent run history."""
    try:
        sb = get_supabase()

        # Get automation
        auto_res = (
            sb.table("automation_health")
            .select("*")
            .eq("service_name", service_name)
            .maybe_single()
            .execute()
        )

        if not auto_res.data:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "automation not found")

        automation = auto_res.data

        # Get recent run log (last 10 runs)
        log_res = (
            sb.table("automation_run_log")
            .select("*")
            .eq("service_name", service_name)
            .order("run_at", desc=True)
            .limit(10)
            .execute()
        )

        return {
            "ok": True,
            "automation": automation,
            "recent_runs": log_res.data or [],
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to get automation: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.post("/{service_name}/report")
async def report_automation_run(
    service_name: str,
    payload: AutomationStatusUpdate,
) -> dict:
    """Report automation run results.

    Called by background jobs to update their health status.
    """
    try:
        sb = get_supabase()

        now_iso = datetime.now(timezone.utc).isoformat()

        # Update automation health
        update_data = {
            "status": payload.status,
            "last_check_at": now_iso,
            "error_message": payload.error_message,
            "last_run_duration_ms": payload.duration_ms,
            "affected_carriers": payload.affected_carriers,
        }

        # Track consecutive failures
        if payload.status == "failed":
            # Increment error count
            auto = (
                sb.table("automation_health")
                .select("error_count,consecutive_failures")
                .eq("service_name", service_name)
                .maybe_single()
                .execute()
            )
            if auto.data:
                update_data["error_count"] = (auto.data.get("error_count", 0) or 0) + 1
                update_data["consecutive_failures"] = (auto.data.get("consecutive_failures", 0) or 0) + 1
        else:
            # Success — reset consecutive failures
            update_data["last_success_at"] = now_iso
            update_data["consecutive_failures"] = 0
            update_data["error_count"] = 0
            update_data["error_message"] = None

        sb.table("automation_health").update(update_data).eq(
            "service_name", service_name
        ).execute()

        # Log run
        log_data = {
            "service_name": service_name,
            "status": payload.status,
            "duration_ms": payload.duration_ms,
            "items_processed": payload.items_processed,
            "error_message": payload.error_message,
            "run_at": now_iso,
        }
        sb.table("automation_run_log").insert(log_data).execute()

        log.info(
            f"Automation {service_name} reported: {payload.status} "
            f"({payload.duration_ms}ms, {payload.items_processed} items)"
        )

        return {
            "ok": True,
            "message": f"automation {service_name} updated",
        }
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to report automation: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.get("/stats/summary")
async def automation_summary() -> dict:
    """Get summary of all automation statuses."""
    try:
        sb = get_supabase()

        result = sb.table("automation_health").select("status,service_name").execute()
        automations = result.data or []

        ok_count = sum(1 for a in automations if a.get("status") == "ok")
        warning_count = sum(1 for a in automations if a.get("status") == "warning")
        failed_count = sum(1 for a in automations if a.get("status") == "failed")

        # Get failures
        failures = [a for a in automations if a.get("status") == "failed"]

        return {
            "ok": True,
            "data": {
                "total": len(automations),
                "ok": ok_count,
                "warning": warning_count,
                "failed": failed_count,
                "failures": [{"service": f["service_name"]} for f in failures],
            },
        }
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to get automation summary: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))
