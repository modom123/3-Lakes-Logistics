"""Duplicate check across leads + active_carriers on DOT/MC/phone/email."""
from __future__ import annotations

from typing import Any


def is_duplicate(record: dict[str, Any]) -> bool:
    dot = record.get("dot_number")
    mc = record.get("mc_number")
    phone = _normalize_phone(record.get("phone"))
    email = (record.get("email") or "").strip().lower() or None
    if not any([dot, mc, phone, email]):
        return False
    try:
        from ..supabase_client import get_supabase
        sb = get_supabase()
        for tbl in ("leads", "active_carriers"):
            q = sb.table(tbl).select("id").limit(1)
            if dot:
                if q.eq("dot_number", dot).execute().data:
                    return True
            if mc:
                if sb.table(tbl).select("id").eq("mc_number", mc).limit(1).execute().data:
                    return True
            if phone:
                if sb.table(tbl).select("id").eq("phone", phone).limit(1).execute().data:
                    return True
            if email:
                if sb.table(tbl).select("id").eq("email", email).limit(1).execute().data:
                    return True
    except Exception:  # noqa: BLE001
        return False
    return False


def _normalize_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return digits or None
