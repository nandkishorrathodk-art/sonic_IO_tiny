import pytest

from sonic.computer.docker_computer import DockerComputerProvider
from sonic.computer.models import ComputerWorkspaceStatus


@pytest.mark.asyncio
async def test_docker_workspace_identity_survives_provider_restart(tmp_path, monkeypatch):
    state_path = tmp_path / "workstations.json"
    monkeypatch.setenv("SONIC_WORKSTATION_STATE_PATH", str(state_path))

    first = DockerComputerProvider(container_name="continuum-test")
    workspace = await first.get_or_create_home("tenant-a")
    assert workspace.tenant_id == "tenant-a"
    assert state_path.exists()

    second = DockerComputerProvider(container_name="continuum-test")
    restored = await second.reconnect(workspace.id, "tenant-a")
    assert restored.id == workspace.id
    assert restored.tenant_id == "tenant-a"
    assert restored.status == ComputerWorkspaceStatus.STOPPED


@pytest.mark.asyncio
async def test_docker_workspace_cannot_be_reconnected_by_another_tenant(tmp_path, monkeypatch):
    monkeypatch.setenv("SONIC_WORKSTATION_STATE_PATH", str(tmp_path / "workstations.json"))
    provider = DockerComputerProvider(container_name="continuum-test")
    workspace = await provider.get_or_create_home("tenant-a")

    with pytest.raises(PermissionError):
        await provider.reconnect(workspace.id, "tenant-b")


@pytest.mark.asyncio
async def test_home_identity_does_not_fabricate_running_status(tmp_path, monkeypatch):
    monkeypatch.setenv("SONIC_WORKSTATION_STATE_PATH", str(tmp_path / "workstations.json"))
    provider = DockerComputerProvider(container_name="continuum-test")
    monkeypatch.setattr(provider, "_container_is_running", lambda: _stopped())

    workspace = await provider.get_or_create_home("tenant-a")

    assert workspace.status == ComputerWorkspaceStatus.STOPPED


async def _stopped():
    return False
