"""Roadie API client — UPS-owned same-day delivery platform.

Docs: https://docs.roadie.com
Driver signup: https://driver.roadie.com
API support: api_support@roadie.com

Environment variables required:
  ROADIE_API_KEY   — Bearer token from your Roadie developer/carrier account

Key endpoints:
  GET  /v1/estimates            rate estimate for a shipment
  POST /v1/shipments            create a shipment (shipper side)
  GET  /v1/shipments            list shipments with status filters
  GET  /v1/shipments/{id}       get shipment detail
  POST /v1/shipments/{id}/cancel   cancel a shipment
  GET  /v1/gigs/available       driver-side: available gigs near a location
  POST /v1/gigs/{id}/claim      driver-side: claim a gig
  POST /v1/webhooks             register webhook for status events

Roadie supports two integration modes:
  1. Shipper mode  — create + track outbound deliveries (your business sends packages)
  2. Driver mode   — claim inbound gigs (your drivers pick up Roadie loads)

For Light Fleet, we use Driver mode: poll available gigs → claim → dispatch to driver.
"""
from __future__ import annotations

from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings

_NAME = "roadie_client"
_BASE = "https://connect.roadie.com/v1"


def _headers() -> dict[str, str]:
    key = get_settings().roadie_api_key
    if not key:
        raise RuntimeError("ROADIE_API_KEY not configured — sign up at driver.roadie.com")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _get(path: str, params: dict | None = None) -> Any:
    r = httpx.get(f"{_BASE}{path}", headers=_headers(), params=params or {}, timeout=15)
    r.raise_for_status()
    return r.json()


def _post(path: str, body: dict | None = None) -> Any:
    r = httpx.post(f"{_BASE}{path}", headers=_headers(), json=body or {}, timeout=15)
    r.raise_for_status()
    return r.json()


# ── Driver-side (receive loads) ───────────────────────────────────────────────

def available_gigs(
    lat: float | None = None,
    lng: float | None = None,
    radius_miles: int = 25,
    limit: int = 25,
) -> list[dict]:
    """
    Fetch available Roadie gigs near a location.
    If lat/lng not provided, Roadie returns gigs in the account's registered service area.
    """
    params: dict = {"limit": limit, "radius": radius_miles}
    if lat is not None:
        params["lat"] = lat
    if lng is not None:
        params["lng"] = lng
    try:
        data = _get("/gigs/available", params)
        gigs = data if isinstance(data, list) else data.get("gigs") or data.get("data") or []
        log_agent(_NAME, "available_gigs", result=f"{len(gigs)} gigs")
        return gigs
    except httpx.HTTPStatusError as e:
        log_agent(_NAME, "available_gigs_error", error=f"HTTP {e.response.status_code}: {e.response.text[:200]}")
        return []
    except Exception as e:  # noqa: BLE001
        log_agent(_NAME, "available_gigs_error", error=str(e)[:200])
        return []


def claim_gig(gig_id: str, driver_id: str | None = None) -> dict[str, Any]:
    """Claim an available gig for a driver."""
    body: dict = {}
    if driver_id:
        body["driver_id"] = driver_id
    try:
        result = _post(f"/gigs/{gig_id}/claim", body)
        log_agent(_NAME, "claim_gig", payload={"gig_id": gig_id}, result="claimed")
        return {"claimed": True, "gig": result}
    except httpx.HTTPStatusError as e:
        return {"claimed": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:  # noqa: BLE001
        return {"claimed": False, "error": str(e)[:200]}


# ── Shipper-side (send shipments) ─────────────────────────────────────────────

def get_estimate(
    pickup_address: str,
    delivery_address: str,
    size: str = "small",
) -> dict[str, Any]:
    """
    Get a rate estimate for a shipment.
    size: 'envelope' | 'small' | 'medium' | 'large' | 'xlarge'
    """
    try:
        result = _post("/estimates", {
            "pickup": {"address": pickup_address},
            "delivery": {"address": delivery_address},
            "size": size,
        })
        return {"estimated": True, "estimate": result}
    except Exception as e:  # noqa: BLE001
        return {"estimated": False, "error": str(e)[:200]}


def create_shipment(
    pickup_address: str,
    delivery_address: str,
    contact_name: str,
    contact_phone: str,
    description: str,
    size: str = "small",
    reference_id: str | None = None,
) -> dict[str, Any]:
    """Create a new Roadie shipment (shipper mode — for sending packages out)."""
    body: dict = {
        "pickup": {
            "address": pickup_address,
            "contact": {"name": contact_name, "phone": contact_phone},
        },
        "delivery": {
            "address": delivery_address,
            "contact": {"name": contact_name, "phone": contact_phone},
        },
        "items": [{"description": description, "quantity": 1, "size": size}],
    }
    if reference_id:
        body["reference_id"] = reference_id
    try:
        result = _post("/shipments", body)
        shipment_id = result.get("id") if isinstance(result, dict) else None
        log_agent(_NAME, "create_shipment", payload={"reference_id": reference_id}, result=str(shipment_id))
        return {"created": True, "shipment_id": shipment_id, "shipment": result}
    except Exception as e:  # noqa: BLE001
        return {"created": False, "error": str(e)[:200]}


def list_shipments(status: str | None = None, limit: int = 25) -> list[dict]:
    """List shipments, optionally filtered by status."""
    params: dict = {"limit": limit}
    if status:
        params["state"] = status
    try:
        data = _get("/shipments", params)
        return data if isinstance(data, list) else data.get("shipments") or data.get("data") or []
    except Exception as e:  # noqa: BLE001
        log_agent(_NAME, "list_shipments_error", error=str(e)[:200])
        return []


def get_shipment(shipment_id: str) -> dict[str, Any]:
    """Get full detail for a shipment."""
    try:
        return _get(f"/shipments/{shipment_id}")
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def cancel_shipment(shipment_id: str) -> dict[str, Any]:
    """Cancel a shipment."""
    try:
        result = _post(f"/shipments/{shipment_id}/cancel")
        log_agent(_NAME, "cancel_shipment", payload={"shipment_id": shipment_id})
        return {"cancelled": True, "result": result}
    except Exception as e:  # noqa: BLE001
        return {"cancelled": False, "error": str(e)[:200]}


# ── Webhooks ──────────────────────────────────────────────────────────────────

def register_webhook(url: str, events: list[str] | None = None) -> dict[str, Any]:
    """Register a webhook endpoint to receive Roadie shipment status events."""
    body = {
        "url": url,
        "events": events or [
            "shipment.created",
            "shipment.driver_assigned",
            "shipment.picked_up",
            "shipment.delivered",
            "shipment.cancelled",
            "shipment.eta_updated",
        ],
    }
    try:
        result = _post("/webhooks", body)
        log_agent(_NAME, "register_webhook", payload={"url": url})
        return {"registered": True, "webhook": result}
    except Exception as e:  # noqa: BLE001
        return {"registered": False, "error": str(e)[:200]}


# ── Health check ──────────────────────────────────────────────────────────────

def ping() -> dict[str, Any]:
    """Test the API connection."""
    try:
        _get("/gigs/available", {"limit": 1})
        return {"connected": True, "platform": "roadie"}
    except RuntimeError as e:
        return {"connected": False, "platform": "roadie", "error": str(e)}
    except httpx.HTTPStatusError as e:
        return {"connected": False, "platform": "roadie", "error": f"HTTP {e.response.status_code}"}
    except Exception as e:  # noqa: BLE001
        return {"connected": False, "platform": "roadie", "error": str(e)[:200]}
