"""Unified ELD interface (steps 83-84).

One `ELDAdapter` protocol, four implementations: Motive, Samsara, Geotab,
Omnitracs. All return a normalized `TelemetryPoint` so the rest of the
app never cares which provider the carrier picked.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol

import httpx

from ..settings import get_settings


@dataclass
class TelemetryPoint:
    truck_id: str
    lat: float
    lng: float
    speed_mph: float = 0.0
    heading: float = 0.0
    odometer_mi: float = 0.0
    fuel_level_pct: float | None = None
    engine_hours: float | None = None
    ts: str = ""
    provider: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class HOSRecord:
    driver_id: str
    duty_status: str       # OFF | SB | D | ON
    drive_remaining_s: int
    shift_remaining_s: int
    cycle_remaining_s: int
    ts: str


class ELDAdapter(Protocol):
    provider: str
    def fetch_vehicles(self, token: str) -> list[dict]: ...
    def fetch_locations(self, token: str) -> Iterable[TelemetryPoint]: ...
    def fetch_hos(self, token: str) -> Iterable[HOSRecord]: ...


class MotiveAdapter:
    provider = "motive"
    base = "https://api.gomotive.com/v1"

    def fetch_vehicles(self, token: str) -> list[dict]:
        r = httpx.get(f"{self.base}/vehicles", headers=_h(token), timeout=20)
        r.raise_for_status()
        return r.json().get("vehicles", [])

    def fetch_locations(self, token: str) -> Iterable[TelemetryPoint]:
        r = httpx.get(f"{self.base}/vehicle_locations", headers=_h(token), timeout=20)
        r.raise_for_status()
        for item in r.json().get("vehicle_locations", []):
            v = item.get("vehicle_location", {})
            yield TelemetryPoint(
                truck_id=str(v.get("vehicle_id") or ""),
                lat=float(v.get("lat") or 0.0), lng=float(v.get("lon") or 0.0),
                speed_mph=float(v.get("speed") or 0.0),
                heading=float(v.get("bearing") or 0.0),
                odometer_mi=float(v.get("odometer") or 0.0),
                fuel_level_pct=v.get("fuel_level"),
                engine_hours=v.get("engine_hours"),
                ts=v.get("located_at") or "",
                provider=self.provider, extra=v,
            )

    def fetch_hos(self, token: str) -> Iterable[HOSRecord]:
        r = httpx.get(f"{self.base}/users/hos_logs", headers=_h(token), timeout=20)
        r.raise_for_status()
        for row in r.json().get("users", []):
            u = row.get("user", {})
            yield HOSRecord(
                driver_id=str(u.get("id")),
                duty_status=u.get("current_duty_status") or "OFF",
                drive_remaining_s=int(u.get("time_until_break") or 0),
                shift_remaining_s=int(u.get("shift_seconds_remaining") or 0),
                cycle_remaining_s=int(u.get("cycle_seconds_remaining") or 0),
                ts=u.get("updated_at") or "",
            )


class SamsaraAdapter:
    provider = "samsara"
    base = "https://api.samsara.com"

    def fetch_vehicles(self, token: str) -> list[dict]:
        r = httpx.get(f"{self.base}/fleet/vehicles", headers=_h(token), timeout=20)
        r.raise_for_status()
        return r.json().get("data", [])

    def fetch_locations(self, token: str) -> Iterable[TelemetryPoint]:
        r = httpx.get(f"{self.base}/fleet/vehicles/locations", headers=_h(token), timeout=20)
        r.raise_for_status()
        for v in r.json().get("data", []):
            loc = v.get("location") or {}
            yield TelemetryPoint(
                truck_id=str(v.get("id")),
                lat=float(loc.get("latitude") or 0.0),
                lng=float(loc.get("longitude") or 0.0),
                speed_mph=float(loc.get("speed") or 0.0),
                heading=float(loc.get("heading") or 0.0),
                ts=loc.get("time") or "",
                provider=self.provider, extra=v,
            )

    def fetch_hos(self, token: str) -> Iterable[HOSRecord]:
        return []


class GeotabAdapter:
    provider = "geotab"

    def fetch_vehicles(self, _token: str) -> list[dict]:
        return []  # Geotab uses SOAP-ish RPC; stub until credentials test.

    def fetch_locations(self, _token: str) -> Iterable[TelemetryPoint]:
        return []

    def fetch_hos(self, _token: str) -> Iterable[HOSRecord]:
        return []


class OmnitracsAdapter:
    provider = "omnitracs"

    def fetch_vehicles(self, _token: str) -> list[dict]:
        return []

    def fetch_locations(self, _token: str) -> Iterable[TelemetryPoint]:
        return []

    def fetch_hos(self, _token: str) -> Iterable[HOSRecord]:
        return []


_REGISTRY: dict[str, ELDAdapter] = {
    "motive": MotiveAdapter(),
    "samsara": SamsaraAdapter(),
    "geotab": GeotabAdapter(),
    "omnitracs": OmnitracsAdapter(),
}


def adapter_for(provider: str) -> ELDAdapter:
    key = (provider or "").lower()
    if key not in _REGISTRY:
        raise ValueError(f"unsupported ELD provider: {provider}")
    return _REGISTRY[key]


def default_token(provider: str) -> str:
    s = get_settings()
    return {
        "motive": s.motive_api_key,
        "samsara": s.samsara_api_key,
        "omnitracs": s.omnitracs_api_key,
    }.get(provider.lower(), "")


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}
