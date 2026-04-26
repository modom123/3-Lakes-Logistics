"""Health check and basic smoke tests."""


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert "ok" in data
    assert "version" in data


def test_health_unauthenticated(client):
    # Health is public — no auth required
    r = client.get("/api/health")
    assert r.status_code == 200


def test_agents_list_requires_auth(client):
    r = client.get("/api/agents/list")
    assert r.status_code in (401, 403)


def test_agents_list_with_auth(client, auth_headers):
    r = client.get("/api/agents/list", headers=auth_headers)
    assert r.status_code == 200
    assert "agents" in r.json()


def test_load_board_requires_auth(client):
    r = client.get("/api/loads/available")
    assert r.status_code in (401, 403)


def test_load_board_with_auth(client, auth_headers):
    r = client.get("/api/loads/available", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "loads" in data
    assert "count" in data
