"""
Tests for Workstation Self-Bootstrap & CA Trust Handshake (Phase 8)
===================================================================
Verifies:
  1. Environment auditing and automated toolchain remediation (`ensure_workstation_ready`).
  2. TCP socket port waiting (`wait_for_port_open`).
  3. Deterministic proxy CA certificate trust handshake (`setup_proxy_ca_trust`).
  4. Integration with ComputerUseAgent.run_mission lifecycle.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from sonic.computer.bootstrap import WorkstationBootstrapEngine, DEFAULT_REQUIRED_BINARIES
from sonic.computer.models import ScreenObservation
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import ComputerActionType


class _MockBootstrapComputer:
    """Mock compute provider simulating container command execution."""

    def __init__(self, missing_binaries: list[str] | None = None, port_open_attempts: int = 1):
        self.commands_executed: list[str] = []
        self.missing_binaries = missing_binaries or []
        self.port_attempts = 0
        self.port_open_attempts = port_open_attempts

    async def _docker_exec(self, cmd: str, timeout: int = 60) -> tuple[int, str, str]:
        self.commands_executed.append(cmd)

        # 1. Dependency probe command
        if "which" in cmd:
            output_lines = []
            for b in self.missing_binaries:
                if b in self.missing_binaries:
                    output_lines.append(f"MISSING:{b}")
            return 0, "\n".join(output_lines), ""

        # 2. Apt install remediation command
        if "apt-get install" in cmd:
            return 0, "Packages installed successfully", ""

        # 3. Port check command
        if "/dev/tcp/" in cmd:
            self.port_attempts += 1
            if self.port_attempts >= self.port_open_attempts:
                return 0, "OPEN", ""
            return 0, "CLOSED", ""

        # 4. Cert fetch command
        if "http://proxy/cert" in cmd or "/tmp/cacert.der" in cmd:
            return 0, "DER bytes fetched", ""

        # 5. OpenSSL / certutil / update-ca-certificates
        if "openssl" in cmd or "update-ca-certificates" in cmd or "certutil" in cmd:
            return 0, "OK", ""

        # 6. Verification probe
        if "httpbin.org" in cmd:
            return 0, "200", ""

        return 0, "", ""


@pytest.mark.asyncio
async def test_bootstrap_ensure_workstation_ready_all_present():
    comp = _MockBootstrapComputer(missing_binaries=[])
    engine = WorkstationBootstrapEngine(comp)

    res = await engine.ensure_workstation_ready(
        "ws-1",
        required_binaries=["python3", "curl", "git", "certutil", "xdotool", "wmctrl"],
    )
    assert res["status"] == "READY"
    assert len(res["missing"]) == 0
    assert len(res["present"]) == 6
    assert len(res["installed"]) == 0


@pytest.mark.asyncio
async def test_bootstrap_ensure_workstation_ready_remediation():
    comp = _MockBootstrapComputer(missing_binaries=["certutil", "ffuf"])
    engine = WorkstationBootstrapEngine(comp)

    res = await engine.ensure_workstation_ready(
        "ws-1",
        required_binaries=["certutil", "ffuf"],
    )
    assert res["status"] == "REMEDIATED"
    assert "certutil" in res["missing"]
    assert "ffuf" in res["missing"]
    assert res["installed"] == ["certutil", "ffuf"]
    assert "ffuf" in res["installed"]

    # Verify apt install command was dispatched
    apt_cmds = [c for c in comp.commands_executed if "apt-get install" in c]
    assert len(apt_cmds) >= 1
    assert "certutil ffuf" in apt_cmds[0]
    assert "ffuf" in apt_cmds[0]


@pytest.mark.asyncio
async def test_bootstrap_wait_for_port_open_success():
    comp = _MockBootstrapComputer(port_open_attempts=2)
    engine = WorkstationBootstrapEngine(comp)

    is_open = await engine.wait_for_port_open(
        host="127.0.0.1", port=8080, timeout=2.0, interval=0.01, workspace_id="ws-1"
    )
    assert is_open is True
    assert comp.port_attempts >= 2


@pytest.mark.asyncio
async def test_bootstrap_wait_for_port_open_timeout():
    comp = _MockBootstrapComputer(port_open_attempts=999)
    engine = WorkstationBootstrapEngine(comp)

    is_open = await engine.wait_for_port_open(
        host="127.0.0.1", port=8080, timeout=0.05, interval=0.01, workspace_id="ws-1"
    )
    assert is_open is False


@pytest.mark.asyncio
async def test_bootstrap_setup_proxy_ca_trust_success():
    comp = _MockBootstrapComputer(port_open_attempts=1)
    engine = WorkstationBootstrapEngine(comp)

    res = await engine.setup_proxy_ca_trust(
        workspace_id="ws-1", proxy_host="127.0.0.1", proxy_port=8080, wait_timeout=1.0
    )
    assert res["proxy_live"] is True
    assert res["cert_fetched"] is True
    assert res["os_imported"] is True
    assert res["nss_imported"] is True
    assert res["verified"] is True

    # Verify certutil import was dispatched into nssdb
    nss_cmds = [c for c in comp.commands_executed if "certutil -d sql:/root/.pki/nssdb" in c]
    assert len(nss_cmds) >= 1


@pytest.mark.asyncio
async def test_bootstrap_setup_proxy_ca_trust_port_closed():
    comp = _MockBootstrapComputer(port_open_attempts=999)
    engine = WorkstationBootstrapEngine(comp)

    res = await engine.setup_proxy_ca_trust(
        workspace_id="ws-1", proxy_host="127.0.0.1", proxy_port=8080, wait_timeout=0.02
    )
    assert res["proxy_live"] is False
    assert res["cert_fetched"] is False
    assert res["verified"] is False


@pytest.mark.asyncio
async def test_agent_run_mission_triggers_bootstrap_audit():
    comp = _MockBootstrapComputer(missing_binaries=[])
    # Attach mock terminal and screenshot to support observe()
    comp.terminal = AsyncMock(return_value=MagicMock(exit_code=0, stdout="test terminal output", stderr=""))
    comp.screenshot = AsyncMock(return_value=ScreenObservation(screenshot_base64="", width=1280, height=800))
    comp.gui_action = AsyncMock(return_value=ScreenObservation())
    comp.status = AsyncMock(return_value=MagicMock(open_applications=[], running_processes=[], active_application="", working_directory="/home/daytona", status="RUNNING"))
    comp.list_files = AsyncMock(return_value=[])
    comp.git_action = AsyncMock(return_value=MagicMock(stdout="clean", branch="main", is_clean=True, exit_code=0))

    agent = ComputerUseAgent(
        computer_provider=comp,
        max_actions=2,
    )

    traces = await agent.run_mission(
        workspace_id="ws-1",
        goal="Perform security inspection of local network",
        steps=1,
    )

    assert agent._bootstrap_performed is True
    # Verify bootstrap dependency check probe was run
    probe_cmds = [c for c in comp.commands_executed if "MISSING:" in c]
    assert len(probe_cmds) >= 1
