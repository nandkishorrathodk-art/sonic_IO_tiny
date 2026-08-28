"""
Unit and Integration tests for Authenticated Live API and Secure Terminal routes.
"""

import pytest
from fastapi.testclient import TestClient
from sonic.api.main import app
from sonic.api.routes.live import register_agent, record_finding, record_asset
from sonic.auth.google_auth import create_jwt_token
from sonic.auth.models import User, UserRole

client = TestClient(app)

# Helper to generate test tokens
def get_auth_headers(role: UserRole = UserRole.OPERATOR, email: str = "operator@target.com"):
    user = User(email=email, name="Test Operator", google_id="g-123", role=role)
    token = create_jwt_token(user)
    return {"Authorization": f"Bearer {token.access_token}"}, token.access_token


def test_unauthenticated_requests_are_rejected():
    """Verify that unauthenticated calls to all /live/* endpoints return 401."""
    assert client.get("/live/stats").status_code == 401
    assert client.get("/live/agents").status_code == 401
    assert client.get("/live/findings").status_code == 401
    assert client.get("/live/graph").status_code == 401
    assert client.get("/live/evidence").status_code == 401
    assert client.post("/live/scan", json={"target": "example.com"}).status_code == 401
    assert client.get("/live/settings").status_code == 401
    assert client.post("/live/settings", json={"llm_model": "gpt-4o"}).status_code == 401


def test_authenticated_live_stats():
    """Test /live/stats with valid JWT token."""
    headers, _ = get_auth_headers()
    response = client.get("/live/stats", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "assets_mapped" in data
    assert "active_agents" in data
    assert "verified_findings" in data
    assert data["user"] == "operator@target.com"


def test_authenticated_live_findings_flow():
    """Test registering tenant finding and retrieving it."""
    headers, _ = get_auth_headers(email="tenant-a@target.com")

    record_finding({
        "title": "Tenant A Finding",
        "severity": "high",
        "vulnerability_class": "IDOR",
        "confidence": 95,
        "poc": "curl https://api/v1/user/10",
        "impact": "Account takeover",
    }, tenant_id="tenant-a@target.com")

    res_findings = client.get("/live/findings", headers=headers)
    assert res_findings.status_code == 200
    findings = res_findings.json().get("findings", [])
    assert any(f["title"] == "Tenant A Finding" for f in findings)


def test_admin_settings_protection():
    """Test that regular operators cannot mutate settings, but admins can."""
    operator_headers, _ = get_auth_headers(role=UserRole.OPERATOR)
    admin_headers, _ = get_auth_headers(role=UserRole.ADMIN)

    # Operator gets 403 Forbidden
    res_op = client.post("/live/settings", json={"llm_model": "claude-3-5-sonnet"}, headers=operator_headers)
    assert res_op.status_code == 403

    # Admin gets 200 OK
    res_admin = client.post("/live/settings", json={"llm_model": "claude-3-5-sonnet"}, headers=admin_headers)
    assert res_admin.status_code == 200
    assert res_admin.json()["status"] == "updated"


def test_terminal_websocket_unauthenticated_rejection():
    """Test that unauthenticated WebSocket connections to /terminal/ws/terminal receive auth error and close."""
    with client.websocket_connect("/terminal/ws/terminal") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "AUTH ERROR" in msg["data"]



def test_terminal_websocket_authenticated_connect():
    """Test that authenticated WebSocket connection attempts to reach container, not host."""
    _, token = get_auth_headers()
    # When container is not running, it gracefully reports container not running rather than running on host
    with client.websocket_connect(f"/terminal/ws/terminal?token={token}&container=non-existent-sandbox") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "SANDBOX NOTICE" in msg["data"] or "not running" in msg["data"]
