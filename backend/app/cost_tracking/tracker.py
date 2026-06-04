"""Cost Tracker — records per-call API costs and usage metrics to Supabase.

Each service helper converts raw units (tokens, minutes, calls) to USD and
writes a row to cost_entries. All helpers are fire-and-forget; they never
raise so they never block business logic.

Pricing table (updated 2026-06):
  Anthropic claude-opus-4-8    : $15.00/$75.00 per 1M tokens input/output
  Anthropic claude-sonnet-4-6  : $3.00/$15.00  per 1M tokens input/output
  Anthropic claude-haiku-4-5   : $0.25/$1.25   per 1M tokens input/output
  OpenRouter qwen-2.5-72b      : $0.35/$0.40   per 1M tokens input/output
  Bland AI                     : $0.06/minute
  Twilio SMS                   : $0.0075/message
  Twilio voice                 : $0.0130/minute
  Google Maps geocoding        : $0.0050/call
  Google Vision OCR            : $0.0015/image
  Stripe transaction           : 2.90% + $0.30 per charge
  Postmark                     : $0.0015/email
  SendGrid                     : $0.0010/email
  Checkr MVR                   : $15.00/check
"""
from __future__ import annotations

from typing import Any

from ..logging_service import get_logger

log = get_logger("cost.tracker")

# ── Anthropic pricing per 1M tokens ──────────────────────────────────────────

_ANTHROPIC_PRICING: dict[str, tuple[float, float]] = {
    # (input_per_1m, output_per_1m)
    "claude-opus-4-8":            (15.00, 75.00),
    "claude-opus-4-7":            (15.00, 75.00),
    "claude-opus-4-6":            (15.00, 75.00),
    "claude-sonnet-4-6":          ( 3.00, 15.00),
    "claude-sonnet-4-5":          ( 3.00, 15.00),
    "claude-haiku-4-5":           ( 0.25,  1.25),
    "claude-haiku-4-5-20251001":  ( 0.25,  1.25),
    "claude-3-5-sonnet-20241022": ( 3.00, 15.00),
    "claude-3-5-haiku-20241022":  ( 0.80,  4.00),
    "claude-3-haiku-20240307":    ( 0.25,  1.25),
    "claude-3-opus-20240229":     (15.00, 75.00),
}

_DEFAULT_ANTHROPIC = (3.00, 15.00)  # sonnet tier as safe default


