"""
Tests for DockerContainerSandbox and DaytonaComputerProvider local fallback.
"""

import pytest
import shutil
from sonic.computer.docker_sandbox import DockerContainerSandbox
from sonic.computer.daytona_computer import DaytonaComputerProvider
from sonic.computer.models import GUIAction, GUIActionType


@pytest.mark.no_live_infra
@pytest.mark.asyncio
async def test_docker_container_sandbox_interface():
    sb = DockerContainerSandbox("sonic-desktop-workstation")
    assert sb.id == "sonic-desktop-workstation"
    assert sb.state == "started"

    # Test preview link
    preview = await sb.get_preview_link(6080)
    assert preview.url == "http://localhost:6080/vnc.html"

    # If docker is running and container is up, test exec
    if shutil.which("docker"):
        res = await sb.process.exec("echo hello_test")
        # In environments where the container is running:
        if res.exit_code == 0:
            assert "hello_test" in res.result


@pytest.mark.no_live_infra
@pytest.mark.asyncio
async def test_daytona_resolves_docker_workstation():
    provider = DaytonaComputerProvider(api_key="")
    # Register or resolve docker-workstation
    sb = await provider._resolve_sandbox("sonic-desktop-workstation")
    assert sb is not None
    assert sb.id == "sonic-desktop-workstation"

    url = await provider.get_vnc_url("sonic-desktop-workstation")
    assert url == "http://localhost:6080/vnc.html"


@pytest.mark.no_live_infra
@pytest.mark.asyncio
async def test_daytona_docker_terminal_and_screenshot():
    provider = DaytonaComputerProvider(api_key="")
    term_res = await provider.terminal("sonic-desktop-workstation", "uname -a")
    if term_res.exit_code == 0:
        assert "Linux" in term_res.stdout

    obs = await provider.screenshot("sonic-desktop-workstation")
    assert obs is not None
    assert obs.width == 1280
    assert obs.height == 800
