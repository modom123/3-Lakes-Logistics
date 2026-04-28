"""Analytics & Intelligence step handlers for execution engine steps 181-200.

Each handler receives (carrier_id, contract_id, payload) and returns a
structured output dict written to execution_steps.output_payload.

Bands:
  181-185  Core KPIs: daily KPI refresh, fleet utilization, lane profitability,
           broker performance ranking, driver ranking
  186-190  Operational analytics: revenue forecast, fuel analysis, dead-head,
           detention report, spot vs. contract
  191-195  Intelligence: cash flow projection, carrier LTV, CSA trend,
           rate index, equipment demand forecast
  196-200  Risk & reporting: compliance risk, weekly executive report,
           Airtable sync, Sentry health, analytics cycle complete
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from ..supabase_client import get_supabase
from ..logging_service import log_agent

log = logging.getLogger("3ll.analytics.steps")


# ── helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> date:
    return date.today()


def _active_carriers() -> list[dict]:
    return (
        get_supabase()
        .table("active_carriers")
        .select("id,company_name,plan,created_at")
        .eq("status", "active")
        .execute()
        .data
    ) or []


# ═══════════════════════════════════════════════════════════════════════════
# STEPS 181-185 — Core KPI refresh
# ═══════════════════════════════════════════════════════════════════════════

def step_181_daily_kpi(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Refresh all fleet-wide KPIs: gross revenue, load count, RPM, utilization.

    Aggregates from contracts (revenue_recognized=True) and fleet_assets.
    Upserts a row into analytics_daily_kpis for today's date.
    """
    sb = get_supabase()
    kpi_date = payload.get("kpi_date", _today().isoformat())

    # Revenue & load counts from settled contracts
    q = sb.table("contracts").select(
        "rate_total,rate_per_mile,origin_city,destination_city"
    ).eq("revenue_recognized", True)
    if carrier_id:
        q = q.eq("carrier_id", str(carrier_id))
    contracts = q.execute().data or []

    total_loads = len(contracts)
    gross_revenue = sum(float(c.get("rate_total") or 0) for c in contracts)
    rates = [float(c["rate_per_mile"]) for c in contracts if c.get("rate_per_mile")]
    avg_rpm = round(sum(rates) / len(rates), 4) if rates else None

    # Fleet counts
    total_trucks_q = sb.table("fleet_assets").select("id")
    active_trucks_q = sb.table("fleet_assets").select("id").eq("status", "active") \
        if hasattr(sb.table("fleet_assets").select("id"), "eq") else None

    total_trucks_data = total_trucks_q.execute().data or []
    total_trucks = len(total_trucks_data)

    # Active = trucks currently in_transit (from truck_telemetry last 6h)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    active_data = (
        sb.table("truck_telemetry")
        .select("truck_id")
        .gte("ts", cutoff)
        .execute()
        .data
    ) or []
    active_trucks = len({r["truck_id"] for r in active_data})
    utilization = round((active_trucks / total_trucks) * 100, 2) if total_trucks else 0.0

    row = {
        "kpi_date": kpi_date,
        "gross_revenue": round(gross_revenue, 2),
        "total_loads": total_loads,
        "avg_rate_per_mile": avg_rpm,
        "fleet_utilization": utilization,
        "active_trucks": active_trucks,
        "total_trucks": total_trucks,
        "computed_at": _now(),
    }

    existing = sb.table("analytics_daily_kpis").select("id").eq("kpi_date", kpi_date).limit(1).execute().data
    if existing:
        sb.table("analytics_daily_kpis").update(row).eq("kpi_date", kpi_date).execute()
    else:
        sb.table("analytics_daily_kpis").insert(row).execute()

    log_agent("analytics", "daily_kpi", payload={"kpi_date": kpi_date, "gross": gross_revenue})
    log.info("step_181: daily_kpi date=%s gross=$%.2f loads=%d rpm=%.4f util=%.1f%%",
             kpi_date, gross_revenue, total_loads, avg_rpm or 0, utilization)
    return {**row, "action": "upserted"}


