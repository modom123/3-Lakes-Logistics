"""Curri API client — same-day B2B delivery carrier integration.

Docs: https://docs.curri.com
Carrier signup: https://carriers.curri.com

Environment variables required:
  CURRI_API_KEY   — Bearer token from your Curri carrier account

Endpoints used:
  GET  /v1/orders/available     list orders available for pickup in your area
  POST /v1/orders/{id}/accept   accept an order
  POST /v1/orders/{id}/reject   decline an order
  GET  /v1/orders/{id}          get order detail
  POST /v1/orders/{id}/status   update trip status (en_route, arrived, delivered)
  POST /v1/webhooks             register a webhook endpoint
"""
from __future__ import annotations

from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings

_NAME = "curri_client"
_BASE = "https://api.curri.com/v1"


def _headers() -> dict[str, str]:
    key = get_settings().curri_api_key
    if not key:
        raise RuntimeError("CURRI_API_KEY not configured — sign up at carriers.curri.com")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _get(path: str, params: dict | None = None) -> dict[str, Any]:
    r = httpx.get(f"{_BASE}{path}", headers=_headers(), params=params or {}, timeout=15)
    r.raise_for_status()
    return r.json()


def _post(path: str, body: dict | None = None) -> dict[str, Any]:
    r = httpx.post(f"{_BASE}{path}", headers=_headers(), json=body or {}, timeout=15)
    r.raise_for_status()
    return r.json()


# ── Public API ────────────────────────────────────────────────────────────────

def available_orders(city: str | None = None, limit: int = 25) -> list[dict]:
    """Fetch orders available for carrier pickup in the configured service area."""
    params: dict = {"limit": limit}
    if city:
        params["city"] = city
    try:
        data = _get("/orders/available", params)
        orders = data if isinstance(data, list) else data.get("orders") or data.get("data") or []
        log_agent(_NAME, "available_orders", result=f"{len(orders)} orders")
        return orders
    except httpx.HTTPStatusError as e:
        log_agent(_NAME, "available_orders_error", error=f"{e.response.status_code}: {e.response.text[:200]}")
        return []
    except Exception as e:  # noqa: BLE001
        log_agent(_NAME, "available_orders_error", error=str(e)[:200])
        return []


def accept_order(order_id: str, driver_id: str | None = None) -> dict[str, Any]:
    """Accept an available order and assign it to a driver."""
    body: dict = {}
    if driver_id:
        body["driver_id"] = driver_id
    try:
        result = _post(f"/orders/{order_id}/accept", body)
        log_agent(_NAME, "accept_order", payload={"order_id": order_id}, result="accepted")
        return {"accepted": True, "order": result}
    except httpx.HTTPStatusError as e:
        return {"accepted": False, "error": f"{e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:  # noqa: BLE001
        return {"accepted": False, "error": str(e)[:200]}


def reject_order(order_id: str, reason: str = "no_capacity") -> dict[str, Any]:
    """Decline an available order."""
    try:
        result = _post(f"/orders/{order_id}/reject", {"reason": reason})
        log_agent(_NAME, "reject_order", payload={"order_id": order_id, "reason": reason})
        return {"rejected": True, "order": result}
    except Exception as e:  # noqa: BLE001
        return {"rejected": False, "error": str(e)[:200]}


def get_order(order_id: str) -> dict[str, Any]:
    """Fetch full order detail."""
    try:
        return _get(f"/orders/{order_id}")
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def update_status(order_id: str, status: str, location: dict | None = None) -> dict[str, Any]:
    """
    Update trip status.
    status: 'en_route_pickup' | 'arrived_pickup' | 'picked_up' | 'en_route_delivery' | 'delivered'
    location: {'lat': float, 'lng': float}  (optional)
    """
    body: dict = {"status": status}
    if location:
        body["location"] = location
    try:
        result = _post(f"/orders/{order_id}/status", body)
        log_agent(_NAME, "update_status", payload={"order_id": order_id, "status": status})
        return {"updated": True, "result": result}
    except Exception as e:  # noqa: BLE001
        return {"updated": False, "error": str(e)[:200]}


def register_webhook(url: str, events: list[str] | None = None) -> dict[str, Any]:
    """Register a webhook endpoint to receive Curri order events."""
    body = {
        "url": url,
        "events": events or [
            "order.available",
            "order.accepted",
            "order.status_updated",
            "order.completed",
            "order.cancelled",
        ],
    }
    try:
        result = _post("/webhooks", body)
        log_agent(_NAME, "register_webhook", payload={"url": url})
        return {"registered": True, "webhook": result}
    except Exception as e:  # noqa: BLE001
        return {"registered": False, "error": str(e)[:200]}


def register_driver(
    driver_id: str,
    name: str,
    email: str,
    phone: str,
    vehicle_type: str = "sedan",
) -> dict[str, Any]:
    """
    Register a driver in the 3 Lakes Curri carrier fleet.

    Curri operates at the carrier level — 3 Lakes accepts orders and dispatches to
    sub-drivers. This call adds the driver to our Curri fleet roster so they can be
    assigned Curri orders through the Eagle Eye dispatch console.

    If Curri's API doesn't expose a /fleet/drivers endpoint for your tier, the driver
    is tagged fleet_eligible in our DB and assigned Curri jobs via our carrier account.
    """
    body: dict = {
        "external_driver_id": driver_id,
        "name": name,
        "email": email,
        "phone": phone,
        "vehicle_type": vehicle_type,
    }
    try:
        result = _post("/fleet/drivers", body)
        curri_driver_id = result.get("id") if isinstance(result, dict) else None
        log_agent(_NAME, "register_driver", payload={"driver_id": driver_id}, result=str(curri_driver_id))
        return {"registered": True, "curri_driver_id": curri_driver_id, "driver": result}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            # Carrier tier doesn't expose fleet roster — driver is still eligible via our account
            log_agent(_NAME, "register_driver", payload={"driver_id": driver_id}, result="fleet_eligible_only")
            return {"registered": True, "curri_driver_id": None, "note": "fleet_eligible"}
        return {"registered": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except RuntimeError as e:
        return {"registered": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"registered": False, "error": str(e)[:200]}


def ping() -> dict[str, Any]:
    """Test the API connection. Returns True if credentials are valid."""
    try:
        _get("/orders/available", {"limit": 1})
        return {"connected": True, "platform": "curri"}
    except RuntimeError as e:
        return {"connected": False, "platform": "curri", "error": str(e)}
    except httpx.HTTPStatusError as e:
        return {"connected": False, "platform": "curri", "error": f"HTTP {e.response.status_code}"}
    except Exception as e:  # noqa: BLE001
        return {"connected": False, "platform": "curri", "error": str(e)[:200]}
