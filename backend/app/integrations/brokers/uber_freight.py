"""Uber Freight REST connector.

Uber Freight Carrier API:
  - Auth: Bearer token (OAuth2 client credentials)
  - Load search: GET /v1/loads/available
  - Load accept: POST /v1/loads/{load_id}/book
  - Status update: POST /v1/loads/{load_id}/status

Docs: https://developer.uberfreight.com/
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ...logging_service import get_logger
from .base import BrokerConnector

log = get_logger("3ll.integrations.uber_freight")

_UF_BASE = "https://api.uberfreight.com"
_UF_MC   = "UF_BROKER"   # Placeholder — Uber Freight's actual MC number


class UberFreightConnector(BrokerConnector):
    """Connector for Uber Freight carrier API."""

    def __init__(self, broker_row: dict) -> None:
        super().__init__(broker_row)
        self._token: str | None = None

    def _auth_token(self) -> str:
        """Get OAuth2 Bearer token from Uber Freight."""
        if self._token:
            return self._token
        if not self._api_key:
            raise ValueError("Uber Freight API key not configured for this broker")

        # Uber Freight uses client_credentials grant
        # api_key is expected to be stored as "client_id:client_secret"
        parts = self._api_key.split(":", 1)
        client_id     = parts[0]
        client_secret = parts[1] if len(parts) > 1 else ""

        data = urllib.parse.urlencode({
            "grant_type":    "client_credentials",
            "client_id":     client_id,
            "client_secret": client_secret,
        }).encode()

        req = urllib.request.Request(
            f"{self._endpoint('/v1/oauth/token')}",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode())
        self._token = body.get("access_token", "")
        return self._token

    def _endpoint(self, path: str) -> str:
        base = self.rest_endpoint.rstrip("/") if self.rest_endpoint else _UF_BASE
        return f"{base}{path}"

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = self._endpoint(path)
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self._auth_token()}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

    def _post(self, path: str, body: dict) -> Any:
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            self._endpoint(path),
            data=data,
            headers={
                "Authorization": f"Bearer {self._auth_token()}",
                "Content-Type":  "application/json",
                "Accept":        "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

    def fetch_available_loads(self) -> list[dict[str, Any]]:
        """Fetch loads available to 3LL from Uber Freight."""
        try:
            resp = self._get("/v1/loads/available", {"limit": 50, "status": "available"})
            loads = resp.get("loads") or resp.get("data") or []
            log.info("uf_fetch broker=%s loads=%d", self.broker_mc, len(loads))
            return loads
        except urllib.error.URLError as exc:
            log.warning("uf_fetch failed broker=%s: %s", self.broker_mc, exc)
            return []

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Map Uber Freight load fields to 3LL schema."""
        origin      = raw.get("origin") or {}
        destination = raw.get("destination") or {}
        price       = raw.get("price") or {}

        return {
            "external_load_id":  raw.get("id") or raw.get("loadId"),
            "load_number":       raw.get("referenceNumber") or raw.get("id"),
            "broker_mc":         _UF_MC,
            "origin_city":       origin.get("city"),
            "origin_state":      origin.get("state"),
            "origin_zip":        origin.get("zip"),
            "destination_city":  destination.get("city"),
            "destination_state": destination.get("state"),
            "destination_zip":   destination.get("zip"),
            "pickup_date":       raw.get("pickupDate") or raw.get("pickup_date"),
            "delivery_date":     raw.get("deliveryDate") or raw.get("delivery_date"),
            "rate_total":        price.get("amount") or price.get("total") or raw.get("rate"),
            "equipment_type":    raw.get("equipmentType") or raw.get("equipment_type"),
            "weight_lbs":        raw.get("weightLbs") or raw.get("weight"),
            "commodity":         raw.get("commodity") or raw.get("commodityDescription"),
            "payment_terms":     "QuickPay",  # Uber Freight defaults to QuickPay
            "source_platform":   "uber_freight",
        }

    def accept_load(self, external_load_id: str) -> dict[str, Any]:
        """Book a load on Uber Freight."""
        try:
            return self._post(f"/v1/loads/{external_load_id}/book", {})
        except Exception as exc:
            log.error("uf_accept load=%s: %s", external_load_id, exc)
            return {"error": str(exc)}

    def send_status(self, external_load_id: str, status_code: str,
                    city: str | None = None, state: str | None = None) -> dict[str, Any]:
        """Post a shipment status update to Uber Freight."""
        body: dict[str, Any] = {"statusCode": status_code}
        if city:
            body["location"] = {"city": city, "state": state}
        try:
            return self._post(f"/v1/loads/{external_load_id}/status", body)
        except Exception as exc:
            log.error("uf_status load=%s: %s", external_load_id, exc)
            return {"error": str(exc)}
