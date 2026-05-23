"""Base broker connector — abstract class + poll-all orchestrator."""
from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from typing import Any

from ...logging_service import get_logger
from ...supabase_client import get_supabase

log = get_logger("3ll.integrations.brokers")


class BrokerConnector(ABC):
    """Base class for all REST broker connectors."""

    def __init__(self, broker_row: dict) -> None:
        self.broker_id      = broker_row["id"]
        self.broker_mc      = broker_row["mc_number"]
        self.company_name   = broker_row["company_name"]
        self.rest_endpoint  = broker_row.get("rest_endpoint") or ""
        self._api_key       = self._decrypt_key(broker_row.get("rest_api_key_enc"))

    @staticmethod
    def _decrypt_key(enc: str | None) -> str:
        """Decode base64 API key stored in DB."""
        if not enc:
            return ""
        try:
            return base64.b64decode(enc.encode()).decode()
        except Exception:
            return ""

    @abstractmethod
    def fetch_available_loads(self) -> list[dict[str, Any]]:
        """Return list of normalized load dicts from the broker's API."""
        ...

    def normalize(self, raw_load: dict[str, Any]) -> dict[str, Any]:
        """Subclasses override to map broker-specific fields to 3LL schema."""
        return raw_load

    def sync(self) -> dict[str, Any]:
        """Fetch loads, create contracts, fire CLM workflow. Returns summary."""
        from ...triggers import fire_clm_workflow
        sb = get_supabase()
        created, skipped, errors = 0, 0, 0

        try:
            loads = self.fetch_available_loads()
        except Exception as exc:
            log.error("broker_connector broker=%s fetch_failed: %s", self.broker_mc, exc)
            return {"broker_mc": self.broker_mc, "created": 0, "errors": 1, "message": str(exc)}

        for raw in loads:
            try:
                norm = self.normalize(raw)
                load_num = norm.get("load_number") or norm.get("external_load_id")
                if not load_num:
                    skipped += 1
                    continue

                # Skip if already exists
                exists = sb.table("contracts").select("id").eq("load_number", load_num).maybe_single().execute()
                if exists.data:
                    skipped += 1
                    continue

                contract_row = {
                    "contract_type":    "rate_confirmation",
                    "status":           "extracted",
                    "source":           f"rest_{self.broker_mc.lower().replace(' ', '_')}",
                    "counterparty_name": self.company_name,
                    "load_number":      load_num,
                    "extracted_vars":   norm,
                    "rate_total":       norm.get("rate_total"),
                    "confidence_score": 0.90,
                    "auto_approved":    False,
                    "flagged_for_review": False,
                    "milestone_pct":    0,
                    "gl_posted":        False,
                    "origin_city":      norm.get("origin_city"),
                    "destination_city": norm.get("destination_city"),
                }
                res = sb.table("contracts").insert(contract_row).execute()
                contract_id = res.data[0]["id"]
                fire_clm_workflow(contract_id)
                created += 1
                log.info("broker_rest_sync load=%s contract=%s broker=%s", load_num, contract_id, self.broker_mc)

            except Exception as exc:
                log.error("broker_rest_sync load_error broker=%s: %s", self.broker_mc, exc)
                errors += 1

        return {"broker_mc": self.broker_mc, "created": created, "skipped": skipped, "errors": errors}


def poll_all_rest_brokers() -> list[dict[str, Any]]:
    """Poll every active REST-type broker and sync available loads.

    Called by the APScheduler cron (wired in main.py).
    """
    from .uber_freight import UberFreightConnector

    sb = get_supabase()
    brokers = sb.table("brokers").select("*").eq("status", "active").eq("api_type", "rest").execute()
    if not brokers.data:
        return []

    results = []
    for row in brokers.data:
        try:
            connector = _build_connector(row)
            if connector:
                result = connector.sync()
                results.append(result)
        except Exception as exc:
            log.error("poll_all_rest_brokers broker=%s: %s", row.get("mc_number"), exc)
            results.append({"broker_mc": row.get("mc_number"), "error": str(exc)})

    return results


def _build_connector(row: dict) -> BrokerConnector | None:
    """Factory — pick the right connector class based on company or endpoint."""
    from .uber_freight import UberFreightConnector

    endpoint = (row.get("rest_endpoint") or "").lower()
    name     = (row.get("company_name") or "").lower()

    if "uber" in name or "uberfreight" in endpoint:
        return UberFreightConnector(row)

    # Default generic connector for unknown REST brokers
    return GenericRESTConnector(row)


class GenericRESTConnector(BrokerConnector):
    """Fallback connector — calls broker's endpoint expecting a JSON array of loads."""

    def fetch_available_loads(self) -> list[dict]:
        import urllib.request, json
        if not self.rest_endpoint:
            return []
        req = urllib.request.Request(
            self.rest_endpoint,
            headers={"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("loads") or data.get("data") or data.get("results") or []
        return []

    def normalize(self, raw: dict) -> dict:
        return {
            "external_load_id":  raw.get("id") or raw.get("load_id") or raw.get("loadId"),
            "load_number":       raw.get("load_number") or raw.get("loadNumber") or raw.get("referenceNumber"),
            "broker_mc":         self.broker_mc,
            "origin_city":       raw.get("origin_city") or raw.get("originCity"),
            "origin_state":      raw.get("origin_state") or raw.get("originState"),
            "destination_city":  raw.get("destination_city") or raw.get("destCity"),
            "destination_state": raw.get("destination_state") or raw.get("destState"),
            "pickup_date":       raw.get("pickup_date") or raw.get("pickupDate"),
            "delivery_date":     raw.get("delivery_date") or raw.get("deliveryDate"),
            "rate_total":        raw.get("rate") or raw.get("total_rate") or raw.get("totalRate"),
            "equipment_type":    raw.get("equipment_type") or raw.get("equipmentType"),
            "weight_lbs":        raw.get("weight") or raw.get("weight_lbs"),
            "commodity":         raw.get("commodity"),
        }
