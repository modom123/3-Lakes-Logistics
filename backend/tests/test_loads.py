"""Integration tests for /api/loads/ endpoints."""
from unittest.mock import MagicMock, patch

_PATCH_TARGET = "app.api.routes_loads.get_supabase"
_LOG_TARGET = "app.supabase_client.get_supabase"

_LOAD = {
    "id": "load-abc",
    "load_number": "L001",
    "carrier_id": "carrier-1",
    "driver_id": "driver-1",
    "driver_name": "John Williams",
    "origin_city": "Chicago", "origin_state": "IL",
    "dest_city": "Atlanta", "dest_state": "GA",
    "rate_total": 2500.00,
    "miles": 730,
    "status": "available",
    "created_at": "2026-04-20T10:00:00Z",
}


def _qb(list_data=None, single_data=_LOAD):
    qb = MagicMock()
    for attr in ("select", "eq", "neq", "gte", "lte", "lt", "gt",
                 "in_", "ilike", "limit", "order", "update", "insert"):
        getattr(qb, attr).return_value = qb
    qb.execute.return_value = MagicMock(data=list_data if list_data is not None else [_LOAD])
    qb.maybe_single.return_value = MagicMock(execute=lambda: MagicMock(data=single_data))
    qb.insert.return_value = MagicMock(execute=lambda: MagicMock(data=[_LOAD]))
    return qb


def _sb(list_data=None, single_data=_LOAD):
    sb = MagicMock()
    sb.table.return_value = _qb(list_data=list_data, single_data=single_data)
    return sb


def test_list_loads_requires_auth(client):
    r = client.get("/api/loads/")
    assert r.status_code in (401, 403)


def test_list_loads(client, auth_headers):
    with patch(_PATCH_TARGET, return_value=_sb()):
        r = client.get("/api/loads/", headers=auth_headers)
    assert r.status_code == 200


def test_available_loads(client, auth_headers):
    with patch(_PATCH_TARGET, return_value=_sb()):
        r = client.get("/api/loads/available", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "loads" in data
    assert "count" in data


def test_create_load(client, auth_headers):
    with patch(_PATCH_TARGET, return_value=_sb()), patch(_LOG_TARGET, return_value=_sb()):
        r = client.post("/api/loads/", json={
            "origin_city": "Chicago", "origin_state": "IL",
            "dest_city": "Atlanta", "dest_state": "GA",
            "rate_total": 2500.00,
            "miles": 730,
            "status": "available",
        }, headers=auth_headers)
    assert r.status_code == 201


def test_get_load(client, auth_headers):
    with patch(_PATCH_TARGET, return_value=_sb(single_data=_LOAD)):
        r = client.get("/api/loads/load-abc", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "load-abc"


def test_get_load_not_found(client, auth_headers):
    with patch(_PATCH_TARGET, return_value=_sb(single_data=None)):
        r = client.get("/api/loads/nonexistent", headers=auth_headers)
    assert r.status_code == 404


def test_update_load_status_valid(client, auth_headers):
    """PATCH /api/loads/{id}/status advances booked → dispatched."""
    load_booked = {**_LOAD, "status": "booked"}
    sb = _sb(single_data=load_booked)
    with patch(_PATCH_TARGET, return_value=sb), patch(_LOG_TARGET, return_value=sb):
        r = client.patch("/api/loads/load-abc/status",
                         json={"status": "dispatched"},
                         headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_update_load_status_invalid_transition(client, auth_headers):
    """PATCH with invalid transition returns 409."""
    load_delivered = {**_LOAD, "status": "delivered"}
    sb = _sb(single_data=load_delivered)
    with patch(_PATCH_TARGET, return_value=sb):
        r = client.patch("/api/loads/load-abc/status",
                         json={"status": "available"},
                         headers=auth_headers)
    assert r.status_code == 409


def test_load_events(client, auth_headers):
    """GET /api/loads/{id}/events returns event list."""
    with patch(_PATCH_TARGET, return_value=_sb(list_data=[])):
        r = client.get("/api/loads/load-abc/events", headers=auth_headers)
    assert r.status_code == 200


def test_cron_mark_overdue(client):
    """POST /api/cron/mark-overdue with no secret (empty CRON_SECRET) succeeds."""
    cron_sb = MagicMock()
    qb = MagicMock()
    for attr in ("eq", "lt", "update"):
        getattr(qb, attr).return_value = qb
    qb.execute.return_value = MagicMock(data=[])
    cron_sb.table.return_value = qb

    with patch("app.api.routes_cron.get_supabase", return_value=cron_sb), \
         patch(_LOG_TARGET, return_value=cron_sb):
        r = client.post("/api/cron/mark-overdue")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "invoices_flagged_overdue" in data


def test_cron_cdl_sweep(client):
    """POST /api/cron/cdl-sweep returns expiring CDL count."""
    cron_sb = MagicMock()
    qb = MagicMock()
    for attr in ("select", "lte", "gte", "eq"):
        getattr(qb, attr).return_value = qb
    qb.execute.return_value = MagicMock(data=[])
    cron_sb.table.return_value = qb

    with patch("app.api.routes_cron.get_supabase", return_value=cron_sb), \
         patch(_LOG_TARGET, return_value=cron_sb), \
         patch("app.agents.signal.run", return_value={}):
        r = client.post("/api/cron/cdl-sweep")
    assert r.status_code == 200
    assert r.json()["ok"] is True
