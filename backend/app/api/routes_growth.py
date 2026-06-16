"""Growth Command — revenue planning and prospect seeding for both business units."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any
import httpx
from fastapi import APIRouter, Depends
from ..api.deps import require_bearer
from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase

router = APIRouter(prefix="/api/growth", dependencies=[Depends(require_bearer)])

_REVENUE_TARGETS = {
    "year_2": {"trading_desk": 1_000_000, "light_fleet": 1_000_000},
    "year_5": {"trading_desk": 10_000_000, "light_fleet": 10_000_000},
}

# ── NPI Registry — free public API for healthcare facility data ──────────────

def _fetch_npi_prospects(taxonomy: str, state: str, limit: int = 20) -> list[dict]:
    """Pull real healthcare facilities from CMS NPI Registry (no key required)."""
    try:
        r = httpx.get(
            "https://npiregistry.cms.hhs.gov/api/",
            params={
                "taxonomy_description": taxonomy,
                "state": state,
                "limit": min(limit, 200),
                "version": "2.1",
                "enumeration_type": "NPI-2",  # organizations only
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        prospects = []
        for r2 in results:
            basic = r2.get("basic") or {}
            addrs = r2.get("addresses") or [{}]
            addr = addrs[0] if addrs else {}
            phones = [a.get("telephone_number") for a in addrs if a.get("telephone_number")]
            name = basic.get("organization_name") or basic.get("name") or ""
            if not name:
                continue
            prospects.append({
                "company": name,
                "contact": basic.get("authorized_official_first_name", "") + " " + basic.get("authorized_official_last_name", ""),
                "phone": phones[0] if phones else None,
                "email": None,
                "city": addr.get("city"),
                "state": addr.get("state"),
                "sector": "healthcare",
                "rep": "marcus_webb",
                "status": "prospect",
                "source": "npi_registry",
                "notes": f"NPI: {r2.get('number')} · Taxonomy: {taxonomy}",
            })
        return prospects
    except Exception:
        return []


def _claude_generate_prospects(sector: str, context: str, limit: int = 15) -> list[dict]:
    """Use Claude to generate realistic B2B prospects for a given sector."""
    s = get_settings()
    if not s.anthropic_api_key:
        return []
    system = (
        f"You are a B2B sales researcher. Generate {limit} realistic US company prospects "
        f"for a {sector} transportation service. Return ONLY a valid JSON array, no markdown. "
        "Each item: {\"company\": string, \"contact\": string, \"phone\": \"(XXX) XXX-XXXX\", "
        "\"email\": string or null, \"city\": string, \"state\": two-letter, \"sector\": string, "
        "\"rep\": \"marcus_webb\", \"status\": \"prospect\", \"source\": \"claude_ai\", "
        "\"notes\": one sentence about their transport needs}"
    )
    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": s.anthropic_api_key, "anthropic-version": "2023-06-01",
                     "Content-Type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 2000,
                  "system": system,
                  "messages": [{"role": "user", "content": context}]},
            timeout=20,
        )
        if resp.status_code == 200:
            text = resp.json()["content"][0]["text"].strip()
            if text.startswith("```"):
                text = "\n".join(text.split("\n")[1:])
                text = text.rsplit("```", 1)[0]
            return json.loads(text)
    except Exception:
        pass
    return []


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/seed-shippers")
def seed_shippers() -> dict:
    """Seed broker_shippers with AI-generated shipper prospects and start Drew dialing."""
    from ..agents import drew
    result = drew.run({"action": "seed_prospects"})
    log_agent("drew", "seed_shippers_via_growth", result=str(result))
    # Immediately kick off a prospect call batch
    call_result = drew.run({"action": "prospect", "limit": 10})
    return {"ok": True, "seed": result, "calls": call_result}


@router.post("/seed-lf-prospects")
def seed_lf_prospects(body: dict = {}) -> dict:  # noqa: B006
    """Seed lf_bd_prospects with real NPI healthcare facilities + AI-generated enterprise/platform leads."""
    db = get_supabase()
    seeded, errors = 0, 0
    now = datetime.now(timezone.utc).isoformat()

    all_prospects: list[dict] = []

    # Healthcare / NEMT — real NPI Registry data
    nemt_taxonomies = [
        ("dialysis", ["IL", "TX", "FL", "OH", "GA"]),
        ("skilled nursing", ["IL", "TX", "FL"]),
        ("home health", ["IL", "TX", "GA"]),
    ]
    for taxonomy, states in nemt_taxonomies:
        for state in states:
            prospects = _fetch_npi_prospects(taxonomy, state, limit=10)
            all_prospects.extend(prospects)

    # Enterprise — AI-generated hotel/corporate/university transport prospects
    enterprise_raw = _claude_generate_prospects(
        "executive and corporate shuttle",
        "Generate prospects for corporate shuttle / executive transport: hotels (Marriott, Hilton, etc), "
        "hospitals (for staff transport), large law firms, consulting companies, convention centers. "
        "Target IL, TX, FL, GA, OH. These companies need reliable driver services for VIP clients and staff.",
        limit=15,
    )
    for p in enterprise_raw:
        p["sector"] = "enterprise"
    all_prospects.extend(enterprise_raw)

    # Platform / last-mile — AI-generated e-commerce / fulfillment prospects
    platform_raw = _claude_generate_prospects(
        "last-mile courier and delivery",
        "Generate prospects for last-mile courier services: regional e-commerce fulfillment centers, "
        "medical labs, pharmacies, auto parts distributors, grocery chains. Target IL, TX, FL, GA, TN. "
        "These need regular courier and same-day delivery drivers.",
        limit=15,
    )
    for p in platform_raw:
        p["sector"] = "platform"
    all_prospects.extend(platform_raw)

    # Insert into lf_bd_prospects
    for p in all_prospects:
        company = (p.get("company") or "").strip()
        if not company:
            continue
        try:
            db.table("lf_bd_prospects").insert({
                "company": company,
                "contact": (p.get("contact") or "").strip() or None,
                "phone": p.get("phone"),
                "email": p.get("email"),
                "city": p.get("city"),
                "state": p.get("state"),
                "sector": p.get("sector") or "healthcare",
                "rep": p.get("rep") or "marcus_webb",
                "status": "prospect",
                "source": p.get("source") or "growth_seed",
                "notes": p.get("notes"),
                "sequence_step": 0,
                "email_count": 0,
                "call_count": 0,
                "do_not_contact": False,
                "created_at": now,
            }).execute()
            seeded += 1
        except Exception:
            errors += 1

    log_agent("lf_bizdev", "seed_prospects", result=f"seeded={seeded} errors={errors}")

    # Start the outreach sequences
    from ..agents import lf_bizdev
    email_result = lf_bizdev.run_email_sequence(daily_limit=20)
    call_result = lf_bizdev.run_call_sequence(daily_limit=10)

    return {
        "ok": True,
        "prospects_seeded": seeded,
        "seed_errors": errors,
        "email_outreach": email_result,
        "call_outreach": call_result,
    }


@router.post("/plan")
def generate_growth_plan(body: dict = {}) -> dict:  # noqa: B006
    """Run CC Gulley + James Bond with revenue targets and store structured growth plan."""
    from ..agents import memory as mem

    s = get_settings()
    targets = {
        "year_2_per_segment": body.get("year_2", 1_000_000),
        "year_5_per_segment": body.get("year_5", 10_000_000),
        "segments": ["north_american_trading_desk", "light_fleet_bizdev"],
    }

    plan_text = ""
    if s.anthropic_api_key:
        try:
            prompt = f"""You are CC Gulley, Chief Strategy Officer at 3 Lakes Logistics.

