"""Shield — Compliance & insurance monitoring (Stage 5 step 63).

- fmcsa_sync     : refresh SAFER snapshot for every active carrier
- coi_expiry_scan: flag COIs expiring ≤ 30 days
- clearinghouse  : daily Clearinghouse check (stub until credentials)
- run            : inline safety light for a single DOT (unchanged API)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from ..integrations.fmcsa import snapshot as fmcsa_snapshot
from ..integrations.slack import post_alert
from ..logging_service import log_agent

SafetyLight = Literal["green", "yellow", "red"]


def _light_from_snapshot(snap, insurance_expiry: str | None) -> SafetyLight:
    if not snap:
        return "yellow"
    if snap.operating_status != "ACTIVE":
        return "red"
    if not snap.insurance_bipd_on_file:
        return "red"
    if insurance_expiry:
        try:
            exp = date.fromisoformat(insurance_expiry)
            if exp <= date.today():
                return "red"
            if (exp - date.today()).days <= 30:
                return "yellow"
        except ValueError:
            return "yellow"
    if snap.safety_rating == "UNSATISFACTORY":
        return "red"
    if snap.safety_rating == "CONDITIONAL":
        return "yellow"
    return "green"


def _update_compliance_row(carrier_id: str, fields: dict[str, Any]) -> None:
    try:
        from ..supabase_client import get_supabase
        fields = {**fields, "last_checked_at": datetime.now(timezone.utc).isoformat()}
        get_supabase().table("insurance_compliance").update(fields).eq(
            "carrier_id", carrier_id
        ).execute()
    except Exception as exc:  # noqa: BLE001
        log_agent("shield", "update_failed", carrier_id=carrier_id, error=str(exc))


def fmcsa_sync() -> dict[str, Any]:
    try:
        from ..supabase_client import get_supabase
        carriers = (
            get_supabase().table("active_carriers")
            .select("id, dot_number")
            .eq("status", "active").execute()
        ).data or []
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    checked = flagged = 0
    for c in carriers:
        dot = c.get("dot_number")
        if not dot:
            continue
        snap = fmcsa_snapshot(dot)
        insurance_expiry = _fetch_expiry(c["id"])
        light = _light_from_snapshot(snap, insurance_expiry)
        _update_compliance_row(c["id"], {
            "safety_light": light,
            "operating_status": snap.operating_status if snap else None,
            "safety_rating": snap.safety_rating if snap else None,
        })
        checked += 1
        if light == "red":
            flagged += 1
            post_alert(f":rotating_light: Shield flagged carrier {c['id']} (DOT {dot}) RED")
    log_agent("shield", "fmcsa_sync", result=f"checked={checked} red={flagged}")
    return {"status": "ok", "checked": checked, "flagged_red": flagged}


def coi_expiry_scan() -> dict[str, Any]:
    cutoff = (date.today() + timedelta(days=30)).isoformat()
    try:
        from ..supabase_client import get_supabase
        rows = (
            get_supabase().table("insurance_compliance")
            .select("carrier_id, policy_expiry")
            .lte("policy_expiry", cutoff).execute()
        ).data or []
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    warned = 0
    for row in rows:
        cid = row.get("carrier_id")
        exp = row.get("policy_expiry")
        try:
            days = (date.fromisoformat(exp) - date.today()).days
        except Exception:  # noqa: BLE001
            days = -1
        light = "red" if days <= 0 else "yellow"
        _update_compliance_row(cid, {"safety_light": light})
        post_alert(f"Shield: COI expires in {days}d for carrier {cid}")
        warned += 1
    log_agent("shield", "coi_expiry_scan", result=f"warned={warned}")
    return {"status": "ok", "warned": warned}


def clearinghouse_scan() -> dict[str, Any]:
    # FMCSA Clearinghouse API requires employer registration + OAuth;
    # until credentials are provisioned we log and no-op.
    log_agent("shield", "clearinghouse_scan", result="stub")
    return {"status": "stub", "reason": "clearinghouse_not_configured"}


def _fetch_expiry(carrier_id: str) -> str | None:
    try:
        from ..supabase_client import get_supabase
        rows = (
            get_supabase().table("insurance_compliance")
            .select("policy_expiry").eq("carrier_id", carrier_id).limit(1).execute()
        ).data or []
        return rows[0].get("policy_expiry") if rows else None
    except Exception:  # noqa: BLE001
        return None


def enqueue_safety_check(carrier_id: str, dot: str | None, _mc: str | None) -> None:
    snap = fmcsa_snapshot(dot) if dot else None
    light = _light_from_snapshot(snap, _fetch_expiry(carrier_id))
    _update_compliance_row(carrier_id, {
        "safety_light": light,
        "operating_status": snap.operating_status if snap else None,
    })


def run(payload: dict[str, Any]) -> dict[str, Any]:
    kind = payload.get("kind") or "check_one"
    if kind == "fmcsa_sync":
        return {"agent": "shield", **fmcsa_sync()}
    if kind == "coi_expiry_scan":
        return {"agent": "shield", **coi_expiry_scan()}
    if kind == "clearinghouse":
        return {"agent": "shield", **clearinghouse_scan()}
    dot = payload.get("dot_number")
    snap = fmcsa_snapshot(dot) if dot else None
    light = _light_from_snapshot(snap, payload.get("insurance_expiry"))
    return {
        "agent": "shield", "status": "ok",
        "dot": dot, "safety_light": light,
        "operating_status": snap.operating_status if snap else None,
        "safety_rating": snap.safety_rating if snap else None,
    }
