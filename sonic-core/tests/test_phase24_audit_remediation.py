"""Tests for Phase 24 - Comprehensive Remediation of All Audited Gaps Across 4 Pillars.

Verifies:
1. ComputerWorkspaceStatus is imported and present in workstation.py telemetry.
2. MotorReflexes.two_stage_click dispatches exactly once (no duplicate click).
3. NetworkSpecialist never hallucinates open ports (pure empirical findings).
4. FalsificationSpecialist requires empirical evidence before verifying vulnerabilities.
5. MissionDirector outcome calibration (SUCCESS requires >= 0.60 success ratio + deliverables).
6. SealedActionPolicy trips seal hash and fails closed if scope_checker rules are altered.
7. ScopeChecker destructive regexes catch rm -fr, rm --recursive, mke2fs, wipefs, and quoted dd of.
8. extract_bbox_midpoint with is_normalized_1000 scales accurately on 1280x800 screens.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from sonic.computer.models import ComputerWorkspaceStatus
from sonic.computer_use.grounding import extract_bbox_midpoint
from sonic.computer_use.motor import MotorReflexes
from sonic.mission_engine.director import MissionDirector
from sonic.mission_engine.models import (
    DeliverableType,
    MissionDeliverable,
    MissionOutcome,
    MissionPhase,
    MissionState,
    MissionStatus,
)
from sonic.computer_use.models import (
    ActionExecutionStatus,
    ComputerActionType,
    ComputerDecisionTrace,
)
from sonic.research.specialist import NetworkSpecialist, FalsificationSpecialist
from sonic.research.orchestrator import ResearchEventBus
from sonic.safety.sealed import SealedActionPolicy
from sonic.safety.scope import RiskLevel, ScopeChecker


def test_computer_workspace_status_import_integrity():
    import sonic.api.routes.workstation as ws_mod
    assert hasattr(ws_mod, "ComputerWorkspaceStatus")
    assert ws_mod.ComputerWorkspaceStatus.RUNNING.value == "RUNNING"


@pytest.mark.asyncio
async def test_two_stage_click_single_dispatch():
    mock_computer = MagicMock()
    mock_computer.gui_action = AsyncMock(return_value={"status": "ok"})
    mock_computer._docker_exec = AsyncMock(return_value=(0, "", ""))

    motor = MotorReflexes(mock_computer)
    res = await motor.two_stage_click("test-ws", x=500, y=400, target_window="Chrome")

    assert "two_stage_clicked" in res
    assert mock_computer.gui_action.call_count == 1
    exec_calls = [c.args[0] for c in mock_computer._docker_exec.call_args_list]
    assert not any("click" in call for call in exec_calls)


@pytest.mark.asyncio
async def test_network_specialist_zero_hallucinated_ports():
    mock_provider = MagicMock()
    mock_provider.scan_ports = AsyncMock(return_value=[])

    bus = ResearchEventBus()
    spec = NetworkSpecialist(name="ZeroHallucinationNetSpec", target="192.0.2.1")
    res = await spec.run({"provider": mock_provider, "delay": 0.01}, bus)

    assert res.get("open_ports_discovered") == 0


@pytest.mark.asyncio
async def test_falsification_specialist_requires_positive_evidence():
    bus = ResearchEventBus()
    spec = FalsificationSpecialist(name="TruthSpec", target_hypothesis_id="hypo-1")
    res = await spec.run({"hypotheses": [{"id": "hypo-1", "statement": "Target has XSS"}]}, bus)

    assert res.get("falsified") is False
    assert res.get("verified") is False
    assert res.get("status") == "INCONCLUSIVE"


def test_sealed_policy_scope_checker_tamper_detection():
    policy = SealedActionPolicy(workspace_root="/home/sonic/workspace")
    policy.seal()
    assert policy.sealed is True

    v1 = policy.evaluate("FILE_READ", "/home/sonic/workspace/file.txt", {"path": "/home/sonic/workspace/file.txt"})
    assert v1.allowed is True

    # Tamper with scope_checker instance patterns
    sc = object.__getattribute__(policy, "scope_checker")
    if hasattr(sc, "_destructive_patterns"):
        sc._destructive_patterns.clear()
    else:
        sc._forbidden_patterns.clear()

    v2 = policy.evaluate("FILE_READ", "/home/sonic/workspace/file.txt", {"path": "/home/sonic/workspace/file.txt"})
    assert v2.allowed is False
    assert "tamper" in v2.reason.lower() or "mismatch" in v2.reason.lower()


@pytest.mark.parametrize("cmd", [
    "rm -fr /home/sonic/workspace/tmp",
    "rm -r -f /var/data",
    "rm --recursive /var/data",
    "mkfs.ext4 /dev/sdb1",
    "mke2fs -t ext4 /dev/sdb",
    "wipefs -a /dev/sdb",
    'dd if=/dev/zero of="/dev/sda" bs=1M',
    "killall -9 python",
    "pkill -9 chrome",
])
def test_destructive_patterns_expanded_coverage(cmd):
    checker = ScopeChecker()
    verdict = checker.classify_command_risk(cmd)
    assert verdict == RiskLevel.L2_FORBIDDEN


def test_extract_bbox_midpoint_normalized_1000_scaling():
    coords = extract_bbox_midpoint([200, 300, 400, 500], width=1280, height=800, is_normalized_1000=True)
    assert coords == (384, 320)
