"""Integration tests for /api/invoices/ endpoints."""
from unittest.mock import MagicMock, patch

# Routes import get_supabase at module level; patch the reference in the route module.
# logging_service uses a lazy import, so patch supabase_client for it.
_PATCH_TARGET = "app.api.routes_invoices.get_supabase"
_LOG_TARGET = "app.supabase_client.get_supabase"

_INV = {
    "id": "inv-001",
    "invoice_number": "INV-202604-0001",
    "carrier_id": "carrier-1",
    "load_id": "load-1",
    "amount": 2500.00,
    "dispatch_fee": 200.00,
    "status": "Unpaid",
    "invoice_date": "2026-04-01",
    "due_date": "2026-04-04",
    "created_at": "2026-04-01T10:00:00Z",
}


def _sb(inv=None, query_list=None):
    """Supabase mock: insert returns inv; list query returns query_list."""
    inv = inv or _INV
    sb = MagicMock()

    def table_side(name):
        qb = MagicMock()
        for attr in ("select", "eq", "neq", "gte", "lte", "lt", "gt",
                     "in_", "ilike", "limit", "order", "update", "maybe_single"):
            getattr(qb, attr).return_value = qb
        if name == "invoices":
            qb.execute.return_value = MagicMock(data=query_list if query_list is not None else [inv])
            qb.insert.return_value = MagicMock(execute=lambda: MagicMock(data=[inv]))
        else:
            qb.execute.return_value = MagicMock(data=[])
            qb.insert.return_value = MagicMock(execute=lambda: MagicMock(data=[]))
        return qb

    sb.table.side_effect = table_side
    return sb


def test_list_invoices_requires_auth(client):
    r = client.get("/api/invoices/")
    assert r.status_code in (401, 403)


def test_list_invoices(client, auth_headers):
    sb = _sb()
    with patch(_PATCH_TARGET, return_value=sb), patch(_LOG_TARGET, return_value=sb):
        r = client.get("/api/invoices/", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "count" in data
    assert "items" in data
    assert "total_amount" in data


def test_create_invoice(client, auth_headers):
    sb = _sb()
    with patch(_PATCH_TARGET, return_value=sb), patch(_LOG_TARGET, return_value=sb):
        r = client.post("/api/invoices/", json={
            "carrier_id": "carrier-1",
            "amount": 2500.00,
        }, headers=auth_headers)
    assert r.status_code == 201
    data = r.json()
    assert data["ok"] is True
    assert "invoice" in data


def test_invoice_aging(client, auth_headers):
    overdue_inv = {**_INV, "status": "Overdue", "due_date": "2026-01-01"}
    sb = _sb(inv=overdue_inv, query_list=[overdue_inv])
    with patch(_PATCH_TARGET, return_value=sb):
        r = client.get("/api/invoices/aging", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "buckets" in data
    assert "as_of" in data
    assert "total_outstanding" in data
    for key in ("current", "1_30", "31_60", "61_90", "over_90"):
        assert key in data["buckets"]


def test_invoice_summary(client, auth_headers):
    sb = _sb()
    with patch(_PATCH_TARGET, return_value=sb):
        r = client.get("/api/invoices/summary?year=2026&month=4", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["period"] == "2026-04"
    assert "total_billed" in data
    assert "collected" in data
    assert "collection_rate" in data


def test_mark_paid(client, auth_headers):
    sb = _sb()
    with patch(_PATCH_TARGET, return_value=sb), patch(_LOG_TARGET, return_value=sb):
        r = client.post("/api/invoices/inv-001/mark-paid",
                        json={"payment_ref": "CHK-1234"},
                        headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "Paid"


def test_mark_overdue(client, auth_headers):
    sb = _sb()
    with patch(_PATCH_TARGET, return_value=sb):
        r = client.post("/api/invoices/inv-001/mark-overdue", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "Overdue"


def test_void_invoice(client, auth_headers):
    sb = _sb()
    with patch(_PATCH_TARGET, return_value=sb), patch(_LOG_TARGET, return_value=sb):
        r = client.delete("/api/invoices/inv-001", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "Void"


def test_cannot_edit_paid_invoice(client, auth_headers):
    paid_inv = {**_INV, "status": "Paid"}
    sb = _sb(inv=paid_inv)
    # maybe_single returns paid invoice
    def table_side(name):
        qb = MagicMock()
        for attr in ("select", "eq", "neq", "gte", "lte", "lt",
                     "in_", "ilike", "limit", "order", "update"):
            getattr(qb, attr).return_value = qb
        qb.maybe_single.return_value = MagicMock(execute=lambda: MagicMock(data=paid_inv))
        qb.execute.return_value = MagicMock(data=[paid_inv])
        return qb
    sb2 = MagicMock()
    sb2.table.side_effect = table_side
    with patch(_PATCH_TARGET, return_value=sb2):
        r = client.patch("/api/invoices/inv-001", json={"notes": "updated"}, headers=auth_headers)
    assert r.status_code == 409


def test_generate_from_load_missing_id(client, auth_headers):
    sb = _sb()
    with patch(_PATCH_TARGET, return_value=sb):
        r = client.post("/api/invoices/generate-from-load",
                        json={},
                        headers=auth_headers)
    assert r.status_code == 400


def test_generate_from_load_wrong_status(client, auth_headers):
    load_data = {"id": "load-1", "status": "available", "rate_total": 1000}

    def table_side(name):
        qb = MagicMock()
        for attr in ("select", "eq", "neq", "gte", "lte", "lt",
                     "in_", "ilike", "limit", "order", "update", "insert"):
            getattr(qb, attr).return_value = qb
        if name == "loads":
            qb.maybe_single.return_value = MagicMock(execute=lambda: MagicMock(data=load_data))
        else:
            qb.maybe_single.return_value = MagicMock(execute=lambda: MagicMock(data=None))
        qb.execute.return_value = MagicMock(data=[])
        return qb

    sb = MagicMock()
    sb.table.side_effect = table_side
    with patch(_PATCH_TARGET, return_value=sb):
        r = client.post("/api/invoices/generate-from-load",
                        json={"load_id": "load-1"},
                        headers=auth_headers)
    assert r.status_code == 409
