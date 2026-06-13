"""Load board API clients — all 15 sources used by Sonny (Steps 23-24).

Each client exposes a `search_loads(params: SearchParams) -> list[LoadResult]`
method. Authentication (OAuth2 token refresh, API key headers, Basic auth) is
handled transparently per-source.  Clients are stateless; token caches are
module-level so tokens survive across calls within a single process lifetime.

Sources:
  1.  DAT               — developer.dat.com       (OAuth2 client-credentials)
  2.  Truckstop         — developer.truckstop.com (Basic / Partner ID)
  3.  123Loadboard      — 123loadboard.com/api/   (API key)
  4.  Trucker Path      — docs.truckerpath.com    (API key)
  5.  Direct Freight    — apidocs.directfreight.com (username/password)
  6.  Uber Freight      — developer.uberfreight.com (OAuth2)
  7.  Loadsmart         — developer.loadsmart.com  (API key)
  8.  NewTrul           — newtrul.com/api          (API key)
  9.  Flock Freight     — flockfreight.com         (API key)
  10. J.B. Hunt 360     — developer.jbhunt.com     (OAuth2)
  11. Coyote GO (RXO)   — api.coyote.com           (OAuth2)
  12. Arrive Logistics  — developer.arrive.com/v4  (OAuth2)
  13. Echo Global       — EchoSync REST            (API key)
  14. Cargo Chief       — cargochief.com           (API key)
  15. Convoy / DAT      — rolled into DAT post-2025 acquisition
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..logging_service import get_logger
from ..settings import get_settings

log = get_logger("sonny.loadboards")

_TIMEOUT = httpx.Timeout(15.0)
_RETRY_CODES = {429, 500, 502, 503, 504}


@dataclass
class SearchParams:
    origin_state: str
    trailer_type: str           # "dry_van" | "reefer" | "flatbed" | "cargo_van" | ...
    origin_city: str = ""       # optional city filter (e.g. "Portland")
    origin_zip: str = ""        # optional ZIP for deadhead center (e.g. "97201")
    max_weight_lbs: int = 45000
    max_deadhead_mi: int = 150
    min_rate_per_mile: float = 2.10
    hos_hours_remaining: float = 11.0


@dataclass
class LoadResult:
    source: str
    load_id: str
    broker_name: str
    origin_city: str
    origin_state: str
    dest_city: str
    dest_state: str
    miles: int | None
    rate_total: float | None
    rate_per_mile: float | None
    weight_lbs: int | None
    trailer_type: str
    pickup_date: str | None     # ISO date string
    raw: dict = field(default_factory=dict, repr=False)


# ── Token cache ──────────────────────────────────────────────────────────────

class _TokenCache:
    def __init__(self):
        self._token: str | None = None
        self._expires_at: float = 0.0

    def valid(self) -> bool:
        return bool(self._token) and time.time() < self._expires_at - 60

    def set(self, token: str, expires_in: int) -> None:
        self._token = token
        self._expires_at = time.time() + expires_in

    @property
    def token(self) -> str | None:
        return self._token


# ── Shared HTTP helpers ───────────────────────────────────────────────────────

def _get(url: str, *, headers: dict, params: dict | None = None) -> dict | list | None:
    try:
        r = httpx.get(url, headers=headers, params=params, timeout=_TIMEOUT)
        if r.status_code in _RETRY_CODES:
            log.warning("loadboard GET %s status=%s", url, r.status_code)
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001
        log.warning("loadboard GET %s error: %s", url, e)
        return None


def _post(url: str, *, headers: dict, json: dict) -> dict | list | None:
    try:
        r = httpx.post(url, headers=headers, json=json, timeout=_TIMEOUT)
        if r.status_code in _RETRY_CODES:
            log.warning("loadboard POST %s status=%s", url, r.status_code)
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001
        log.warning("loadboard POST %s error: %s", url, e)
        return None


def _fetch_oauth2_token(token_url: str, client_id: str, client_secret: str,
                        scope: str = "") -> tuple[str | None, int]:
    try:
        data: dict[str, str] = {"grant_type": "client_credentials",
                                 "client_id": client_id,
                                 "client_secret": client_secret}
        if scope:
            data["scope"] = scope
        r = httpx.post(token_url, data=data, timeout=_TIMEOUT)
        r.raise_for_status()
        body = r.json()
        return body.get("access_token"), int(body.get("expires_in", 3600))
    except Exception as e:  # noqa: BLE001
        log.warning("oauth2 token fetch %s error: %s", token_url, e)
        return None, 0


# ─────────────────────────────────────────────────────────────────────────────
# 1. DAT  (+ Convoy loads — DAT acquired Convoy platform July 2025)
# ─────────────────────────────────────────────────────────────────────────────

_dat_cache = _TokenCache()


def _dat_token() -> str | None:
    if _dat_cache.valid():
        return _dat_cache.token
    s = get_settings()
    if not s.dat_client_id or not s.dat_client_secret:
        return None
    tok, exp = _fetch_oauth2_token(
        "https://identity.dat.com/access/v1/token/client",
        s.dat_client_id, s.dat_client_secret,
        scope="freight/read")
    if tok:
        _dat_cache.set(tok, exp)
    return tok


def dat_search(p: SearchParams) -> list[LoadResult]:
    tok = _dat_token()
    if not tok:
        return []
    headers = {"Authorization": f"Bearer {tok}", "Accept": "application/json"}
    body = _post("https://freight.api.dat.com/search/v3/loads", headers=headers, json={
        "origin": {"stateProv": p.origin_state},
        "equipment": {"trailerTypes": [p.trailer_type.upper()]},
        "maxDeadheadMiles": p.max_deadhead_mi,
        "limit": 50,
    })
    if not body:
        return []
    return [_dat_map(l) for l in (body.get("results") or [])]


def _dat_map(l: dict) -> LoadResult:
    rate = l.get("rateInfo") or {}
    origin = l.get("origin") or {}
    dest = l.get("destination") or {}
    return LoadResult(
        source="dat",
        load_id=str(l.get("id", "")),
        broker_name=l.get("company", {}).get("name", ""),
        origin_city=origin.get("city", ""),
        origin_state=origin.get("stateProv", ""),
        dest_city=dest.get("city", ""),
        dest_state=dest.get("stateProv", ""),
        miles=l.get("computedMiles"),
        rate_total=rate.get("amount"),
        rate_per_mile=rate.get("ratePerMile"),
        weight_lbs=l.get("loadWeight"),
        trailer_type=l.get("equipment", {}).get("trailerType", ""),
        pickup_date=l.get("earliestPickupDate"),
        raw=l,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Truckstop
# ─────────────────────────────────────────────────────────────────────────────

def truckstop_search(p: SearchParams) -> list[LoadResult]:
    s = get_settings()
    if not s.truckstop_username or not s.truckstop_password:
        return []
    import base64
    creds = base64.b64encode(f"{s.truckstop_username}:{s.truckstop_password}".encode()).decode()
    headers = {
        "Authorization": f"Basic {creds}",
        "X-Partner-ID": s.truckstop_partner_id,
        "Content-Type": "application/json",
    }
    body = _post("https://api.truckstop.com/v1/loads/search", headers=headers, json={
        "origin": {"state": p.origin_state},
        "equipment": p.trailer_type,
        "maxDeadheadMiles": p.max_deadhead_mi,
        "pageSize": 50,
    })
    if not body:
        return []
    return [_ts_map(l) for l in (body.get("loads") or [])]


def _ts_map(l: dict) -> LoadResult:
    return LoadResult(
        source="truckstop",
        load_id=str(l.get("loadId", "")),
        broker_name=l.get("postedByCompany", ""),
        origin_city=l.get("originCity", ""),
        origin_state=l.get("originState", ""),
        dest_city=l.get("destinationCity", ""),
        dest_state=l.get("destinationState", ""),
        miles=l.get("miles"),
        rate_total=l.get("rateTotal"),
        rate_per_mile=l.get("ratePerMile"),
        weight_lbs=l.get("weight"),
        trailer_type=l.get("equipment", ""),
        pickup_date=l.get("pickupDate"),
        raw=l,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. 123Loadboard
# ─────────────────────────────────────────────────────────────────────────────

def loadboard123_search(p: SearchParams) -> list[LoadResult]:
    s = get_settings()
    if not s.loadboard_123_api_key:
        return []
    headers = {"X-API-Key": s.loadboard_123_api_key, "Accept": "application/json"}
    params: dict = {
        "originState": p.origin_state,
        "equipType": p.trailer_type or "cargo_van",
        "maxDeadhead": p.max_deadhead_mi,
        "limit": 50,
    }
    if p.origin_city:
        params["originCity"] = p.origin_city
    if p.origin_zip:
        params["originZip"] = p.origin_zip
    body = _get("https://api.123loadboard.com/v3/loads", headers=headers, params=params)
    if not body:
        return []
    loads = body if isinstance(body, list) else (body.get("loads") or [])
    return [_123_map(l) for l in loads]


def _123_map(l: dict) -> LoadResult:
    return LoadResult(
        source="123loadboard",
        load_id=str(l.get("id", l.get("loadId", ""))),
        broker_name=l.get("company", l.get("companyName", "")),
        origin_city=l.get("originCity", ""),
        origin_state=l.get("originState", ""),
        dest_city=l.get("destCity", l.get("destinationCity", "")),
        dest_state=l.get("destState", l.get("destinationState", "")),
        miles=l.get("miles"),
        rate_total=l.get("rate"),
        rate_per_mile=l.get("ratePerMile"),
        weight_lbs=l.get("weight"),
        trailer_type=l.get("equipType", ""),
        pickup_date=l.get("pickupDate"),
        raw=l,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Trucker Path
# ─────────────────────────────────────────────────────────────────────────────

def truckerpath_search(p: SearchParams) -> list[LoadResult]:
    s = get_settings()
    if not s.truckerpath_api_key:
        return []
    headers = {"Authorization": f"Bearer {s.truckerpath_api_key}", "Accept": "application/json"}
    body = _post("https://api.truckerpath.com/truckloads/v1/search", headers=headers, json={
        "origin": {"state": p.origin_state},
        "trailerType": p.trailer_type,
        "maxDeadheadMiles": p.max_deadhead_mi,
        "count": 50,
    })
    if not body:
        return []
    return [_tp_map(l) for l in (body.get("loads") or [])]


def _tp_map(l: dict) -> LoadResult:
    o = l.get("origin") or {}
    d = l.get("destination") or {}
    return LoadResult(
        source="truckerpath",
        load_id=str(l.get("loadId", "")),
        broker_name=l.get("postedBy", ""),
        origin_city=o.get("city", ""),
        origin_state=o.get("state", ""),
        dest_city=d.get("city", ""),
        dest_state=d.get("state", ""),
        miles=l.get("miles"),
        rate_total=l.get("rate"),
        rate_per_mile=l.get("ratePerMile"),
        weight_lbs=l.get("weight"),
        trailer_type=l.get("trailerType", ""),
        pickup_date=l.get("pickupDate"),
        raw=l,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Direct Freight
# ─────────────────────────────────────────────────────────────────────────────

_df_token_cache: dict[str, Any] = {"token": None, "expires_at": 0.0}


def _df_token() -> str | None:
    s = get_settings()
    if not s.direct_freight_username or not s.direct_freight_password:
        return None
    if _df_token_cache["token"] and time.time() < _df_token_cache["expires_at"] - 60:
        return _df_token_cache["token"]
    r = _post("https://api.directfreight.com/v1/auth/token", headers={}, json={
        "username": s.direct_freight_username,
        "password": s.direct_freight_password,
    })
    if r and r.get("token"):
        _df_token_cache["token"] = r["token"]
        _df_token_cache["expires_at"] = time.time() + int(r.get("expiresIn", 3600))
        return r["token"]
    return None


def direct_freight_search(p: SearchParams) -> list[LoadResult]:
    tok = _df_token()
    if not tok:
        return []
    headers = {"Authorization": f"Bearer {tok}", "Accept": "application/json"}
    body = _get("https://api.directfreight.com/v1/loads", headers=headers, params={
        "originState": p.origin_state,
        "equipmentType": p.trailer_type,
        "maxDeadhead": p.max_deadhead_mi,
        "limit": 50,
    })
    if not body:
        return []
    loads = body if isinstance(body, list) else (body.get("loads") or [])
    return [_df_map(l) for l in loads]


def _df_map(l: dict) -> LoadResult:
    return LoadResult(
        source="direct_freight",
        load_id=str(l.get("loadId", l.get("id", ""))),
        broker_name=l.get("company", ""),
        origin_city=l.get("originCity", ""),
        origin_state=l.get("originState", ""),
        dest_city=l.get("destCity", ""),
        dest_state=l.get("destState", ""),
        miles=l.get("miles"),
        rate_total=l.get("rate"),
        rate_per_mile=l.get("ratePerMile"),
        weight_lbs=l.get("weight"),
        trailer_type=l.get("equipType", ""),
        pickup_date=l.get("pickupDate"),
        raw=l,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Uber Freight
# ─────────────────────────────────────────────────────────────────────────────

_uf_cache = _TokenCache()


def _uf_token() -> str | None:
    if _uf_cache.valid():
        return _uf_cache.token
    s = get_settings()
    if not s.uber_freight_client_id or not s.uber_freight_client_secret:
        return None
    tok, exp = _fetch_oauth2_token(
        "https://login.uberfreight.com/oauth/token",
        s.uber_freight_client_id, s.uber_freight_client_secret,
        scope="loads.read")
    if tok:
        _uf_cache.set(tok, exp)
    return tok


def uber_freight_search(p: SearchParams) -> list[LoadResult]:
    tok = _uf_token()
    if not tok:
        return []
    headers = {"Authorization": f"Bearer {tok}", "Accept": "application/json"}
    body = _post("https://api.uberfreight.com/v1/carrier/loads/search", headers=headers, json={
        "originState": p.origin_state,
        "equipmentType": p.trailer_type,
        "maxDeadheadMiles": p.max_deadhead_mi,
        "limit": 50,
    })
    if not body:
        return []
    return [_uf_map(l) for l in (body.get("loads") or [])]


def _uf_map(l: dict) -> LoadResult:
    o = l.get("origin") or {}
    d = l.get("destination") or {}
    r = l.get("rate") or {}
    return LoadResult(
        source="uber_freight",
        load_id=str(l.get("loadId", "")),
        broker_name="Uber Freight",
        origin_city=o.get("city", ""),
        origin_state=o.get("state", ""),
        dest_city=d.get("city", ""),
        dest_state=d.get("state", ""),
        miles=l.get("miles"),
        rate_total=r.get("total"),
        rate_per_mile=r.get("perMile"),
        weight_lbs=l.get("weight"),
        trailer_type=l.get("equipmentType", ""),
        pickup_date=l.get("pickupDate"),
        raw=l,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. Loadsmart
# ─────────────────────────────────────────────────────────────────────────────

def loadsmart_search(p: SearchParams) -> list[LoadResult]:
    s = get_settings()
    if not s.loadsmart_api_key:
        return []
    headers = {"Authorization": f"ApiKey {s.loadsmart_api_key}", "Accept": "application/json"}
    body = _post("https://api.loadsmart.com/v1/loads/search", headers=headers, json={
        "pickup": {"state": p.origin_state},
        "equipment": p.trailer_type,
        "max_deadhead": p.max_deadhead_mi,
        "limit": 50,
    })
    if not body:
        return []
    return [_ls_map(l) for l in (body.get("results") or body if isinstance(body, list) else [])]


def _ls_map(l: dict) -> LoadResult:
    pickup = l.get("pickup") or {}
    dropoff = l.get("dropoff") or {}
    return LoadResult(
        source="loadsmart",
        load_id=str(l.get("guid", l.get("id", ""))),
        broker_name="Loadsmart",
        origin_city=pickup.get("city", ""),
        origin_state=pickup.get("state", ""),
        dest_city=dropoff.get("city", ""),
        dest_state=dropoff.get("state", ""),
        miles=l.get("miles"),
        rate_total=l.get("price"),
        rate_per_mile=None,
        weight_lbs=l.get("weight"),
        trailer_type=l.get("equipment", ""),
        pickup_date=(pickup.get("date") or "")[:10] or None,
        raw=l,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 8. NewTrul (acquired by Highway, 2024)
# ─────────────────────────────────────────────────────────────────────────────

def newtrul_search(p: SearchParams) -> list[LoadResult]:
    s = get_settings()
    if not s.newtrul_api_key:
        return []
    headers = {"X-API-Key": s.newtrul_api_key, "Accept": "application/json"}
    body = _get("https://api.newtrul.com/v1/loads", headers=headers, params={
        "originState": p.origin_state,
        "equipmentType": p.trailer_type,
        "maxDeadhead": p.max_deadhead_mi,
        "limit": 50,
    })
    if not body:
        return []
    loads = body if isinstance(body, list) else (body.get("loads") or [])
    return [_nt_map(l) for l in loads]


def _nt_map(l: dict) -> LoadResult:
    return LoadResult(
        source="newtrul",
        load_id=str(l.get("id", "")),
        broker_name=l.get("broker", l.get("company", "")),
        origin_city=l.get("originCity", ""),
        origin_state=l.get("originState", ""),
        dest_city=l.get("destCity", ""),
        dest_state=l.get("destState", ""),
        miles=l.get("miles"),
        rate_total=l.get("rate"),
        rate_per_mile=l.get("ratePerMile"),
        weight_lbs=l.get("weight"),
        trailer_type=l.get("equipmentType", ""),
        pickup_date=l.get("pickupDate"),
        raw=l,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 9. Flock Freight
# ─────────────────────────────────────────────────────────────────────────────

def flock_freight_search(p: SearchParams) -> list[LoadResult]:
    s = get_settings()
    if not s.flock_freight_api_key:
        return []
    headers = {"X-API-Key": s.flock_freight_api_key, "Accept": "application/json"}
    body = _post("https://api.flockfreight.com/v1/loads/search", headers=headers, json={
        "origin": {"state": p.origin_state},
        "equipmentType": p.trailer_type,
        "maxDeadheadMiles": p.max_deadhead_mi,
        "limit": 50,
    })
    if not body:
        return []
    return [_ff_map(l) for l in (body.get("loads") or [])]


def _ff_map(l: dict) -> LoadResult:
    o = l.get("origin") or {}
    d = l.get("destination") or {}
    return LoadResult(
        source="flock_freight",
        load_id=str(l.get("loadId", "")),
        broker_name="Flock Freight",
        origin_city=o.get("city", ""),
        origin_state=o.get("state", ""),
        dest_city=d.get("city", ""),
        dest_state=d.get("state", ""),
        miles=l.get("miles"),
        rate_total=l.get("rate"),
        rate_per_mile=l.get("ratePerMile"),
        weight_lbs=l.get("weight"),
        trailer_type=l.get("equipmentType", ""),
        pickup_date=l.get("pickupDate"),
        raw=l,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 10. J.B. Hunt 360
# ─────────────────────────────────────────────────────────────────────────────

_jbh_cache = _TokenCache()


def _jbh_token() -> str | None:
    if _jbh_cache.valid():
        return _jbh_cache.token
    s = get_settings()
    if not s.jbhunt_client_id or not s.jbhunt_client_secret:
        return None
    tok, exp = _fetch_oauth2_token(
        "https://api.jbhunt.com/oauth2/token",
        s.jbhunt_client_id, s.jbhunt_client_secret,
        scope="loads.search")
    if tok:
        _jbh_cache.set(tok, exp)
    return tok


def jbhunt_search(p: SearchParams) -> list[LoadResult]:
    tok = _jbh_token()
    if not tok:
        return []
    headers = {"Authorization": f"Bearer {tok}", "Accept": "application/json"}
    body = _post("https://api.jbhunt.com/connect360/v2/loads/search", headers=headers, json={
        "originState": p.origin_state,
        "equipmentType": p.trailer_type,
        "maxDeadheadMiles": p.max_deadhead_mi,
        "pageSize": 50,
    })
    if not body:
        return []
    return [_jbh_map(l) for l in (body.get("loads") or [])]


def _jbh_map(l: dict) -> LoadResult:
    o = l.get("origin") or {}
    d = l.get("destination") or {}
    r = l.get("rate") or {}
    return LoadResult(
        source="j_b_hunt_360",
        load_id=str(l.get("loadNumber", l.get("id", ""))),
        broker_name="J.B. Hunt",
        origin_city=o.get("city", ""),
        origin_state=o.get("state", ""),
        dest_city=d.get("city", ""),
        dest_state=d.get("state", ""),
        miles=l.get("miles"),
        rate_total=r.get("total"),
        rate_per_mile=r.get("perMile"),
        weight_lbs=l.get("weight"),
        trailer_type=l.get("equipmentType", ""),
        pickup_date=l.get("pickupDate"),
        raw=l,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 11. Coyote GO (now RXO)
# ─────────────────────────────────────────────────────────────────────────────

_coyote_cache = _TokenCache()


def _coyote_token() -> str | None:
    if _coyote_cache.valid():
        return _coyote_cache.token
    s = get_settings()
    if not s.coyote_client_id or not s.coyote_client_secret:
        return None
    tok, exp = _fetch_oauth2_token(
        "https://api.coyote.com/oauth/token",
        s.coyote_client_id, s.coyote_client_secret)
    if tok:
        _coyote_cache.set(tok, exp)
    return tok


def coyote_search(p: SearchParams) -> list[LoadResult]:
    tok = _coyote_token()
    if not tok:
        return []
    headers = {"Authorization": f"Bearer {tok}", "Accept": "application/json"}
    body = _post("https://api.coyote.com/v2/loads/search", headers=headers, json={
        "originState": p.origin_state,
        "equipmentType": p.trailer_type,
        "maxDeadheadMiles": p.max_deadhead_mi,
        "pageSize": 50,
    })
    if not body:
        return []
    return [_coyote_map(l) for l in (body.get("loads") or [])]


def _coyote_map(l: dict) -> LoadResult:
    return LoadResult(
        source="coyote_go",
        load_id=str(l.get("loadId", l.get("id", ""))),
        broker_name="Coyote Logistics",
        origin_city=l.get("originCity", ""),
        origin_state=l.get("originState", ""),
        dest_city=l.get("destCity", ""),
        dest_state=l.get("destState", ""),
        miles=l.get("miles"),
        rate_total=l.get("rate"),
        rate_per_mile=l.get("ratePerMile"),
        weight_lbs=l.get("weight"),
        trailer_type=l.get("equipmentType", ""),
        pickup_date=l.get("pickupDate"),
        raw=l,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 12. Arrive Logistics
# ─────────────────────────────────────────────────────────────────────────────

_arrive_cache = _TokenCache()


def _arrive_token() -> str | None:
    if _arrive_cache.valid():
        return _arrive_cache.token
    s = get_settings()
    if not s.arrive_client_id or not s.arrive_client_secret:
        return None
    try:
        r = httpx.post("https://api.arrive.com/oauth/token",
                       json={"grant_type": "client_credentials",
                             "client_id": s.arrive_client_id,
                             "client_secret": s.arrive_client_secret},
                       timeout=_TIMEOUT)
        r.raise_for_status()
        body = r.json()
        tok = body.get("access_token")
        if tok:
            _arrive_cache.set(tok, int(body.get("expires_in", 3600)))
        return tok
    except Exception as e:  # noqa: BLE001
        log.warning("arrive token error: %s", e)
        return None


def arrive_search(p: SearchParams) -> list[LoadResult]:
    tok = _arrive_token()
    if not tok:
        return []
    headers = {"Authorization": f"Bearer {tok}", "Accept": "application/json"}
    body = _get("https://api.arrive.com/v4/loads", headers=headers, params={
        "origin_state": p.origin_state,
        "equipment_type": p.trailer_type,
        "max_deadhead": p.max_deadhead_mi,
        "limit": 50,
    })
    if not body:
        return []
    loads = body if isinstance(body, list) else (body.get("loads") or [])
    return [_arrive_map(l) for l in loads]


def _arrive_map(l: dict) -> LoadResult:
    o = l.get("origin") or {}
    d = l.get("destination") or {}
    return LoadResult(
        source="arrive_logistics",
        load_id=str(l.get("id", l.get("loadId", ""))),
        broker_name="Arrive Logistics",
        origin_city=o.get("city", ""),
        origin_state=o.get("state", ""),
        dest_city=d.get("city", ""),
        dest_state=d.get("state", ""),
        miles=l.get("miles"),
        rate_total=l.get("rate"),
        rate_per_mile=l.get("rate_per_mile"),
        weight_lbs=l.get("weight"),
        trailer_type=l.get("equipment_type", ""),
        pickup_date=l.get("pickup_date"),
        raw=l,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 13. Echo Global (EchoSync)
# ─────────────────────────────────────────────────────────────────────────────

def echo_global_search(p: SearchParams) -> list[LoadResult]:
    s = get_settings()
    if not s.echo_global_api_key:
        return []
    headers = {"X-EchoSync-Key": s.echo_global_api_key, "Accept": "application/json"}
    body = _post("https://echosync.echo.com/api/v2/loads/search", headers=headers, json={
        "origin": {"state": p.origin_state},
        "equipmentType": p.trailer_type,
        "maxDeadheadMiles": p.max_deadhead_mi,
        "pageSize": 50,
    })
    if not body:
        return []
    return [_echo_map(l) for l in (body.get("loads") or [])]


def _echo_map(l: dict) -> LoadResult:
    o = l.get("origin") or {}
    d = l.get("destination") or {}
    r = l.get("rate") or {}
    return LoadResult(
        source="echo_global",
        load_id=str(l.get("loadNumber", l.get("id", ""))),
        broker_name="Echo Global",
        origin_city=o.get("city", ""),
        origin_state=o.get("state", ""),
        dest_city=d.get("city", ""),
        dest_state=d.get("state", ""),
        miles=l.get("miles"),
        rate_total=r.get("total"),
        rate_per_mile=r.get("perMile"),
        weight_lbs=l.get("weight"),
        trailer_type=l.get("equipmentType", ""),
        pickup_date=l.get("pickupDate"),
        raw=l,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 14. Cargo Chief
# ─────────────────────────────────────────────────────────────────────────────

def cargo_chief_search(p: SearchParams) -> list[LoadResult]:
    s = get_settings()
    if not s.cargo_chief_api_key:
        return []
    headers = {"Authorization": f"Bearer {s.cargo_chief_api_key}", "Accept": "application/json"}
    body = _post("https://api.cargochief.com/v1/loads/search", headers=headers, json={
        "origin": {"state": p.origin_state},
        "equipment": p.trailer_type,
        "maxDeadheadMiles": p.max_deadhead_mi,
        "limit": 50,
    })
    if not body:
        return []
    return [_cc_map(l) for l in (body.get("loads") or [])]


def _cc_map(l: dict) -> LoadResult:
    return LoadResult(
        source="cargo_chief",
        load_id=str(l.get("id", "")),
        broker_name=l.get("broker", ""),
        origin_city=l.get("originCity", ""),
        origin_state=l.get("originState", ""),
        dest_city=l.get("destCity", ""),
        dest_state=l.get("destState", ""),
        miles=l.get("miles"),
        rate_total=l.get("rate"),
        rate_per_mile=l.get("ratePerMile"),
        weight_lbs=l.get("weight"),
        trailer_type=l.get("equipment", ""),
        pickup_date=l.get("pickupDate"),
        raw=l,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 15. C.H. Robinson — Navisphere Carrier API (free for registered carriers)
#     Register: chrobinson.com/carriers/sign-up → Navisphere account → email DOT#
# ─────────────────────────────────────────────────────────────────────────────

_chr_cache = _TokenCache()


def _chr_token() -> str | None:
    if _chr_cache.valid():
        return _chr_cache.token
    s = get_settings()
    if not s.chrobinson_client_id or not s.chrobinson_client_secret:
        return None
    tok, exp = _fetch_oauth2_token(
        "https://api.chrobinson.com/identity/connect/token",
        s.chrobinson_client_id, s.chrobinson_client_secret,
        scope="navisphere.loads.read")
    if tok:
        _chr_cache.set(tok, exp)
    return tok


def chrobinson_search(p: SearchParams) -> list[LoadResult]:
    tok = _chr_token()
    if not tok:
        return []
    headers = {"Authorization": f"Bearer {tok}", "Accept": "application/json"}
    body = _post("https://api.chrobinson.com/loads/v1/search", headers=headers, json={
        "originLocation": {
            "stateProv": p.origin_state,
            **({"city": p.origin_city} if p.origin_city else {}),
        },
        "equipmentType": p.trailer_type,
        "maxDeadheadMiles": p.max_deadhead_mi,
        "pageSize": 50,
    })
    if not body:
        return []
    return [_chr_map(l) for l in (body.get("loads") or [])]


def _chr_map(l: dict) -> LoadResult:
    o = l.get("originLocation") or {}
    d = l.get("destinationLocation") or {}
    r = l.get("rate") or {}
    return LoadResult(
        source="ch_robinson",
        load_id=str(l.get("loadNumber", l.get("id", ""))),
        broker_name="C.H. Robinson",
        origin_city=o.get("city", ""),
        origin_state=o.get("stateProv", ""),
        dest_city=d.get("city", ""),
        dest_state=d.get("stateProv", ""),
        miles=l.get("totalMiles"),
        rate_total=r.get("amount"),
        rate_per_mile=r.get("perMile"),
        weight_lbs=l.get("weight"),
        trailer_type=l.get("equipmentType", ""),
        pickup_date=(l.get("stops") or [{}])[0].get("appointmentStartDate", "")[:10] or None,
        raw=l,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Master search — fan out to all 16 sources, deduplicate by (origin, dest, rate)
# ─────────────────────────────────────────────────────────────────────────────

_ALL_CLIENTS = [
    dat_search,           # 1 — DAT (includes Convoy inventory post-acquisition)
    truckstop_search,     # 2
    loadboard123_search,  # 3
    truckerpath_search,   # 4
    direct_freight_search,# 5
    uber_freight_search,  # 6
    loadsmart_search,     # 7
    newtrul_search,       # 8
    flock_freight_search, # 9
    jbhunt_search,        # 10
    coyote_search,        # 11
    arrive_search,        # 12
    echo_global_search,   # 13
    cargo_chief_search,   # 14
    chrobinson_search,    # 15 — C.H. Robinson Navisphere (free)
    # 16 = Convoy: folded into DAT after July 2025 acquisition — sourced above
]


def search_all(params: SearchParams) -> list[LoadResult]:
    """Query all 15 sources and return deduplicated, rate-filtered results."""
    results: list[LoadResult] = []
    for fn in _ALL_CLIENTS:
        try:
            batch = fn(params)
            results.extend(batch)
            log.info("loadboard %s returned %d loads", fn.__name__, len(batch))
        except Exception as e:  # noqa: BLE001
            log.warning("loadboard %s failed: %s", fn.__name__, e)

    # Filter by minimum rate and deduplicate
    filtered = [
        r for r in results
        if r.rate_per_mile is None or r.rate_per_mile >= params.min_rate_per_mile
    ]
    seen: set[tuple] = set()
    unique: list[LoadResult] = []
    for r in filtered:
        key = (r.origin_state, r.dest_state, r.rate_total, r.miles)
        if key not in seen:
            seen.add(key)
            unique.append(r)

    unique.sort(key=lambda r: r.rate_per_mile or 0, reverse=True)
    return unique


# ── Connection Status ─────────────────────────────────────────────────────────

def get_connection_status() -> list[dict]:
    """Return credential status for all 15 load board sources."""
    s = get_settings()
    return [
        {
            "id": "dat", "name": "DAT Power", "tier": "premium",
            "est_loads_day": 500, "monthly_cost": "$699+",
            "connected": bool(s.dat_client_id and s.dat_client_secret),
            "keys_needed": ["DAT_CLIENT_ID", "DAT_CLIENT_SECRET"],
            "signup_url": "https://developer.dat.com",
            "notes": "Largest load board in North America. Includes Convoy loads (acquired 2025).",
        },
        {
            "id": "truckstop", "name": "Truckstop", "tier": "premium",
            "est_loads_day": 350, "monthly_cost": "$499+",
            "connected": bool(s.truckstop_username and s.truckstop_password),
            "keys_needed": ["TRUCKSTOP_USERNAME", "TRUCKSTOP_PASSWORD", "TRUCKSTOP_PARTNER_ID"],
            "signup_url": "https://www.truckstop.com/carriers/",
            "notes": "Strong dry van and reefer coverage. Partner ID required for API access.",
        },
        {
            "id": "123loadboard", "name": "123Loadboard", "tier": "mid",
            "est_loads_day": 150, "monthly_cost": "$45/mo",
            "connected": bool(s.loadboard_123_api_key),
            "keys_needed": ["LOADBOARD_123_API_KEY"],
            "signup_url": "https://www.123loadboard.com/",
            "notes": "Affordable. Good cargo van / sprinter coverage. API key in account settings.",
        },
        {
            "id": "truckerpath", "name": "Trucker Path", "tier": "mid",
            "est_loads_day": 120, "monthly_cost": "Contact sales",
            "connected": bool(s.truckerpath_api_key),
            "keys_needed": ["TRUCKERPATH_API_KEY"],
            "signup_url": "https://truckerpath.com/freight/",
            "notes": "Mobile-first platform with strong small carrier network.",
        },
        {
            "id": "direct_freight", "name": "Direct Freight", "tier": "mid",
            "est_loads_day": 100, "monthly_cost": "$25/mo",
            "connected": bool(s.direct_freight_username and s.direct_freight_password),
            "keys_needed": ["DIRECT_FREIGHT_USERNAME", "DIRECT_FREIGHT_PASSWORD"],
            "signup_url": "https://www.directfreight.com/",
            "notes": "Very affordable. Good for backup coverage and spot loads.",
        },
        {
            "id": "uber_freight", "name": "Uber Freight", "tier": "tech",
            "est_loads_day": 200, "monthly_cost": "Free (carrier)",
            "connected": bool(s.uber_freight_client_id and s.uber_freight_client_secret),
            "keys_needed": ["UBER_FREIGHT_CLIENT_ID", "UBER_FREIGHT_CLIENT_SECRET"],
            "signup_url": "https://www.uberfreight.com/carriers/",
            "notes": "Instant book loads. Strong CA and TX markets. OAuth2 via developer portal.",
        },
        {
            "id": "loadsmart", "name": "Loadsmart", "tier": "tech",
            "est_loads_day": 180, "monthly_cost": "Free (broker API)",
            "connected": bool(s.loadsmart_api_key),
            "keys_needed": ["LOADSMART_API_KEY"],
            "signup_url": "https://developer.loadsmart.com/",
            "notes": "Digital freight matching. Good for dry van lanes. Free broker API.",
        },
        {
            "id": "newtrul", "name": "NewTrul", "tier": "tech",
            "est_loads_day": 80, "monthly_cost": "Contact sales",
            "connected": bool(s.newtrul_api_key),
            "keys_needed": ["NEWTRUL_API_KEY"],
            "signup_url": "https://www.newtrul.com/",
            "notes": "Growing platform focused on broker-carrier automation.",
        },
        {
            "id": "flock_freight", "name": "Flock Freight", "tier": "tech",
            "est_loads_day": 90, "monthly_cost": "Contact sales",
            "connected": bool(s.flock_freight_api_key),
            "keys_needed": ["FLOCK_FREIGHT_API_KEY"],
            "signup_url": "https://www.flockfreight.com/",
            "notes": "Shared truckload specialist. Good for partial loads and lane consolidation.",
        },
        {
            "id": "jbhunt", "name": "J.B. Hunt 360", "tier": "enterprise",
            "est_loads_day": 300, "monthly_cost": "Contact sales",
            "connected": bool(s.jbhunt_client_id and s.jbhunt_client_secret),
            "keys_needed": ["JBHUNT_CLIENT_ID", "JBHUNT_CLIENT_SECRET"],
            "signup_url": "https://developer.jbhunt.com/",
            "notes": "High volume. Intermodal + truckload. Enterprise relationship required.",
        },
        {
            "id": "coyote", "name": "Coyote GO (RXO)", "tier": "enterprise",
            "est_loads_day": 250, "monthly_cost": "Contact sales",
            "connected": bool(s.coyote_client_id and s.coyote_client_secret),
            "keys_needed": ["COYOTE_CLIENT_ID", "COYOTE_CLIENT_SECRET"],
            "signup_url": "https://www.rxo.com/technology/",
            "notes": "Rebranded as RXO. Strong spot market. Large broker network access.",
        },
        {
            "id": "arrive", "name": "Arrive Logistics", "tier": "enterprise",
            "est_loads_day": 200, "monthly_cost": "Contact sales",
            "connected": bool(s.arrive_client_id and s.arrive_client_secret),
            "keys_needed": ["ARRIVE_CLIENT_ID", "ARRIVE_CLIENT_SECRET"],
            "signup_url": "https://developer.arrive.com/",
            "notes": "Fast-growing broker with strong technology platform.",
        },
        {
            "id": "echo_global", "name": "Echo Global", "tier": "enterprise",
            "est_loads_day": 180, "monthly_cost": "Contact sales",
            "connected": bool(s.echo_global_api_key),
            "keys_needed": ["ECHO_GLOBAL_API_KEY"],
            "signup_url": "https://www.echo.com/carriers/",
            "notes": "Publicly traded broker. Strong carrier partnerships.",
        },
        {
            "id": "cargo_chief", "name": "Cargo Chief", "tier": "tech",
            "est_loads_day": 70, "monthly_cost": "Contact sales",
            "connected": bool(s.cargo_chief_api_key),
            "keys_needed": ["CARGO_CHIEF_API_KEY"],
            "signup_url": "https://www.cargochief.com/",
            "notes": "AI-driven rate intelligence + load matching.",
        },
        {
            "id": "chrobinson", "name": "C.H. Robinson (Navisphere)", "tier": "enterprise",
            "est_loads_day": 600, "monthly_cost": "Free (carrier)",
            "connected": bool(s.chrobinson_client_id and s.chrobinson_client_secret),
            "keys_needed": ["CHROBINSON_CLIENT_ID", "CHROBINSON_CLIENT_SECRET"],
            "signup_url": "https://developer.chrobinson.com/",
            "notes": "Largest US broker. Free Navisphere Carrier API. Highest load volume. Apply at developer portal.",
        },
    ]
