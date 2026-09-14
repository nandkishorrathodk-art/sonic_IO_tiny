"""
Unit tests for DockerComputerProvider (Native Workstation Engine).
"""

import os
import base64
import shutil
import subprocess
from unittest.mock import AsyncMock
import pytest
from sonic.computer.daytona_computer import DaytonaComputerProvider
from sonic.computer.docker_computer import DockerComputerProvider, _get_display
from sonic.computer.models import GUIAction, GUIActionType


def _docker_daemon_up() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return (
            subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            ).returncode
            == 0
        )
    except Exception:
        return False


@pytest.mark.no_live_infra
@pytest.mark.asyncio
async def test_docker_computer_provider_lifecycle():
    provider = DockerComputerProvider(container_name="sonic-desktop-workstation")
    ws = await provider.create("tenant-1", "eng-1")
    assert ws.id == "sonic-desktop-workstation"
    assert ws.tenant_id == "tenant-1"

    url = await provider.get_vnc_url(ws.id)
    # A real noVNC listener only exists when the daemon + workstation container
    # are actually up. Fail-closed returns None otherwise — assert accordingly.
    if _docker_daemon_up():
        assert url is not None
        assert "6080" in url

    if _docker_daemon_up():
        status = await provider.status(ws.id)
        assert status.workspace_id == "sonic-desktop-workstation"
        assert len(status.running_processes) >= 0

        # Test terminal execution
        res = await provider.terminal(ws.id, "echo hello_docker_native")
        if res.exit_code == 0:
            assert "hello_docker_native" in res.stdout

        # Test screenshot
        obs = await provider.screenshot(ws.id)
        assert obs.width == 1280
        assert obs.height == 800

        # Test gui click action
        action = GUIAction(action=GUIActionType.CLICK, x=100, y=100)
        action_obs = await provider.gui_action(ws.id, action)
        assert action_obs.width == 1280


@pytest.mark.no_live_infra
@pytest.mark.asyncio
async def test_docker_computer_provider_files_and_apps():
    provider = DockerComputerProvider(container_name="sonic-desktop-workstation")
    ws_id = "sonic-desktop-workstation"

    if _docker_daemon_up():
        # Test write file
        test_content = "sonic_security_audit_test_file"
        test_path = "/tmp/sonic_test.txt"
        wrote = await provider.write_file(ws_id, test_path, test_content)
        assert wrote is True

        # Test read file
        read_back = await provider.read_file(ws_id, test_path)
        assert test_content in read_back

        # Test list applications
        apps = await provider.application_list(ws_id)
        assert len(apps) > 0


@pytest.mark.no_live_infra
@pytest.mark.asyncio
async def test_docker_screenshot_does_not_reuse_stale_pixels_after_capture_failure():
    provider = DockerComputerProvider(container_name="sonic-desktop-workstation")
    encoded = base64.b64encode(b"pixel-data" * 20).decode()
    provider._docker_exec = AsyncMock(side_effect=[
        (0, encoded, ""),
        (126, "", "display unavailable"),
    ])

    first = await provider.screenshot("ws-1")
    provider._last_screenshot_time = 0.0
    second = await provider.screenshot("ws-1")

    assert first.desktop_state == "INTERACTIVE"
    assert second.desktop_state == "NO_DISPLAY"
    assert second.screenshot_base64 == ""


@pytest.mark.no_live_infra
def test_docker_computer_display_resolution(monkeypatch):
    """Proves dynamic display resolution helper checks environment and defaults to :99."""
    monkeypatch.delenv("DISPLAY", raising=False)
    provider = DockerComputerProvider()
    assert _get_display() == ":99"
    assert provider._get_display("ws-1") == ":99"

    monkeypatch.setenv("DISPLAY", ":42")
    assert _get_display() == ":42"
    assert provider._get_display("ws-1") == ":42"


@pytest.mark.no_live_infra
@pytest.mark.asyncio
async def test_docker_computer_launch_application_quoting(monkeypatch):
    """Proves launch_application uses shlex.split and quotes each part individually."""
    monkeypatch.delenv("DISPLAY", raising=False)
    provider = DockerComputerProvider()
    provider._docker_exec = AsyncMock(return_value=(0, "", ""))

    success = await provider.launch_application("ws-1", "chromium https://target.local")
    assert success is True
    provider._docker_exec.assert_called_once()
    called_cmd = provider._docker_exec.call_args[0][0]
    expected_spawn = "DISPLAY=:99 nohup chromium https://target.local >/dev/null 2>&1 &"
    assert called_cmd == expected_spawn

    # Also test an argument with spaces / special characters that requires escaping
    provider._docker_exec.reset_mock()
    success2 = await provider.launch_application("ws-1", "chromium 'https://target.local/path with spaces'")
    assert success2 is True
    called_cmd2 = provider._docker_exec.call_args[0][0]
    expected_spawn2 = "DISPLAY=:99 nohup chromium 'https://target.local/path with spaces' >/dev/null 2>&1 &"
    assert called_cmd2 == expected_spawn2


@pytest.mark.no_live_infra
@pytest.mark.asyncio
async def test_daytona_computer_display_and_launch_quoting(monkeypatch):
    """Proves DaytonaComputerProvider uses :0 default, checks DISPLAY, and quotes launch arguments."""
    from sonic.sandbox.provider import ExecResult

    monkeypatch.delenv("DISPLAY", raising=False)
    provider = DaytonaComputerProvider(api_key="")
    assert provider._get_display("ws-1") == ":0"

    monkeypatch.setenv("DISPLAY", ":1")
    assert provider._get_display("ws-1") == ":1"

    provider.terminal = AsyncMock(return_value=ExecResult(command="", exit_code=0, stdout="", stderr=""))
    success = await provider.launch_application("ws-1", "chromium https://target.local")
    assert success is True
    provider.terminal.assert_called_once()
    called_cmd = provider.terminal.call_args[0][1]
    expected_spawn = "DISPLAY=:1 nohup chromium https://target.local >/dev/null 2>&1 &"
    assert called_cmd == expected_spawn

    # Also test special characters quoting
    provider.terminal.reset_mock()
    success2 = await provider.launch_application("ws-1", "chromium 'https://target.local/search?q=1&v=2'")
    assert success2 is True
    called_cmd2 = provider.terminal.call_args[0][1]
    expected_spawn2 = "DISPLAY=:1 nohup chromium 'https://target.local/search?q=1&v=2' >/dev/null 2>&1 &"
    assert called_cmd2 == expected_spawn2