def step_182_fleet_utilization(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Calculate fleet utilization rate: active trucks / total trucks.

    Breaks down by carrier and equipment type. Updates analytics_daily_kpis
    with the precise utilization figure.
    """
    sb = get_supabase()
    today = _today().isoformat()

    # Per-carrier breakdown
    carriers = [{"id": str(carrier_id)}] if carrier_id else _active_carriers()
    breakdown: list[dict] = []
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()

    for c in carriers:
        cid = c["id"]
        total = len(
            sb.table("fleet_assets").select("id").eq("carrier_id", cid).execute().data or []
        )
        if total == 0:
            continue

        active_pings = (
            sb.table("truck_telemetry")
            .select("truck_id")
            .eq("carrier_id", cid)
            .gte("ts", cutoff)
            .execute()
            .data
        ) or []
        active = len({r["truck_id"] for r in active_pings})
        util = round((active / total) * 100, 2)
        breakdown.append({
            "carrier_id": cid,
            "total_trucks": total,
            "active_trucks": active,
            "utilization_pct": util,
        })

    fleet_total = sum(b["total_trucks"] for b in breakdown)
    fleet_active = sum(b["active_trucks"] for b in breakdown)
    fleet_util = round((fleet_active / fleet_total) * 100, 2) if fleet_total else 0.0

    # Update today's KPI row
    sb.table("analytics_daily_kpis").update({
        "fleet_utilization": fleet_util,
        "active_trucks": fleet_active,
        "total_trucks": fleet_total,
    }).eq("kpi_date", today).execute()

    log.info("step_182: fleet_utilization total=%d active=%d util=%.1f%%",
             fleet_total, fleet_active, fleet_util)
    return {
        "fleet_utilization_pct": fleet_util,
        "total_trucks": fleet_total,
        "active_trucks": fleet_active,
        "carrier_breakdown": breakdown,
        "as_of": cutoff,
    }


def step_183_lane_profitability(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Analyze profitability by lane (origin_state → destination_state pair).

    Aggregates executed contracts grouped by state pair, computes
    avg_rate_per_mile and total_revenue, upserts analytics_lane_stats.
    """
    sb = get_supabase()

    q = sb.table("contracts").select(
        "extracted_vars,rate_total,rate_per_mile,origin_city,destination_city"
    ).eq("revenue_recognized", True)
    if carrier_id:
        q = q.eq("carrier_id", str(carrier_id))
    contracts = q.execute().data or []

    # Group by origin_state → destination_state
    lanes: dict[tuple[str, str], list[float]] = {}
    lane_revenue: dict[tuple[str, str], float] = {}

    for c in contracts:
        evars = c.get("extracted_vars") or {}
        o_state = evars.get("origin_state") or ""
        d_state = evars.get("destination_state") or ""
        if not o_state or not d_state:
            continue
        key = (o_state.upper(), d_state.upper())
        rpm = float(c.get("rate_per_mile") or 0)
        rev = float(c.get("rate_total") or 0)
        lanes.setdefault(key, []).append(rpm)
        lane_revenue[key] = lane_revenue.get(key, 0) + rev

    upserted: list[dict] = []
    for (o, d), rpms in lanes.items():
        avg_rpm = round(sum(rpms) / len(rpms), 4) if rpms else None
        row = {
            "origin_state": o,
            "destination_state": d,
            "total_loads": len(rpms),
            "avg_rate_per_mile": avg_rpm,
            "total_revenue": round(lane_revenue.get((o, d), 0), 2),
            "last_updated_at": _now(),
        }
        existing = sb.table("analytics_lane_stats").select("id").eq(
            "origin_state", o).eq("destination_state", d).limit(1).execute().data
        if existing:
            sb.table("analytics_lane_stats").update(row).eq(
                "origin_state", o).eq("destination_state", d).execute()
        else:
            sb.table("analytics_lane_stats").insert(row).execute()
        upserted.append(row)

    # Top lane by revenue
    top = max(upserted, key=lambda r: r["total_revenue"]) if upserted else {}
    log.info("step_183: lane_profitability lanes=%d top=%s→%s",
             len(upserted), top.get("origin_state"), top.get("destination_state"))
    return {
        "lanes_analyzed": len(upserted),
        "top_lane": f"{top.get('origin_state')}→{top.get('destination_state')}" if top else None,
        "top_lane_revenue": top.get("total_revenue"),
        "lanes": upserted,
    }


def step_184_broker_performance(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Rank brokers by composite performance: pay speed, rate quality, dispute rate.

    Reads broker_scorecards (built by step 145) and ranks by a weighted score:
      on_time_pay_pct (40%) + avg_rate_per_mile_index (40%) + low dispute (20%).
    """
    sb = get_supabase()
    scorecards = sb.table("broker_scorecards").select("*").execute().data or []

    if not scorecards:
        return {"ranked_count": 0, "brokers": [], "note": "No broker scorecards yet"}

    # Normalize rates to 0-100 for ranking
    rates = [float(s["avg_rate_per_mile"]) for s in scorecards if s.get("avg_rate_per_mile")]
    max_rate = max(rates) if rates else 1
    min_rate = min(rates) if rates else 0
    rate_range = (max_rate - min_rate) or 1

    ranked: list[dict] = []
    for sc in scorecards:
        pay_score = float(sc.get("on_time_pay_pct") or 50)
        rate = float(sc.get("avg_rate_per_mile") or 0)
        rate_score = ((rate - min_rate) / rate_range) * 100 if rate_range else 50
        dispute_pct = float(sc.get("dispute_rate_pct") or 0)
        dispute_score = max(0.0, 100.0 - dispute_pct * 5)  # 0% disputes = 100pts

        composite = round(pay_score * 0.40 + rate_score * 0.40 + dispute_score * 0.20, 2)
        ranked.append({
            "broker_mc": sc["broker_mc"],
            "broker_name": sc.get("broker_name"),
            "total_loads": sc.get("total_loads", 0),
            "avg_rate_per_mile": rate,
            "on_time_pay_pct": pay_score,
            "dispute_rate_pct": dispute_pct,
            "volume_discount_tier": sc.get("volume_discount_tier", "none"),
            "composite_score": composite,
        })

    ranked.sort(key=lambda x: x["composite_score"], reverse=True)
    for i, b in enumerate(ranked, 1):
        b["rank"] = i

    log.info("step_184: broker_performance ranked=%d top=%s score=%.1f",
             len(ranked), ranked[0].get("broker_name") if ranked else "N/A",
             ranked[0].get("composite_score", 0) if ranked else 0)
    return {
        "ranked_count": len(ranked),
        "top_broker": ranked[0] if ranked else None,
        "brokers": ranked,
    }


def step_185_driver_ranking(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Update driver performance ranking across all carriers.

    Score = on_time_delivery_pct (50%) + loads_per_month (30%) + cdl_status (20%).
    Upserts analytics_driver_rankings with rank_position.
    """
    sb = get_supabase()
    carriers = [{"id": str(carrier_id)}] if carrier_id else _active_carriers()

    all_drivers: list[dict] = []

    for c in carriers:
        cid = c["id"]
        drivers = (
            sb.table("driver_cdl")
            .select("driver_id,driver_name,cdl_status")
            .eq("carrier_id", cid)
            .execute()
            .data
        ) or []

        for drv in drivers:
            did = drv["driver_id"]

            # Load count: delivered loads involving this driver
            loads = (
                sb.table("loads")
                .select("id,status,pickup_at,delivery_at")
                .eq("carrier_id", cid)
                .eq("driver_code", did)
                .execute()
                .data
            ) or []

            total_loads = len(loads)
            on_time = sum(
                1 for l in loads
                if l.get("status") == "delivered" and l.get("delivery_at")
            )
            on_time_pct = round((on_time / total_loads) * 100, 2) if total_loads else 0.0

            # CDL status score
            cdl_score = {"green": 100.0, "yellow": 60.0, "red": 0.0}.get(
                drv.get("cdl_status", "green"), 100.0
            )

            # Loads per month (approximate)
            loads_pm = min(total_loads / max(1, 1), 30)  # cap at 30
            loads_score = (loads_pm / 30) * 100

            perf_score = round(
                on_time_pct * 0.50 + loads_score * 0.30 + cdl_score * 0.20, 2
            )

            row = {
                "carrier_id": cid,
                "driver_id": did,
                "driver_name": drv.get("driver_name"),
                "total_loads": total_loads,
                "on_time_pct": on_time_pct,
                "performance_score": perf_score,
                "last_updated_at": _now(),
            }
            existing = (
                sb.table("analytics_driver_rankings")
                .select("id")
                .eq("carrier_id", cid)
                .eq("driver_id", did)
                .limit(1)
                .execute()
                .data
            )
            if existing:
                sb.table("analytics_driver_rankings").update(row).eq(
                    "carrier_id", cid).eq("driver_id", did).execute()
            else:
                sb.table("analytics_driver_rankings").insert(row).execute()
            all_drivers.append(row)

    # Assign global rank by performance_score
    all_drivers.sort(key=lambda x: x["performance_score"], reverse=True)
    for i, drv in enumerate(all_drivers, 1):
        sb.table("analytics_driver_rankings").update({"rank_position": i}).eq(
            "carrier_id", drv["carrier_id"]
        ).eq("driver_id", drv["driver_id"]).execute()
        drv["rank_position"] = i

    top = all_drivers[0] if all_drivers else {}
    log.info("step_185: driver_ranking drivers=%d top=%s score=%.1f",
             len(all_drivers), top.get("driver_name"), top.get("performance_score", 0))
    return {
        "drivers_ranked": len(all_drivers),
        "top_driver": top,
        "rankings": all_drivers[:20],  # top 20 in output payload
    }
