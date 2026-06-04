"""Drew Calloway — Shipper Development Rep, Broker Division.

Drew's job is pure revenue: land shipper accounts. Not carriers — shippers.
Manufacturers, distributors, retailers, e-commerce fulfillment centers —
any company that moves freight and needs a reliable broker.

He works a different list than Vance. Vance calls carriers to recruit them.
Drew calls shippers to win their freight. Same Bland AI infrastructure,
completely different script and value proposition.

One active shipper posting 5 loads/week at $2,500 average = $650K/year gross.
Drew's job is to stack those accounts.

Actions via run(payload):
  prospect        — dial a batch of shippers via Bland AI
  add_shipper     — manually add a shipper account to the CRM
  call_shipper    — one-off Bland AI call to a specific shipper
  pipeline        — shipper CRM: status breakdown, revenue by account
  update_shipper  — update status/notes on a shipper record
"""
from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from .bland_client import start_outbound_call
from . import memory as mem

_SHIPPER_SCRIPT = """Hi, this is Drew Calloway calling from 3 Lakes Logistics. We're a \
licensed freight broker based in the Midwest and I'm reaching out because we work with \
companies in your industry to move freight at competitive rates with same-day booking and \
real-time load tracking. Who handles your freight and transportation decisions? \
I'd love to put together a quick rate comparison for your top lanes."""

_QUALIFY_SYSTEM = """You are Drew Calloway, Shipper Development Rep at 3 Lakes Logistics.

Given a shipper prospect (company type, industry, location), score their fit as a
brokerage customer and suggest the outreach angle.

Return valid JSON only:
{
  "fit_score": 8,
  "primary_angle": "one sentence — what pain point to lead with",
  "estimated_loads_per_week": 10,
  "estimated_avg_load_value": 2200,
  "est_annual_revenue": 1144000,
  "priority": "high" | "medium" | "low"
}"""


def _normalize_phone(phone: str) -> str | None:
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return None


def _qualify_prospect(prospect: dict) -> dict | None:
    s = get_settings()
    if not s.anthropic_api_key:
        return None
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": s.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 250,
                "system": _QUALIFY_SYSTEM,
                "messages": [{"role": "user", "content": f"Qualify this shipper prospect:\n\n{json.dumps(prospect, default=str)}"}],
            },
            timeout=15,
        )
        if r.status_code == 200:
            _d = r.json()
            try:
                from ..cost_tracking import track_anthropic as _ta
                _usage = _d.get("usage", {})
                _ta("claude-haiku-4-5-20251001", _usage.get("input_tokens", 0), _usage.get("output_tokens", 0), agent="drew")
            except Exception:
                pass
            text = _d["content"][0]["text"].strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
    except Exception:
        pass
    return None


def prospect(payload: dict) -> dict:
    """Dial a batch of shipper prospects via Bland AI."""
    limit  = int(payload.get("limit") or 20)
    states = payload.get("states") or []  # optional state filter
    db     = get_supabase()

    cutoff = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    query  = (
        db.table("broker_shippers")
        .select("id,company_name,contact_name,phone,address_state,primary_commodity")
        .in_("status", ["prospect", "contacted"])
        .not_.is_("phone", "null")
        .or_(f"last_contact_at.is.null,last_contact_at.lt.{cutoff}")
        .limit(limit)
    )
    if states:
        query = query.in_("address_state", states)

    rows = query.execute().data or []

    called, errors = 0, 0
    now = datetime.now(timezone.utc).isoformat()

    for row in rows:
        phone = _normalize_phone(row.get("phone") or "")
        if not phone:
            errors += 1
            continue

        result = start_outbound_call(
            lead_id=str(row["id"]),
            phone=phone,
            prospect_name=row.get("contact_name") or "there",
            prospect_email="",
            company_name=row.get("company_name") or "",
            dot_number="",
            current_pain="freight cost and reliability",
            webhook_url="",
        )

        if result.get("status") == "started":
            db.table("broker_shippers").update({
                "last_contact_at": now,
                "status": "contacted",
            }).eq("id", row["id"]).execute()
            called += 1
        else:
            errors += 1

        time.sleep(1)

    log_agent("drew", "prospect", result=f"called={called} errors={errors}")
    return {"agent": "drew", "action": "prospect", "called": called, "errors": errors, "batch_size": len(rows)}


def add_shipper(payload: dict) -> dict:
    """Add a shipper account to the CRM."""
    if not payload.get("company_name"):
        return {"agent": "drew", "status": "error", "error": "company_name required"}

    qual = _qualify_prospect({
        "company": payload.get("company_name"),
        "industry": payload.get("primary_commodity"),
        "state": payload.get("address_state"),
        "avg_loads_per_week": payload.get("avg_loads_per_week"),
    })

    row = {
        "company_name":        payload["company_name"],
        "contact_name":        payload.get("contact_name"),
        "phone":               payload.get("phone"),
        "email":               payload.get("email"),
        "address_city":        payload.get("address_city"),
        "address_state":       (payload.get("address_state") or "").upper()[:2] or None,
        "primary_commodity":   payload.get("primary_commodity"),
        "trailer_types":       payload.get("trailer_types") or ["dry_van"],
        "avg_loads_per_week":  payload.get("avg_loads_per_week") or (qual or {}).get("estimated_loads_per_week"),
        "avg_load_value":      payload.get("avg_load_value")     or (qual or {}).get("estimated_avg_load_value"),
        "status":              payload.get("status", "prospect"),
        "source":              payload.get("source", "drew"),
        "notes":               payload.get("notes"),
    }

    result = get_supabase().table("broker_shippers").insert(row).execute()
    shipper_id = (result.data or [{}])[0].get("id") if result.data else None

    log_agent("drew", "add_shipper", payload={"company": row["company_name"]},
              result=f"id={shipper_id} fit={( qual or {}).get('fit_score','?')}")
    return {
        "agent": "drew",
        "action": "add_shipper",
        "status": "added",
        "shipper_id": shipper_id,
        "company_name": row["company_name"],
        "ai_qualification": qual,
    }


