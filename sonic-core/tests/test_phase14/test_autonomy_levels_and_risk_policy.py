"""
Tests for Phase 14: Computer Autonomy Levels & Security Policies.
"""

import pytest
from sonic.computer.models import ApplicationPolicy
from sonic.computer_use.models import ComputerAutonomyLevel, EngineeringMissionMode


def test_autonomy_levels_and_policy_invariants():
    # 1. Verify Autonomy Levels
    assert ComputerAutonomyLevel.L0_MANUAL.value == "L0_MANUAL"
    assert ComputerAutonomyLevel.L1_ASSISTED.value == "L1_ASSISTED"
    assert ComputerAutonomyLevel.L2_SUPERVISED_AUTONOMOUS.value == "L2_SUPERVISED_AUTONOMOUS"
    assert ComputerAutonomyLevel.L3_AUTONOMOUS.value == "L3_AUTONOMOUS"

    # 2. Verify Mission Modes
    assert EngineeringMissionMode.ENGINEERING_MODE.value == "ENGINEERING_MODE"
    assert EngineeringMissionMode.SECURITY_RESEARCH_MODE.value == "SECURITY_RESEARCH_MODE"
    assert EngineeringMissionMode.DEBUG_MODE.value == "DEBUG_MODE"
    assert EngineeringMissionMode.GENERAL_ENGINEERING_MODE.value == "GENERAL_ENGINEERING_MODE"

    # 3. Verify Policy
    policy = ApplicationPolicy()
    assert policy.is_package_allowed("code-server")[0] is True
    assert policy.is_package_allowed("cryptominer")[0] is False
