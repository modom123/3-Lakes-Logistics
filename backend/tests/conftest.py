"""pytest configuration — sets up a test FastAPI client with mocked Supabase."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Set test env vars before importing the app
os.environ.setdefault("ENV", "test")
os.environ.setdefault("API_BEARER_TOKEN", "test-token")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")

# Stub out the supabase package so the app can import without a real DB connection.
# This must happen before any app module is imported.
if "supabase" not in sys.modules:
    _supabase_stub = MagicMock()
    _supabase_stub.create_client.return_value = MagicMock()
    sys.modules["supabase"] = _supabase_stub
    sys.modules["supabase.Client"] = MagicMock()
# Also stub out heavy optional dependencies that may not be installed in CI
for _mod in ("stripe", "twilio", "twilio.rest", "anthropic", "sendgrid",
             "sendgrid.helpers", "sendgrid.helpers.mail"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


def _mock_supabase():
    """Return a MagicMock that satisfies the chained Supabase query builder pattern."""
    sb = MagicMock()
    qb = MagicMock()
    # Any chain of .table().select().eq()...execute() returns empty data by default
    qb.execute.return_value = MagicMock(data=[], count=0)
    qb.select.return_value = qb
    qb.eq.return_value = qb
    qb.neq.return_value = qb
    qb.gte.return_value = qb
    qb.lte.return_value = qb
    qb.in_.return_value = qb
    qb.ilike.return_value = qb
    qb.limit.return_value = qb
    qb.order.return_value = qb
    qb.single.return_value = qb
    qb.maybe_single.return_value = qb
    qb.insert.return_value = qb
    qb.update.return_value = qb
    qb.upsert.return_value = qb
    qb.delete.return_value = qb
    sb.table.return_value = qb
    sb.rpc.return_value = qb
    return sb


@pytest.fixture(scope="session")
def mock_sb():
    return _mock_supabase()


@pytest.fixture(scope="session")
def client(mock_sb):
    with patch("app.supabase_client.get_supabase", return_value=mock_sb):
        from app.main import create_app
        app = create_app()
        with TestClient(app) as c:
            yield c


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token"}
