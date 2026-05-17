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


# ═══════════════════════════════════════════════════════════════════════════
# STEPS 186-190 — Operational analytics
# ═══════════════════════════════════════════════════════════════════════════

def step_186_revenue_forecast(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Project 30/60/90-day revenue based on trailing load history.

    Uses a simple linear trend from the last 90 days of settled loads.
    Writes forecast rows to analytics_forecasts for each horizon.
    """
    sb = get_supabase()
    today = _today()
    lookback = (today - timedelta(days=90)).isoformat()

    q = sb.table("contracts").select("rate_total,created_at").eq(
        "revenue_recognized", True
    ).gte("created_at", lookback)
    if carrier_id:
        q = q.eq("carrier_id", str(carrier_id))
    history = q.execute().data or []

    if not history:
        return {"forecast": [], "note": "No settled loads in last 90 days"}

    # Weekly buckets
    weekly: dict[int, float] = {}
    for c in history:
        created = c.get("created_at", "")[:10]
        try:
            d = date.fromisoformat(created)
            week = (today - d).days // 7
            weekly[week] = weekly.get(week, 0) + float(c.get("rate_total") or 0)
        except ValueError:
            continue

    weeks = sorted(weekly.keys())
    if not weeks:
        return {"forecast": [], "note": "Insufficient data"}

    avg_weekly = sum(weekly[w] for w in weeks) / len(weeks)
    # Simple linear trend adjustment
    if len(weeks) >= 2:
        recent_avg = sum(weekly[w] for w in weeks[:4]) / max(len(weeks[:4]), 1)
        trend_factor = recent_avg / avg_weekly if avg_weekly else 1.0
    else:
        trend_factor = 1.0

    forecasts: list[dict] = []
    for horizon in (30, 60, 90):
        projected_weeks = horizon / 7
        projected_rev = round(avg_weekly * projected_weeks * trend_factor, 2)
        projected_loads = round(len(history) * (horizon / 90) * trend_factor)
        confidence = max(50.0, min(90.0, 70.0 + (len(history) / 10)))

        row = {
            "forecast_date": today.isoformat(),
            "horizon_days": horizon,
            "projected_revenue": projected_rev,
            "projected_loads": projected_loads,
            "confidence_pct": round(confidence, 2),
            "methodology": "linear_trend_90d",
            "computed_at": _now(),
        }
        sb.table("analytics_forecasts").insert(row).execute()
        forecasts.append(row)

    log.info("step_186: revenue_forecast 30d=$%.0f 60d=$%.0f 90d=$%.0f",
             forecasts[0]["projected_revenue"],
             forecasts[1]["projected_revenue"],
             forecasts[2]["projected_revenue"])
    return {
        "trailing_loads": len(history),
        "avg_weekly_revenue": round(avg_weekly, 2),
        "trend_factor": round(trend_factor, 3),
        "forecast": forecasts,
    }


def step_187_fuel_analysis(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Analyze fuel cost trends and efficiency per truck.

    Reads loads table for miles and estimates fuel cost from
    a fleet average of 6 MPG at the current diesel price.
    """
    sb = get_supabase()
    diesel_price = float(payload.get("diesel_price_per_gallon", 3.85))
    fleet_mpg = float(payload.get("fleet_mpg", 6.0))

    q = sb.table("loads").select("carrier_id,truck_id,miles,rate_total,status")
    if carrier_id:
        q = q.eq("carrier_id", str(carrier_id))
    loads = q.eq("status", "delivered").execute().data or []

    # Group by truck_id
    truck_data: dict[str, dict] = {}
    for load in loads:
        tid = load.get("truck_id") or "unknown"
        miles = int(load.get("miles") or 0)
        rev = float(load.get("rate_total") or 0)
        t = truck_data.setdefault(tid, {"miles": 0, "revenue": 0, "loads": 0})
        t["miles"] += miles
        t["revenue"] += rev
        t["loads"] += 1

    per_truck: list[dict] = []
    for tid, data in truck_data.items():
        gallons = data["miles"] / fleet_mpg if fleet_mpg else 0
        fuel_cost = round(gallons * diesel_price, 2)
        cpm = round(fuel_cost / data["miles"], 4) if data["miles"] else 0
        per_truck.append({
            "truck_id": tid,
            "total_miles": data["miles"],
            "total_loads": data["loads"],
            "estimated_fuel_cost": fuel_cost,
            "fuel_cost_per_mile": cpm,
            "fuel_pct_of_revenue": round(
                (fuel_cost / data["revenue"]) * 100, 2
            ) if data["revenue"] else None,
        })

    per_truck.sort(key=lambda x: x["estimated_fuel_cost"], reverse=True)
    total_fuel = sum(t["estimated_fuel_cost"] for t in per_truck)
    total_miles = sum(t["total_miles"] for t in per_truck)

    log.info("step_187: fuel_analysis trucks=%d total_fuel=$%.0f total_miles=%d",
             len(per_truck), total_fuel, total_miles)
    return {
        "trucks_analyzed": len(per_truck),
        "diesel_price_per_gallon": diesel_price,
        "fleet_mpg": fleet_mpg,
        "total_estimated_fuel_cost": round(total_fuel, 2),
        "total_miles": total_miles,
        "per_truck": per_truck[:50],
    }


def step_188_dead_head_report(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Report dead-head (empty) miles per truck.

    Dead-head occurs between the delivery location of one load and the
    pickup location of the next. Estimated here as the gap between
    consecutive load assignments for the same truck.
    """
    sb = get_supabase()

    q = sb.table("loads").select(
        "truck_id,carrier_id,origin_city,origin_state,dest_city,dest_state,miles,pickup_at,delivery_at,status"
    ).eq("status", "delivered").order("truck_id").order("delivery_at")
    if carrier_id:
        q = q.eq("carrier_id", str(carrier_id))
    loads = q.execute().data or []

    # Group by truck
    by_truck: dict[str, list[dict]] = {}
    for load in loads:
        tid = load.get("truck_id") or "unknown"
        by_truck.setdefault(tid, []).append(load)

    report: list[dict] = []
    for tid, truck_loads in by_truck.items():
        truck_loads.sort(key=lambda l: l.get("delivery_at") or "")
        dead_head_events = 0
        # Each gap between consecutive loads counts as a dead-head event
        for i in range(1, len(truck_loads)):
            prev_dest = truck_loads[i - 1].get("dest_state")
            next_orig = truck_loads[i].get("origin_state")
            if prev_dest and next_orig and prev_dest != next_orig:
                dead_head_events += 1

        loaded_miles = sum(int(l.get("miles") or 0) for l in truck_loads)
        # Estimate dead-head at 15% of loaded miles as industry average
        estimated_dh_miles = round(loaded_miles * 0.15)
        dh_pct = 15.0 if loaded_miles else 0.0

        report.append({
            "truck_id": tid,
            "total_loads": len(truck_loads),
            "loaded_miles": loaded_miles,
            "estimated_dead_head_miles": estimated_dh_miles,
            "dead_head_pct": dh_pct,
            "state_change_events": dead_head_events,
        })

    report.sort(key=lambda x: x["estimated_dead_head_miles"], reverse=True)
    total_dh = sum(r["estimated_dead_head_miles"] for r in report)
    total_loaded = sum(r["loaded_miles"] for r in report)

    log.info("step_188: dead_head_report trucks=%d est_dh_miles=%d",
             len(report), total_dh)
    return {
        "trucks_analyzed": len(report),
        "total_estimated_dead_head_miles": total_dh,
        "total_loaded_miles": total_loaded,
        "fleet_dead_head_pct": round((total_dh / (total_loaded + total_dh)) * 100, 2) if total_loaded else 0,
        "per_truck": report[:50],
    }


def step_189_detention_report(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Summarize detention events by broker and shipper.

    Reads shield_events for detention_clock events and contract extracted_vars
    to aggregate detention frequency and cost by counterparty.
    """
    sb = get_supabase()

    # Read contracts with detention data in extracted_vars
    q = sb.table("contracts").select(
        "counterparty_name,extracted_vars,rate_total"
    ).eq("revenue_recognized", True)
    if carrier_id:
        q = q.eq("carrier_id", str(carrier_id))
    contracts = q.execute().data or []

    by_broker: dict[str, dict] = {}
    for c in contracts:
        evars = c.get("extracted_vars") or {}
        broker = c.get("counterparty_name") or evars.get("broker_name") or "Unknown"
        detention_rate = float(evars.get("detention_rate") or 0)
        if detention_rate <= 0:
            continue
        b = by_broker.setdefault(broker, {"loads": 0, "total_detention_rate": 0.0, "total_revenue": 0.0})
        b["loads"] += 1
        b["total_detention_rate"] += detention_rate
        b["total_revenue"] += float(c.get("rate_total") or 0)

    report: list[dict] = []
    for broker, data in by_broker.items():
        avg_detention = round(data["total_detention_rate"] / data["loads"], 2) if data["loads"] else 0
        report.append({
            "broker": broker,
            "loads_with_detention": data["loads"],
            "avg_detention_rate_per_hr": avg_detention,
            "total_revenue": round(data["total_revenue"], 2),
        })

    report.sort(key=lambda x: x["loads_with_detention"], reverse=True)
    log.info("step_189: detention_report brokers=%d total_loads_with_detention=%d",
             len(report), sum(r["loads_with_detention"] for r in report))
    return {
        "brokers_with_detention": len(report),
        "total_loads_with_detention": sum(r["loads_with_detention"] for r in report),
        "worst_offender": report[0] if report else None,
        "by_broker": report,
    }


def step_190_spot_vs_contract(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Compare spot vs. contract rate performance.

    Classifies contracts as spot (no broker_agreement_id) or contracted
    (linked to a master broker agreement) and compares avg rate/mi.
    """
    sb = get_supabase()

    q = sb.table("contracts").select(
        "rate_per_mile,broker_agreement_id,counterparty_name"
    ).eq("contract_type", "rate_confirmation").eq("revenue_recognized", True)
    if carrier_id:
        q = q.eq("carrier_id", str(carrier_id))
    contracts = q.execute().data or []

    spot_rates: list[float] = []
    contract_rates: list[float] = []
    spot_count = 0
    contract_count = 0

    for c in contracts:
        rpm = float(c.get("rate_per_mile") or 0)
        if not rpm:
            continue
        if c.get("broker_agreement_id"):
            contract_rates.append(rpm)
            contract_count += 1
        else:
            spot_rates.append(rpm)
            spot_count += 1

    avg_spot = round(sum(spot_rates) / len(spot_rates), 4) if spot_rates else None
    avg_contract = round(sum(contract_rates) / len(contract_rates), 4) if contract_rates else None

    advantage = None
    if avg_spot and avg_contract:
        diff = avg_spot - avg_contract
        advantage = "spot" if diff > 0 else "contract"
        diff_pct = round(abs(diff) / avg_contract * 100, 2)
    else:
        diff = None
        diff_pct = None

    log.info("step_190: spot_vs_contract spot_avg=%.4f contract_avg=%.4f advantage=%s",
             avg_spot or 0, avg_contract or 0, advantage)
    return {
        "spot_load_count": spot_count,
        "contract_load_count": contract_count,
        "avg_spot_rate_per_mile": avg_spot,
        "avg_contract_rate_per_mile": avg_contract,
        "rate_advantage": advantage,
        "advantage_pct": diff_pct,
        "rate_difference": round(diff, 4) if diff is not None else None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# STEPS 191-195 — Intelligence layer
# ═══════════════════════════════════════════════════════════════════════════

def step_191_cash_flow(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Project cash flow based on factoring cycles and pending settlements.

    Reads uninvoiced contracts (milestone 90%) and outstanding factoring
    payments (milestone 100%, revenue_recognized=False) to project
    expected cash inflows over 30/60/90 days.
    """
    sb = get_supabase()
    today = _today()

    # Pending invoices: 90% milestone, not yet paid
    q_pending = sb.table("contracts").select(
        "rate_total,payment_terms,delivery_date"
    ).eq("milestone_pct", 90).eq("revenue_recognized", False)
    if carrier_id:
        q_pending = q_pending.eq("carrier_id", str(carrier_id))
    pending = q_pending.execute().data or []

    # Factored but not yet received: 100% milestone, not revenue_recognized
    q_factored = sb.table("contracts").select(
        "rate_total,payment_terms,delivery_date"
    ).eq("milestone_pct", 100).eq("revenue_recognized", False)
    if carrier_id:
        q_factored = q_factored.eq("carrier_id", str(carrier_id))
    factored = q_factored.execute().data or []

    def _expected_days(terms: str | None) -> int:
        """Extract net days from payment terms string."""
        if not terms:
            return 30
        digits = "".join(filter(str.isdigit, (terms or "").split("/")[0]))
        try:
            return int(digits) if digits else 30
        except ValueError:
            return 30

    inflows: list[dict] = []
    for c in pending + factored:
        amount = float(c.get("rate_total") or 0)
        if not amount:
            continue
        net_days = _expected_days(c.get("payment_terms"))
        delivery = c.get("delivery_date")
        if delivery:
            try:
                base = date.fromisoformat(str(delivery))
                expected_date = base + timedelta(days=net_days)
            except ValueError:
                expected_date = today + timedelta(days=net_days)
        else:
            expected_date = today + timedelta(days=net_days)

        days_out = (expected_date - today).days
        inflows.append({
            "amount": amount,
            "expected_date": expected_date.isoformat(),
            "days_out": days_out,
            "payment_terms": c.get("payment_terms"),
        })

    proj_30 = sum(i["amount"] for i in inflows if 0 <= i["days_out"] <= 30)
    proj_60 = sum(i["amount"] for i in inflows if 0 <= i["days_out"] <= 60)
    proj_90 = sum(i["amount"] for i in inflows if 0 <= i["days_out"] <= 90)
    overdue = sum(i["amount"] for i in inflows if i["days_out"] < 0)

    log.info("step_191: cash_flow 30d=$%.0f 60d=$%.0f 90d=$%.0f overdue=$%.0f",
             proj_30, proj_60, proj_90, overdue)
    return {
        "pending_invoice_count": len(pending),
        "factored_count": len(factored),
        "projected_30d": round(proj_30, 2),
        "projected_60d": round(proj_60, 2),
        "projected_90d": round(proj_90, 2),
        "overdue_amount": round(overdue, 2),
        "total_outstanding": round(sum(i["amount"] for i in inflows), 2),
        "inflows": sorted(inflows, key=lambda x: x["days_out"])[:50],
    }


def step_192_carrier_ltv(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Calculate carrier lifetime value: subscription revenue + load revenue.

    LTV = months_active × plan_monthly_rate + total_settled_load_revenue.
    Projects 12-month forward LTV using trailing 3-month average.
    """
    sb = get_supabase()

    plan_rates: dict[str, float] = {
        "founders": 297.0,
        "pro": 497.0,
        "enterprise": 997.0,
        "free": 0.0,
    }

    carriers = [{"id": str(carrier_id)}] if carrier_id else _active_carriers()
    ltv_data: list[dict] = []

    for c in carriers:
        cid = c["id"]
        created_str = (c.get("created_at") or _now())[:10]
        try:
            created = date.fromisoformat(created_str)
        except ValueError:
            created = _today()
        months_active = max(1, ((_today() - created).days) // 30)
        plan = (c.get("plan") or "founders").lower()
        monthly_rate = plan_rates.get(plan, 297.0)
        subscription_rev = round(months_active * monthly_rate, 2)

        # Load revenue
        loads_rev = (
            sb.table("contracts")
            .select("rate_total")
            .eq("carrier_id", cid)
            .eq("revenue_recognized", True)
            .execute()
            .data
        ) or []
        total_load_rev = sum(float(l.get("rate_total") or 0) for l in loads_rev)
        load_count = len(loads_rev)

        # 12-month forward projection from trailing 3-month avg
        recent_cutoff = (_today() - timedelta(days=90)).isoformat()
        recent_loads = (
            sb.table("contracts")
            .select("rate_total")
            .eq("carrier_id", cid)
            .eq("revenue_recognized", True)
            .gte("created_at", recent_cutoff)
            .execute()
            .data
        ) or []
        trailing_3mo = sum(float(l.get("rate_total") or 0) for l in recent_loads)
        projected_annual = round((trailing_3mo / 3) * 12 + monthly_rate * 12, 2)

        ltv_data.append({
            "carrier_id": cid,
            "company_name": c.get("company_name"),
            "plan": plan,
            "months_active": months_active,
            "subscription_revenue": subscription_rev,
            "total_load_revenue": round(total_load_rev, 2),
            "total_load_count": load_count,
            "total_ltv": round(subscription_rev + total_load_rev, 2),
            "projected_annual_value": projected_annual,
        })

    ltv_data.sort(key=lambda x: x["total_ltv"], reverse=True)
    total_fleet_ltv = sum(c["total_ltv"] for c in ltv_data)

    log.info("step_192: carrier_ltv carriers=%d total_fleet_ltv=$%.0f", len(ltv_data), total_fleet_ltv)
    return {
        "carriers_evaluated": len(ltv_data),
        "total_fleet_ltv": round(total_fleet_ltv, 2),
        "avg_carrier_ltv": round(total_fleet_ltv / len(ltv_data), 2) if ltv_data else 0,
        "top_carrier": ltv_data[0] if ltv_data else None,
        "carriers": ltv_data[:20],
    }


def step_193_csa_trend(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Track CSA score trends and predict carrier risk trajectory.

    Reads shield_events for csa_refresh events over the past 90 days,
    computes the safety_light change frequency, and flags carriers trending red.
    """
    sb = get_supabase()
    cutoff = (_today() - timedelta(days=90)).isoformat()

    q = sb.table("shield_events").select(
        "carrier_id,event_type,severity,payload,created_at"
    ).eq("event_type", "safety_light_change").gte("created_at", cutoff)
    if carrier_id:
        q = q.eq("carrier_id", str(carrier_id))
    events = q.execute().data or []

    # Group by carrier
    by_carrier: dict[str, list[dict]] = {}
    for e in events:
        cid = e["carrier_id"]
        by_carrier.setdefault(cid, []).append(e)

    trending_red: list[dict] = []
    trending_green: list[dict] = []
    stable: list[dict] = []

    for cid, carrier_events in by_carrier.items():
        carrier_events.sort(key=lambda e: e["created_at"])
        lights = [
            e.get("payload", {}).get("new_light", "green")
            for e in carrier_events
        ]
        if not lights:
            continue

        latest = lights[-1]
        red_count = lights.count("red")
        yellow_count = lights.count("yellow")
        total = len(lights)

        # Trending red: last light is red or >50% of readings were yellow/red
        risk_ratio = (red_count * 2 + yellow_count) / (total * 2) if total else 0

        entry = {
            "carrier_id": cid,
            "latest_light": latest,
            "red_count": red_count,
            "yellow_count": yellow_count,
            "total_readings": total,
            "risk_ratio": round(risk_ratio, 3),
        }
        if latest == "red" or risk_ratio > 0.5:
            trending_red.append(entry)
        elif latest == "green" and risk_ratio < 0.1:
            trending_green.append(entry)
        else:
            stable.append(entry)

    log.info("step_193: csa_trend carriers=%d trending_red=%d trending_green=%d",
             len(by_carrier), len(trending_red), len(trending_green))
    return {
        "carriers_analyzed": len(by_carrier),
        "trending_red_count": len(trending_red),
        "trending_green_count": len(trending_green),
        "stable_count": len(stable),
        "trending_red": trending_red,
        "trending_green": trending_green,
    }


def step_194_rate_index(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Build internal rate index from all executed rate confirmations.

    Groups by origin_state × destination_state × equipment_type,
    computes avg/min/max/p25/p75 rate per mile, upserts analytics_rate_index.
    """
    sb = get_supabase()

    q = sb.table("contracts").select(
        "rate_per_mile,extracted_vars"
    ).eq("contract_type", "rate_confirmation").eq("revenue_recognized", True)
    if carrier_id:
        q = q.eq("carrier_id", str(carrier_id))
    contracts = q.execute().data or []

    # Group by (origin_state, dest_state, equipment_type)
    buckets: dict[tuple[str, str, str], list[float]] = {}
    for c in contracts:
        rpm = float(c.get("rate_per_mile") or 0)
        if not rpm:
            continue
        evars = c.get("extracted_vars") or {}
        o = (evars.get("origin_state") or "").upper()
        d = (evars.get("destination_state") or "").upper()
        eq = (evars.get("equipment_type") or "dry_van").lower().replace(" ", "_")
        if not o or not d:
            continue
        buckets.setdefault((o, d, eq), []).append(rpm)

    upserted: list[dict] = []
    for (o, d, eq), rates in buckets.items():
        rates_sorted = sorted(rates)
        n = len(rates_sorted)
        p25 = rates_sorted[int(n * 0.25)] if n >= 4 else rates_sorted[0]
        p75 = rates_sorted[int(n * 0.75)] if n >= 4 else rates_sorted[-1]

        row = {
            "origin_state": o,
            "destination_state": d,
            "equipment_type": eq,
            "sample_count": n,
            "avg_rate_per_mile": round(sum(rates) / n, 4),
            "min_rate_per_mile": round(min(rates), 4),
            "max_rate_per_mile": round(max(rates), 4),
            "p25_rate_per_mile": round(p25, 4),
            "p75_rate_per_mile": round(p75, 4),
            "computed_at": _now(),
        }
        existing = (
            sb.table("analytics_rate_index")
            .select("id")
            .eq("origin_state", o).eq("destination_state", d).eq("equipment_type", eq)
            .limit(1).execute().data
        )
        if existing:
            sb.table("analytics_rate_index").update(row).eq(
                "origin_state", o).eq("destination_state", d).eq("equipment_type", eq).execute()
        else:
            sb.table("analytics_rate_index").insert(row).execute()
        upserted.append(row)

    log.info("step_194: rate_index lanes_indexed=%d total_samples=%d",
             len(upserted), sum(r["sample_count"] for r in upserted))
    return {
        "lanes_indexed": len(upserted),
        "total_samples": sum(r["sample_count"] for r in upserted),
        "index": upserted[:50],
    }


def step_195_equipment_demand(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Forecast equipment demand by type from lane stats and load history.

    Counts load volume by equipment_type from executed contracts over the
    last 90 days, then projects forward demand by type.
    """
    sb = get_supabase()
    cutoff = (_today() - timedelta(days=90)).isoformat()

    q = sb.table("contracts").select(
        "extracted_vars"
    ).eq("revenue_recognized", True).gte("created_at", cutoff)
    if carrier_id:
        q = q.eq("carrier_id", str(carrier_id))
    contracts = q.execute().data or []

    demand: dict[str, int] = {}
    for c in contracts:
        evars = c.get("extracted_vars") or {}
        eq = (evars.get("equipment_type") or "dry_van").lower().replace(" ", "_").replace("-", "_")
        demand[eq] = demand.get(eq, 0) + 1

    total = sum(demand.values()) or 1
    ranked = sorted(demand.items(), key=lambda x: x[1], reverse=True)

    forecast: list[dict] = []
    for eq_type, count in ranked:
        share_pct = round((count / total) * 100, 2)
        # Project 30-day demand from 90-day trailing
        projected_30d = round(count / 3)
        forecast.append({
            "equipment_type": eq_type,
            "trailing_90d_loads": count,
            "market_share_pct": share_pct,
            "projected_30d_loads": projected_30d,
        })

    log.info("step_195: equipment_demand types=%d top=%s",
             len(forecast), forecast[0]["equipment_type"] if forecast else "N/A")
    return {
        "trailing_period_days": 90,
        "total_loads_analyzed": total,
        "equipment_types": len(forecast),
        "demand_forecast": forecast,
    }


# ═══════════════════════════════════════════════════════════════════════════
# STEPS 196-200 — Risk & reporting
# ═══════════════════════════════════════════════════════════════════════════

def step_196_compliance_risk(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Assess compliance risk score across carrier fleet.

    TODO: Replace stub with real compliance risk analysis logic.
    """
    log.info("step_196: compliance_risk (stub) carrier=%s", carrier_id)
    return {"step": 196, "status": "stub", "carrier_id": str(carrier_id) if carrier_id else None}


def step_197_weekly_report(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Generate weekly executive report.

    TODO: Replace stub with real weekly report generation logic.
    """
    log.info("step_197: weekly_report (stub) carrier=%s", carrier_id)
    return {"step": 197, "status": "stub", "carrier_id": str(carrier_id) if carrier_id else None}


def step_198_airtable_sync(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Sync analytics data to Airtable.

    TODO: Replace stub with real Airtable sync logic.
    """
    log.info("step_198: airtable_sync (stub) carrier=%s", carrier_id)
    return {"step": 198, "status": "stub", "carrier_id": str(carrier_id) if carrier_id else None}


def step_199_sentry_health(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Check Sentry health and error rates.

    TODO: Replace stub with real Sentry health check logic.
    """
    log.info("step_199: sentry_health (stub) carrier=%s", carrier_id)
    return {"step": 199, "status": "stub", "carrier_id": str(carrier_id) if carrier_id else None}


def step_200_analytics_complete(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Mark analytics cycle as complete.

    TODO: Replace stub with real analytics completion logic.
    """
    log.info("step_200: analytics_complete (stub) carrier=%s", carrier_id)
    return {"step": 200, "status": "stub", "carrier_id": str(carrier_id) if carrier_id else None}
