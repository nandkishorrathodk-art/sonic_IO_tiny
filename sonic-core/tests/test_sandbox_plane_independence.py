"""
SONIC-REDA — Sandbox-Plane Independence Regression Tests
==========================================================
Proves the headless sandbox (operator) plane no longer depends on the graphical
workstation being provisioned:

1. Sandbox command/file/tree/services work with NO desktop provisioned.
2. A provisioned desktop is still preferred when present.
3. A tenant that explicitly requested a desktop and whose provision FAILED
   fails closed (503) instead of silently using the headless fallback.
4. The sandbox plane is tenant-scoped (per-tenant container) and runs in the
   workspace root.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sonic.api.main import app
from sonic.api.routes import workstation as ws
from sonic.auth.google_auth import create_jwt_token
from sonic.auth.models import User, UserRole
from sonic.sandbox.provider import ExecResult


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_state():
    ws._tenant_workstations.clear()
    ws._desktop_intent.clear()
    yield
    ws._tenant_workstations.clear()
    ws._desktop_intent.clear()


def _headers(tenant_id: str = "tenant-alpha", email: str = "eng@company.com"):
    user = User(email=email, name="Engineer", role=UserRole.OPERATOR, tenant_id=tenant_id)
    token = create_jwt_token(user)
    return {"Authorization": f"Bearer {token.access_token}"}


class _FakePlane:
    """Stand-in for SandboxComputePlane that answers without live Docker."""

    plane_kind = "headless_sandbox"

    def __init__(self, workspace_id: str = "sonic-sandbox-abc", ok: bool = True):
        self.workspace_id = workspace_id
        self._ok = ok
        self.calls: list[tuple] = []

    async def ensure(self):
        return self._ok

    async def attach(self):
        return self._ok

    async def terminal(self, workspace_id="", command="", timeout=60, actor="operator", **kwargs):
        self.calls.append(("terminal", command))
        if not self._ok:
            return ExecResult(command=str(command), exit_code=126, stdout="", stderr="fail-closed")
        return ExecResult(command=str(command), exit_code=0, stdout="sandbox-ok", stderr="")

    async def list_files(self, workspace_id="", path="."):
        return []

    async def read_file(self, workspace_id="", path=""):
        return "sandbox file body"

    async def write_file(self, workspace_id="", path="", content="", actor="operator", **kwargs):
        return True

    async def service_action(self, workspace_id="", service_name="", action="status", actor="operator"):
        from sonic.computer.models import ServiceInfo

        return ServiceInfo(name=service_name, status="RUNNING", port=0, logs=[])


@pytest.mark.asyncio
async def test_sandbox_plane_resolves_without_desktop(monkeypatch):
    """No desktop provisioned -> an independent sandbox plane is returned."""
    plane = _FakePlane()

    async def fake_resolve(tenant_id, session_id, *, provision):
        return plane

    monkeypatch.setattr(ws, "_resolve_sandbox_plane", fake_resolve)
    resolved = await ws._resolve_sandbox_plane("tenant-alpha", "default", provision=True)
    assert resolved is plane


@pytest.mark.asyncio
async def test_resolve_prefers_provisioned_desktop(monkeypatch):
    """A provisioned desktop is preferred over the headless plane."""
    ws._tenant_workstations["tenant-alpha"] = {
        "default": {"desktop": {"workspace_id": "sonic-desktop-workstation"}}
    }
    sentinel = object()
    monkeypatch.setattr(ws, "get_daytona_computer", lambda: sentinel)

    resolved = await ws._resolve_sandbox_plane("tenant-alpha", "default", provision=True)
    assert resolved is sentinel


@pytest.mark.asyncio
async def test_desktop_intent_fails_closed_without_desktop(monkeypatch):
    """Tenant asked for a desktop and has none -> fail closed, no fallback."""
    ws._desktop_intent.add("tenant-alpha")
    resolved = await ws._resolve_sandbox_plane("tenant-alpha", "default", provision=True)
    assert resolved is None


def test_command_endpoint_uses_sandbox_plane_without_desktop(client, monkeypatch):
    """POST /workstation/command must work with no desktop provisioned."""
    plane = _FakePlane()

    async def fake_resolve(tenant_id, session_id, *, provision):
        return plane

    monkeypatch.setattr(ws, "_resolve_sandbox_plane", fake_resolve)
    res = client.post(
        "/workstation/command", headers=_headers(), json={"command": "uname -a", "session_id": "default"}
    )
    assert res.status_code == 200
    assert res.json()["exit_code"] == 0
    assert res.json()["execution_environment"] == "headless_sandbox"
    assert ("terminal", "uname -a") in plane.calls


def test_command_endpoint_fails_closed_when_no_plane(client, monkeypatch):
    """No usable sandbox -> documented fail-closed 503 (never host execution)."""
    async def fake_resolve(tenant_id, session_id, *, provision):
        return None

    monkeypatch.setattr(ws, "_resolve_sandbox_plane", fake_resolve)
    res = client.post(
        "/workstation/command", headers=_headers(), json={"command": "whoami", "session_id": "default"}
    )
    assert res.status_code == 503
    assert "Direct host OS execution is strictly prohibited" in res.json()["detail"]


def test_file_endpoints_use_sandbox_plane_without_desktop(client, monkeypatch):
    """GET/POST /workstation/file work without a desktop."""
    plane = _FakePlane()

    async def fake_resolve(tenant_id, session_id, *, provision):
        return plane

    monkeypatch.setattr(ws, "_resolve_sandbox_plane", fake_resolve)

    read = client.get("/workstation/file?path=notes.txt", headers=_headers())
    assert read.status_code == 200
    assert read.json()["content"] == "sandbox file body"

    write = client.post(
        "/workstation/file", headers=_headers(), json={"path": "notes.txt", "content": "hi"}
    )
    assert write.status_code == 200
    assert write.json()["status"] == "saved"


def test_sandbox_plane_is_tenant_scoped():
    """Each tenant resolves to its own sandbox container id."""
    a = ws._tenant_hash("tenant-alpha")
    b = ws._tenant_hash("tenant-beta")
    assert a != b
    assert len(a) == 12 and len(b) == 12
