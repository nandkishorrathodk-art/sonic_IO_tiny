"""
Tests for Phase 12: Stop Intelligence & Research Modes.
"""

import pytest
from sonic.researcher.manager import ResearchManager
from sonic.researcher.models import ResearchMode, StopReason


def test_goal_satisfied_stopping_condition():
    mgr = ResearchManager(
        mission_id="m-stop-1",
        tenant_id="t-stop-1",
        goal="Audit Admin Endpoint",
        mode=ResearchMode.AUTONOMOUS,
    )
    q1 = mgr.add_question("Is admin endpoint protected by auth?")
    mgr.resolve_question(q1.id, "No, unauthenticated access allowed.")

    stopped, reason, _ = mgr.check_stop_condition(
        budget_used=2.0, max_budget=20.0, time_elapsed_s=10.0, max_time_s=120.0
    )
    assert stopped is True
    assert reason == StopReason.GOAL_SATISFIED


def test_budget_exhaustion_stopping_condition():
    mgr = ResearchManager(
        mission_id="m-stop-2",
        tenant_id="t-stop-2",
        goal="Deep Fuzzing Mission",
        mode=ResearchMode.ASSISTED,
    )
    mgr.add_question("Can parameter X be fuzzed?")

    stopped, reason, _ = mgr.check_stop_condition(
        budget_used=25.0, max_budget=20.0, time_elapsed_s=30.0, max_time_s=120.0
    )
    assert stopped is True
    assert reason == StopReason.BUDGET_EXHAUSTED
