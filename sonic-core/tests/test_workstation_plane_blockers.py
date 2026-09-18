"""
SONIC-REDA — Regression tests for the workstation-plane blockers
=================================================================
Locks in the fixes that made the native Docker workstation usable:

1. Durable workspace state isolation: a test run must never write a foreign
   tenant into the real ``sonic_data/docker_workstations.json`` (that
   permanently locked the real backend out of provisioning).
2. Stale-claim reclaim: ``DockerComputerProvider.create()`` /
   ``get_or_create_home()`` must not refuse a different tenant when the
   container is NOT running (persisted ownership is authoritative only while
   the desktop is live).
3. ``create()`` verify-the-real-result: a non-zero ``docker start`` must never
   be reported as RUNNING.
4. Safety path confinement must use the provider's real workspace root
   (``/home/sonic/workspace``), not ``/root``.
"""

from __future__ import annotations

import json

import pytest

from sonic.computer.docker_computer import DockerComputerProvider
from sonic.computer.models import ComputerWorkspaceStatus


def _stopped():
    async def _inner():
        return False
    return _inner()


def _running():
    async def _inner():
        return True
    return _inner()


@pytest.mark.asyncio
async def test_stale_cross_tenant_claim_is_reclaimed_when_container_stopped(
    tmp_path, monkeypatch
):
    """A persisted claim from another tenant must not block a stopped desktop."""
    state_path = tmp_path / "docker_workstations.json"
    state_path.write_text(
        json.dumps(
            {
                "sonic-desktop-workstation": {
                    "tenant_id": "tenant-1",
                    "engagement_id": "eng-1",
                    "workspace_type": "MISSION_COMPUTER",
                    "profile": "KALI_SECURITY",
                    "provider_type": "DockerComputerProvider",
                    "image": "sonic-workstation:latest",
                    "status": "RUNNING",
                }
            }
        )
    )
    monkeypatch.setenv("SONIC_WORKSTATION_STATE_PATH", str(state_path))

    provider = DockerComputerProvider(container_name="sonic-desktop-workstation")
    assert provider._workspace_owner == "tenant-1"

    # Container is stopped -> the stale claim is not authoritative.
    monkeypatch.setattr(provider, "_container_is_running", lambda: _stopped())
    monkeypatch.setattr(provider, "_provision_workstation", lambda: _false())

    ws = await provider.create("default", "default")
    assert ws.tenant_id == "default"
    # No live container -> must not fabricate RUNNING.
    assert ws.status in (ComputerWorkspaceStatus.STOPPED, ComputerWorkspaceStatus.FAILED)


async def _false():
    return False


@pytest.mark.asyncio
async def test_running_container_still_refuses_cross_tenant_takeover(
    tmp_path, monkeypatch
):
    """A live desktop must NOT be silently reassigned to a different tenant."""
    monkeypatch.setenv("SONIC_WORKSTATION_STATE_PATH", str(tmp_path / "ws.json"))
    provider = DockerComputerProvider(container_name="sonic-desktop-workstation")
    provider._workspace_owner = "tenant-1"
    monkeypatch.setattr(provider, "_container_is_running", lambda: _running())

    with pytest.raises(RuntimeError):
        await provider.create("default", "default")


@pytest.mark.asyncio
async def test_get_or_create_home_reclaims_stale_claim(tmp_path, monkeypatch):
    """get_or_create_home mirrors create()'s stale-claim behaviour."""
    monkeypatch.setenv("SONIC_WORKSTATION_STATE_PATH", str(tmp_path / "ws.json"))
    provider = DockerComputerProvider(container_name="sonic-desktop-workstation")
    provider._workspace_owner = "tenant-1"
    monkeypatch.setattr(provider, "_container_is_running", lambda: _stopped())

    home = await provider.get_or_create_home("default")
    assert home.tenant_id == "default"


@pytest.mark.asyncio
async def test_failed_docker_start_is_not_reported_running(tmp_path, monkeypatch):
    """A refused `docker start` must yield STOPPED/FAILED, never RUNNING."""
    monkeypatch.setenv("SONIC_WORKSTATION_STATE_PATH", str(tmp_path / "ws.json"))
    provider = DockerComputerProvider(container_name="does-not-exist")
    monkeypatch.setattr(provider, "_container_is_running", lambda: _stopped())
    monkeypatch.setattr(provider, "_provision_workstation", lambda: _false())

    ws = await provider.create("default", "default")
    assert ws.status != ComputerWorkspaceStatus.RUNNING


def test_workstation_route_uses_provider_workspace_root():
    """Path confinement must match the provider's real workspace root."""
    from fastapi import HTTPException

    from sonic.api.routes.workstation import _WORKSPACE_ROOT, _workspace_file_path

    assert _WORKSPACE_ROOT == "/home/sonic/workspace"
    # A file inside the workspace root is allowed.
    assert _workspace_file_path("notes.txt") == "/home/sonic/workspace/notes.txt"
    # Traversal outside remains rejected.
    with pytest.raises(HTTPException):
        _workspace_file_path("../../etc/passwd")
