"""
Tests for Phase 13: Computer Models, State & Application Policy.
"""

import pytest
from sonic.computer.models import (
    ApplicationPolicy,
    ComputerAuditEvent,
    ComputerProfile,
    ComputerRiskLevel,
    ComputerSession,
    ComputerSessionMode,
    ComputerState,
    ComputerWorkspace,
    ComputerWorkspaceStatus,
    ComputerWorkspaceType,
    GUIAction,
    GUIActionType,
    ScreenObservation,
)


def test_computer_workspace_and_state_models():
    ws = ComputerWorkspace(
        tenant_id="tenant-alpha",
        engagement_id="eng-alpha",
        workspace_type=ComputerWorkspaceType.MISSION_COMPUTER,
        profile=ComputerProfile.KALI_SECURITY,
    )
    assert ws.status == ComputerWorkspaceStatus.READY
    assert ws.workspace_type == ComputerWorkspaceType.MISSION_COMPUTER
    assert "desktop" in ws.capabilities
    assert "ide" in ws.capabilities

    state = ComputerState(
        workspace_id=ws.id,
        tenant_id=ws.tenant_id,
        active_application="code-server",
        open_applications=["Desktop", "Terminal", "code-server"],
        active_window="code-server",
    )
    assert state.active_application == "code-server"
    assert len(state.open_applications) == 3


def test_application_policy_rules():
    policy = ApplicationPolicy()

    # Allowed packages
    ok_nmap, _ = policy.is_package_allowed("nmap")
    ok_git, _ = policy.is_package_allowed("git")
    ok_ffuf, _ = policy.is_package_allowed("ffuf")
    ok_burp, _ = policy.is_package_allowed("burpsuite")

    assert ok_nmap is True
    assert ok_git is True
    assert ok_ffuf is True
    assert ok_burp is True

    # Forbidden packages
    bad_miner, reason = policy.is_package_allowed("cryptominer")
    bad_bot, _ = policy.is_package_allowed("ddos-bot")
    bad_relay, _ = policy.is_package_allowed("tor-relay")

    assert bad_miner is False
    assert bad_bot is False
    assert bad_relay is False
    assert "prohibited" in reason.lower()