def call_shipper(payload: dict) -> dict:
    """One-off Bland AI call to a specific shipper."""
    shipper_id   = payload.get("shipper_id")
    phone        = payload.get("phone")
    company_name = payload.get("company_name") or "Shipper"
    contact_name = payload.get("contact_name") or "there"

    if not phone and shipper_id:
        row = (get_supabase().table("broker_shippers").select("phone,company_name,contact_name")
               .eq("id", shipper_id).single().execute()).data or {}
        phone        = row.get("phone")
        company_name = row.get("company_name") or company_name
        contact_name = row.get("contact_name") or contact_name

    if not phone:
        return {"agent": "drew", "status": "error", "error": "phone required"}

    normalized = _normalize_phone(phone)
    if not normalized:
        return {"agent": "drew", "status": "error", "error": "invalid phone number"}

    result = start_outbound_call(
        lead_id=shipper_id or "direct",
        phone=normalized,
        prospect_name=contact_name,
        prospect_email=payload.get("email") or "",
        company_name=company_name,
        dot_number="",
        current_pain="freight cost and carrier reliability",
        webhook_url="",
    )

    if shipper_id and result.get("status") == "started":
        get_supabase().table("broker_shippers").update({
            "last_contact_at": datetime.now(timezone.utc).isoformat(),
            "status": "contacted",
        }).eq("id", shipper_id).execute()

    log_agent("drew", "call_shipper", payload={"phone": phone, "company": company_name},
              result=result.get("status", "unknown"))
    return {"agent": "drew", "action": "call_shipper", "company": company_name, "call_result": result}


def pipeline(payload: dict) -> dict:
    """Shipper CRM pipeline — status breakdown and top accounts by revenue."""
    db   = get_supabase()
    rows = (
        db.table("broker_shippers")
        .select("id,company_name,status,address_state,primary_commodity,avg_loads_per_week,avg_load_value,total_loads_brokered,total_revenue,last_contact_at,next_followup")
        .order("total_revenue", desc=True)
        .limit(100)
        .execute()
    ).data or []

    by_status: dict[str, int] = {}
    for r in rows:
        s = r.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1

    active = [r for r in rows if r.get("status") == "active"]
    total_active_revenue = sum(float(r.get("total_revenue") or 0) for r in active)

    # Overdue follow-ups
    today = date.today().isoformat()
    overdue = [r for r in rows if r.get("next_followup") and r["next_followup"] < today]

    log_agent("drew", "pipeline", result=f"total={len(rows)} active={len(active)} revenue=${total_active_revenue:.0f}")
    return {
        "agent": "drew",
        "action": "pipeline",
        "total_shippers": len(rows),
        "by_status": by_status,
        "active_accounts": len(active),
        "active_revenue_ytd": round(total_active_revenue, 2),
        "overdue_followups": len(overdue),
        "top_accounts": active[:10],
        "all_shippers": rows[:50],
    }


def update_shipper(payload: dict) -> dict:
    """Update status, notes, or follow-up date on a shipper record."""
    shipper_id = payload.get("shipper_id") or payload.get("id")
    if not shipper_id:
        return {"agent": "drew", "status": "error", "error": "shipper_id required"}

    update: dict[str, Any] = {}
    for field in ["status", "notes", "next_followup", "contact_name", "phone", "email",
                  "avg_loads_per_week", "avg_load_value", "primary_commodity"]:
        if payload.get(field) is not None:
            update[field] = payload[field]

    if not update:
        return {"agent": "drew", "status": "error", "error": "no fields to update"}

    get_supabase().table("broker_shippers").update(update).eq("id", shipper_id).execute()
    log_agent("drew", "update_shipper", payload={"id": shipper_id}, result=str(update))
    return {"agent": "drew", "action": "update_shipper", "status": "updated", "shipper_id": shipper_id, "fields": list(update.keys())}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action", "pipeline")
    if action == "prospect":
        return prospect(payload)
    if action == "add_shipper":
        return add_shipper(payload)
    if action == "call_shipper":
        return call_shipper(payload)
    if action == "pipeline":
        return pipeline(payload)
    if action == "update_shipper":
        return update_shipper(payload)
    return {"agent": "drew", "status": "error", "error": f"unknown action: {action}",
            "valid_actions": ["prospect", "add_shipper", "call_shipper", "pipeline", "update_shipper"]}