3 Lakes Logistics operates two growth businesses:
1. **North American Trading Desk** — freight brokerage. Revenue = (sell rate - buy rate) per load.
   Drew Calloway prospects shippers. Rex books loads. Casey covers with carriers. Jordan finds lanes.
   Current: Starting from zero. Bland AI cold calling + email.

2. **Light Fleet Business Development** — non-asset transport (NEMT, executive, courier, gig economy).
   Automated 5-touch email drip + Bland AI outbound calling. Three reps targeting healthcare, enterprise, platform.
   Current: Sequences built, prospect seeding just launched.

Revenue targets: ${targets['year_2_per_segment']:,} per segment by Year 2 (2027), ${targets['year_5_per_segment']:,} per segment by Year 5 (2030).

Produce a structured 90-day execution plan for EACH segment with:
- Monthly revenue milestones (Month 1, 3, 6, 12, 24, 60)
- Key metrics to track (loads/week, active shippers, trips/day, active clients)
- Top 5 priority actions for the first 30 days
- What needs to be true to hit Year 2 ($1M)
- What needs to be true to hit Year 5 ($10M)
- Network partnerships to pursue (load boards, NEMT networks, delivery platforms)
- Risk factors and mitigations

Format as structured JSON with keys: trading_desk and light_fleet, each containing: milestones (array), kpis (array), first_30_days (array of 5 actions), year_2_requirements (array), year_5_requirements (array), partnerships (array), risks (array)."""

            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": s.anthropic_api_key, "anthropic-version": "2023-06-01",
                         "Content-Type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 3000,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=30,
            )
            if resp.status_code == 200:
                plan_text = resp.json()["content"][0]["text"].strip()
        except Exception:
            pass

    # Parse plan if JSON
    plan_data: dict = {}
    if plan_text:
        try:
            clean = plan_text
            if clean.startswith("```"):
                clean = "\n".join(clean.split("\n")[1:]).rsplit("```", 1)[0]
            plan_data = json.loads(clean)
        except Exception:
            plan_data = {"raw": plan_text}

    ts = datetime.now(timezone.utc).isoformat()
    full_plan = {
        "generated_at": ts,
        "targets": targets,
        "plan": plan_data,
        "issued_by": "cc_gulley",
    }

    # Store in CC Gulley's memory so Bond can reference it
    mem.remember("cc_gulley", "growth_plan", full_plan, confidence=0.95,
                 source_agent="commander", summary=f"Growth plan: $1M/segment Year 2 → $10M/segment Year 5")
    mem.remember("cc_gulley", f"directive:{ts}", {
        "subject": "Revenue Growth Plan — $1M Year 2 / $10M Year 5",
        "message": f"Growth plan stored. Targets: ${targets['year_2_per_segment']:,}/segment by 2027, ${targets['year_5_per_segment']:,}/segment by 2030.",
        "issued_at": ts,
        "from": "commander",
    }, confidence=0.9, source_agent="commander", summary="Revenue Growth Plan")

    log_agent("cc_gulley", "growth_plan_generated",
              payload=targets, result=f"Plan stored — Year 2 ${targets['year_2_per_segment']:,}/segment")

    return {"ok": True, "plan": full_plan}


@router.get("/dashboard")
def growth_dashboard() -> dict:
    """Combined revenue + pipeline snapshot for both business units."""
    db = get_supabase()

    # Trading Desk pipeline
    shippers = (db.table("broker_shippers")
                .select("status,total_revenue,avg_loads_per_week,avg_load_value")
                .limit(500).execute()).data or []
    shipper_by_status: dict[str, int] = {}
    for s in shippers:
        st = s.get("status") or "unknown"
        shipper_by_status[st] = shipper_by_status.get(st, 0) + 1
    td_active_rev = sum(float(s.get("total_revenue") or 0) for s in shippers if s.get("status") == "active")
    td_pipeline_value = sum(
        float(s.get("avg_loads_per_week") or 0) * float(s.get("avg_load_value") or 2500) * 52 * 0.15
        for s in shippers if s.get("status") in ("prospect", "contacted", "qualified")
    )

    # Light Fleet pipeline
    lf_prospects = (db.table("lf_bd_prospects")
                    .select("status,sector,sequence_step")
                    .limit(500).execute()).data or []
    lf_by_status: dict[str, int] = {}
    lf_by_sector: dict[str, int] = {}
    for p in lf_prospects:
        st = p.get("status") or "prospect"
        lf_by_status[st] = lf_by_status.get(st, 0) + 1
        sec = p.get("sector") or "unknown"
        lf_by_sector[sec] = lf_by_sector.get(sec, 0) + 1

    # LF revenue from trips
    try:
        trips = (db.table("light_vehicle_trips")
                 .select("rate_total,status").eq("status", "completed").limit(2000).execute()).data or []
        lf_revenue = sum(float(t.get("rate_total") or 0) for t in trips)
    except Exception:
        lf_revenue = 0.0

    return {
        "ok": True,
        "targets": _REVENUE_TARGETS,
        "trading_desk": {
            "total_shippers": len(shippers),
            "by_status": shipper_by_status,
            "active_revenue_ytd": round(td_active_rev, 2),
            "pipeline_annualized_value": round(td_pipeline_value, 2),
            "year_2_gap": max(0, _REVENUE_TARGETS["year_2"]["trading_desk"] - td_active_rev),
        },
        "light_fleet": {
            "total_prospects": len(lf_prospects),
            "by_status": lf_by_status,
            "by_sector": lf_by_sector,
            "revenue_ytd": round(lf_revenue, 2),
            "year_2_gap": max(0, _REVENUE_TARGETS["year_2"]["light_fleet"] - lf_revenue),
        },
    }
