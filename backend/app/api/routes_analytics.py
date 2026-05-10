"""Analytics & reporting — performance metrics, utilization, trends."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from ..logging_service import get_logger
from ..supabase_client import get_supabase
from .deps import require_bearer

log = get_logger("analytics.routes")
router = APIRouter(dependencies=[require_bearer()])


@router.get("/fleet/utilization")
async def fleet_utilization(
    days: int = Query(30, ge=7, le=365),
) -> dict:
    """Get fleet utilization rate over time (% trucks on active loads)."""
    try:
        sb = get_supabase()

        # Get daily snapshots of utilization
        # For now, calculate from current state (real implementation would use historical snapshots)

        all_trucks = sb.table("fleet_assets").select("*").execute()
        trucks = all_trucks.data or []

        total = len(trucks)
        on_load = sum(1 for t in trucks if t.get("status") == "on_load")

        utilization = (on_load / total * 100) if total > 0 else 0

        return {
            "ok": True,
            "data": {
                "total_trucks": total,
                "trucks_on_load": on_load,
                "utilization_percent": round(utilization, 1),
                "available_trucks": total - on_load,
            },
        }
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to get fleet utilization: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.get("/carriers/performance")
async def carrier_performance(
    limit: int = Query(10, ge=1, le=100),
) -> dict:
    """Get top carriers by revenue, utilization, and rating."""
    try:
        sb = get_supabase()

        # Get all carriers
        carriers_res = sb.table("active_carriers").select("*").execute()
        carriers = carriers_res.data or []

        # Get loads per carrier
        loads_res = sb.table("loads").select("*").execute()
        all_loads = loads_res.data or []

        # Calculate metrics per carrier
        carrier_metrics = []
        for carrier in carriers:
            carrier_id = carrier.get("id")
            carrier_loads = [l for l in all_loads if l.get("carrier_id") == carrier_id]

            total_revenue = sum(float(l.get("rate_total", 0)) for l in carrier_loads)
            load_count = len(carrier_loads)
            avg_rate = total_revenue / load_count if load_count > 0 else 0
            avg_rpm = avg_rate / (sum(float(l.get("miles", 1)) for l in carrier_loads) / load_count) if load_count > 0 else 0

            # Get fleet for this carrier
            fleet_res = sb.table("fleet_assets").select("*").eq("carrier_id", carrier_id).execute()
            fleet = fleet_res.data or []
            on_load = sum(1 for t in fleet if t.get("status") == "on_load")
            utilization = (on_load / len(fleet) * 100) if len(fleet) > 0 else 0

            carrier_metrics.append({
                "carrier_id": carrier_id,
                "company_name": carrier.get("company_name"),
                "loads_mtd": load_count,
                "revenue_mtd": round(total_revenue, 2),
                "avg_rpm": round(avg_rpm, 2),
                "utilization_percent": round(utilization, 1),
                "trucks": len(fleet),
                "status": carrier.get("status"),
            })

        # Sort by revenue
        carrier_metrics.sort(key=lambda x: x["revenue_mtd"], reverse=True)

        return {
            "ok": True,
            "count": len(carrier_metrics[:limit]),
            "data": carrier_metrics[:limit],
        }
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to get carrier performance: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.get("/loads/summary")
async def loads_summary(
    days: int = Query(30, ge=1, le=365),
) -> dict:
    """Get load statistics (count, revenue, by status)."""
    try:
        sb = get_supabase()

        # Get loads from last N days
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_iso = cutoff.isoformat()

        loads_res = (
            sb.table("loads")
            .select("*")
            .gte("created_at", cutoff_iso)
            .execute()
        )
        loads = loads_res.data or []

        # Group by status
        by_status = {}
        total_revenue = 0

        for load in loads:
            status = load.get("status", "unknown")
            by_status[status] = by_status.get(status, 0) + 1
            total_revenue += float(load.get("rate_total", 0))

        return {
            "ok": True,
            "data": {
                "period_days": days,
                "total_loads": len(loads),
                "total_revenue": round(total_revenue, 2),
                "avg_per_load": round(total_revenue / len(loads), 2) if loads else 0,
                "by_status": by_status,
            },
        }
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to get loads summary: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.get("/compliance/summary")
async def compliance_summary() -> dict:
    """Get overall compliance status across all carriers."""
    try:
        sb = get_supabase()

        # Check compliance table
        carriers_res = sb.table("active_carriers").select("*").execute()
        carriers = carriers_res.data or []

        compliant = 0
        warnings = 0
        critical = 0

        for carrier in carriers:
            # Simplified: active carriers = compliant, suspended/churned = not
            if carrier.get("status") == "active":
                compliant += 1
            elif carrier.get("status") == "suspended":
                warnings += 1
            else:
                critical += 1

        return {
            "ok": True,
            "data": {
                "total_carriers": len(carriers),
                "compliant": compliant,
                "warnings": warnings,
                "critical": critical,
                "compliance_rate_percent": round(
                    (compliant / len(carriers) * 100) if carriers else 0, 1
                ),
            },
        }
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to get compliance summary: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.get("/revenue/trend")
async def revenue_trend(
    months: int = Query(12, ge=1, le=24),
) -> dict:
    """Get monthly revenue trend."""
    try:
        sb = get_supabase()

        # Get loads from last N months
        loads_res = sb.table("loads").select("*").execute()
        all_loads = loads_res.data or []

        # Group by month
        monthly = {}
        for load in all_loads:
            if load.get("created_at"):
                created = datetime.fromisoformat(load["created_at"])
                month_key = created.strftime("%Y-%m")
                if month_key not in monthly:
                    monthly[month_key] = {"loads": 0, "revenue": 0}
                monthly[month_key]["loads"] += 1
                monthly[month_key]["revenue"] += float(load.get("rate_total", 0))

        # Sort by month
        sorted_months = sorted(monthly.items())[-months:]

        trend = [
            {
                "month": month,
                "loads": data["loads"],
                "revenue": round(data["revenue"], 2),
            }
            for month, data in sorted_months
        ]

        return {
            "ok": True,
            "count": len(trend),
            "data": trend,
        }
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to get revenue trend: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.get("/equipment/mix")
async def equipment_mix() -> dict:
    """Get fleet composition by equipment type."""
    try:
        sb = get_supabase()

        fleet_res = sb.table("fleet_assets").select("*").execute()
        trucks = fleet_res.data or []

        # Count by trailer type
        by_type = {}
        for truck in trucks:
            truck_type = truck.get("trailer_type", "unknown")
            by_type[truck_type] = by_type.get(truck_type, 0) + 1

        # Sort by count descending
        sorted_types = sorted(by_type.items(), key=lambda x: x[1], reverse=True)

        equipment = [
            {
                "type": truck_type,
                "count": count,
                "percentage": round((count / len(trucks) * 100) if trucks else 0, 1),
            }
            for truck_type, count in sorted_types
        ]

        return {
            "ok": True,
            "total_trucks": len(trucks),
            "data": equipment,
        }
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to get equipment mix: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))