def track(
    service: str,
    category: str,
    cost_usd: float,
    *,
    units: float | None = None,
    unit_type: str | None = None,
    description: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Write one cost_entry row. Never raises."""
    if cost_usd <= 0:
        return
    try:
        from ..supabase_client import get_supabase
        get_supabase().table("cost_entries").insert({
            "service": service,
            "category": category,
            "cost_usd": round(cost_usd, 6),
            "units": units,
            "unit_type": unit_type,
            "description": description,
            "metadata": metadata or {},
        }).execute()
    except Exception as exc:  # noqa: BLE001
        log.warning("cost_entry write failed service=%s: %s", service, exc)


def track_anthropic(
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    agent: str | None = None,
    carrier_id: str | None = None,
) -> None:
    """Track an Anthropic Claude API call cost."""
    in_price, out_price = _ANTHROPIC_PRICING.get(model, _DEFAULT_ANTHROPIC)
    cost = (input_tokens / 1_000_000 * in_price) + (output_tokens / 1_000_000 * out_price)
    total_tokens = input_tokens + output_tokens
    track(
        service="anthropic",
        category="ai_llm",
        cost_usd=cost,
        units=total_tokens,
        unit_type="tokens",
        description=f"{model} · {agent or 'unknown'} agent",
        metadata={
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "agent": agent,
            "carrier_id": carrier_id,
        },
    )


def track_openrouter(
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    agent: str | None = None,
) -> None:
    """Track an OpenRouter LLM call cost (Qwen default: $0.35/$0.40 per 1M)."""
    in_cost = input_tokens / 1_000_000 * 0.35
    out_cost = output_tokens / 1_000_000 * 0.40
    cost = in_cost + out_cost
    track(
        service="openrouter",
        category="ai_llm",
        cost_usd=cost,
        units=input_tokens + output_tokens,
        unit_type="tokens",
        description=f"{model} · {agent or 'unknown'}",
        metadata={"model": model, "input_tokens": input_tokens, "output_tokens": output_tokens, "agent": agent},
    )


def track_bland_ai(
    duration_minutes: float,
    *,
    call_id: str | None = None,
    agent: str | None = None,
    carrier_id: str | None = None,
) -> None:
    """Track a Bland AI outbound voice call at $0.06/minute."""
    cost = duration_minutes * 0.06
    track(
        service="bland_ai",
        category="communications",
        cost_usd=cost,
        units=duration_minutes,
        unit_type="minutes",
        description=f"voice call · {agent or 'vance'}",
        metadata={"call_id": call_id, "agent": agent, "carrier_id": carrier_id},
    )


def track_twilio(
    *,
    sms_count: int = 0,
    call_minutes: float = 0.0,
    carrier_id: str | None = None,
) -> None:
    """Track Twilio SMS ($0.0075/msg) and/or voice ($0.013/min) costs."""
    cost = sms_count * 0.0075 + call_minutes * 0.013
    if cost <= 0:
        return
    parts = []
    if sms_count:
        parts.append(f"{sms_count} SMS")
    if call_minutes:
        parts.append(f"{call_minutes:.1f} min voice")
    track(
        service="twilio",
        category="communications",
        cost_usd=cost,
        units=sms_count + call_minutes,
        unit_type="mixed",
        description=", ".join(parts),
        metadata={"sms_count": sms_count, "call_minutes": call_minutes, "carrier_id": carrier_id},
    )


def track_postmark(
    email_count: int = 1,
    *,
    template: str | None = None,
) -> None:
    """Track Postmark transactional email at $0.0015/email."""
    track(
        service="postmark",
        category="communications",
        cost_usd=email_count * 0.0015,
        units=email_count,
        unit_type="emails",
        description=template or "transactional email",
    )


def track_sendgrid(
    email_count: int = 1,
    *,
    purpose: str | None = None,
) -> None:
    """Track SendGrid email at $0.001/email."""
    track(
        service="sendgrid",
        category="communications",
        cost_usd=email_count * 0.001,
        units=email_count,
        unit_type="emails",
        description=purpose or "inbound parse / transactional",
    )


def track_google_maps(
    call_count: int = 1,
    *,
    operation: str = "geocoding",
) -> None:
    """Track Google Maps API at $0.005/call."""
    track(
        service="google_maps",
        category="data",
        cost_usd=call_count * 0.005,
        units=call_count,
        unit_type="api_calls",
        description=operation,
    )


def track_google_vision(
    image_count: int = 1,
    *,
    operation: str = "ocr",
) -> None:
    """Track Google Vision OCR at $0.0015/image."""
    track(
        service="google_vision",
        category="data",
        cost_usd=image_count * 0.0015,
        units=image_count,
        unit_type="images",
        description=operation,
    )


def track_stripe_fee(
    charge_amount_usd: float,
    *,
    transaction_type: str = "charge",
    carrier_id: str | None = None,
) -> None:
    """Track Stripe processing fee (2.9% + $0.30 per charge)."""
    fee = charge_amount_usd * 0.029 + 0.30
    track(
        service="stripe",
        category="payments",
        cost_usd=fee,
        units=charge_amount_usd,
        unit_type="usd_charged",
        description=f"stripe {transaction_type} fee",
        metadata={"charge_amount": charge_amount_usd, "type": transaction_type, "carrier_id": carrier_id},
    )


def track_checkr(
    check_count: int = 1,
    *,
    check_type: str = "mvr",
    driver_id: str | None = None,
) -> None:
    """Track Checkr background check at $15/MVR."""
    rates = {"mvr": 15.00, "background": 29.00, "drug_test": 65.00}
    rate = rates.get(check_type, 15.00)
    track(
        service="checkr",
        category="compliance",
        cost_usd=check_count * rate,
        units=check_count,
        unit_type="checks",
        description=f"checkr {check_type}",
        metadata={"check_type": check_type, "driver_id": driver_id},
    )
