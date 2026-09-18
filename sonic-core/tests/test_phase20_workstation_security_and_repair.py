"""
SONIC-REDA — Phase 20 Workstation Security & Repair Regression Tests
===================================================================
Proves:
    1. Sandboxed Execution / Fail-Closed: /workstation/command routes strictly to container sandbox and fails-closed when absent.
    2. Authentication Enforcement: All /workstation routes reject unauthenticated requests.
    3. Multi-Tenant Scoping: State is partitioned strictly by tenant ID.
    4. Safe File Access: Paths outside repository root are strictly forbidden (403).
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from sonic.api.main import app
from sonic.api.routes.workstation import _tenant_workstations
from sonic.auth.google_auth import create_jwt_token
from sonic.auth.models import User, UserRole


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def isolated_workstation_state():
    _tenant_workstations.clear()
    yield
    _tenant_workstations.clear()


@pytest.fixture
def auth_headers():
    user = User(
        email="engineer@company.com",
        name="Lead Engineer",
        role=UserRole.OPERATOR,
        tenant_id="tenant-alpha",
    )
    auth_token = create_jwt_token(user)
    return {"Authorization": f"Bearer {auth_token.access_token}"}


@pytest.fixture
def tenant2_headers():
    user2 = User(
        email="tenant2@othercorp.com",
        name="External Auditor",
        role=UserRole.OPERATOR,
        tenant_id="tenant-beta",
    )
    auth_token2 = create_jwt_token(user2)
    return {"Authorization": f"Bearer {auth_token2.access_token}"}


def test_workstation_unauthenticated_rejected(client):
    """Proves unauthenticated requests are strictly rejected with 401."""
    res = client.get("/workstation/state")
    assert res.status_code == 401

    res_cmd = client.post("/workstation/command", json={"command": "whoami"})
    assert res_cmd.status_code == 401

    res_tree = client.get("/workstation/tree")
    assert res_tree.status_code == 401


def test_workstation_command_executes_in_sandbox(client, auth_headers):
    """
    CRITICAL SECURITY REGRESSION TEST:
    Proves /workstation/command executes in the Docker sandbox (not host).
    """
    res = client.post(
        "/workstation/command",
        headers=auth_headers,
        json={"command": "uname -a"},
    )
    if res.status_code == 200:
        data = res.json()
        # The command runs in an isolated sandbox plane — the provisioned desktop
        # when present, otherwise the independent headless sandbox. Never host.
        assert data["execution_environment"] in ("docker_sandbox", "headless_sandbox")
        assert "Linux" in data["output"]
    else:
        # If docker is not running on test machine, must fail closed with 503
        assert res.status_code == 503
        assert "Direct host OS execution is strictly prohibited" in res.json()["detail"]


def test_workstation_command_fails_closed_when_sandbox_unavailable(client, auth_headers):
    """
    CRITICAL SECURITY REGRESSION TEST:
    Proves that when the sandbox is not available, the route FAILS CLOSED (503)
    and NEVER falls back to executing on the host.
    """
    with patch("asyncio.create_subprocess_exec", side_effect=Exception("Docker down")):
        res = client.post(
            "/workstation/command",
            headers=auth_headers,
            json={"command": "whoami"},
        )
        assert res.status_code == 503
        assert "Direct host OS execution is strictly prohibited" in res.json()["detail"]


def test_workstation_multi_tenant_isolation(client, auth_headers, tenant2_headers):
    """Proves Tenant A and Tenant B have separate workstation states."""
    # Tenant 1 sets mission
    res1 = client.post(
        "/workstation/prompt",
        headers=auth_headers,
        json={"prompt": "Tenant 1 Secret Mission", "session_id": "session-1"},
    )
    assert res1.status_code == 200

    # Tenant 2 checks their state
    res2 = client.get("/workstation/state?session_id=session-1", headers=tenant2_headers)
    assert res2.status_code == 200
    # Must NOT see Tenant 1's mission
    assert res2.json()["mission_name"] != "Tenant 1 Secret Mission"


def test_workstation_file_access_path_traversal_blocked(client, auth_headers):
    """Proves path traversal outside repository is rejected with 403."""
    res = client.get("/workstation/file?path=../../../../etc/passwd", headers=auth_headers)
    assert res.status_code == 403


@pytest.fixture
def auditor_headers():
    user = User(
        email="auditor@company.com",
        name="Compliance Auditor",
        role=UserRole.AUDITOR,
        tenant_id="tenant-alpha",
    )
    auth_token = create_jwt_token(user)
    return {"Authorization": f"Bearer {auth_token.access_token}"}


def test_workstation_auditor_blocked_from_mutations(client, auditor_headers):
    """RBAC: read-only AUDITOR role must be rejected (403) from all workstation mutation routes."""
    mutation_routes = [
        ("post", "/workstation/desktop/provision", {}),
        ("post", "/workstation/desktop/action", {"action": "click", "coordinates": [10, 10]}),
        ("post", "/workstation/file", {"path": "sonic-core/sonic/__init__.py", "content": "x"}),
        ("post", "/workstation/command", {"command": "whoami"}),
        ("post", "/workstation/prompt", {"prompt": "test"}),
        ("delete", "/workstation/session?session_id=sess", None),
    ]
    for method, route, body in mutation_routes:
        if method == "post":
            res = client.post(route, headers=auditor_headers, json=body)
        else:
            res = client.delete(route, headers=auditor_headers)
        assert res.status_code == 403, f"AUDITOR was allowed to {method.upper()} {route} (got {res.status_code})"


def test_workstation_auditor_can_read_state(client, auditor_headers):
    """RBAC: read-only AUDITOR may still GET workstation state and desktop status (no mutation)."""
    res_state = client.get("/workstation/state", headers=auditor_headers)
    assert res_state.status_code == 200
    res_status = client.get("/workstation/desktop/status", headers=auditor_headers)
    assert res_status.status_code == 200
    # Screenshot with no workspace should degrade gracefully to 200 NO_DISPLAY, not 403/409.
    res_screen = client.get("/workstation/desktop/screenshot", headers=auditor_headers)
    assert res_screen.status_code == 200
    assert res_screen.json()["desktop_state"] == "NO_DISPLAY"


def test_workstation_screenshot_no_workspace_returns_no_display(client, auth_headers):
    """Screenshot endpoint degrades to a 200 NO_DISPLAY observation when no workstation is provisioned."""
    res = client.get("/workstation/desktop/screenshot", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["desktop_state"] == "NO_DISPLAY"
    assert data["screenshot_base64"] == ""


def test_workstation_desktop_action_no_workspace_blocks(client, auth_headers):
    """Desktop action without a substrate remains fail-closed."""
    res = client.post(
        "/workstation/desktop/action",
        headers=auth_headers,
        json={"action": "click", "coordinates": [200, 150]},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "BLOCKED"
    assert data["observation"]["desktop_state"] == "NO_DISPLAY"
    assert data["observation"]["desktop_state"] == "NO_DISPLAY"
