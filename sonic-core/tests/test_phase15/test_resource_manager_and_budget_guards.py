"""
Tests for Phase 15: Resource Manager & Budget Guards.
"""

import pytest
from sonic.mission_engine.resource_manager import MissionResourceManager


def test_resource_manager_budget_and_sandbox_guards():
    rm = MissionResourceManager(default_budget_dollars=10.0, max_sandboxes_per_mission=2)
    mission_id = "msn-test-01"

    rm.register_mission(mission_id, budget_dollars=10.0)

    # 1. Check sandbox allocations
    assert rm.can_allocate_sandbox(mission_id) is True
    assert rm.allocate_sandbox(mission_id, "sb-01") is True
    assert rm.allocate_sandbox(mission_id, "sb-02") is True
    assert rm.can_allocate_sandbox(mission_id) is False  # Limit reached (2)
    assert rm.allocate_sandbox(mission_id, "sb-03") is False

    rm.release_sandbox(mission_id, "sb-01")
    assert rm.can_allocate_sandbox(mission_id) is True

    # 2. Check spend & budget guards
    rm.record_spend(mission_id, dollars=4.50, tokens=5000, compute_seconds=30.0)
    assert rm.is_budget_exhausted(mission_id) is False

    rm.record_spend(mission_id, dollars=6.00)
    assert rm.is_budget_exhausted(mission_id) is True

    summary = rm.get_resource_summary(mission_id)
    assert summary["spent_dollars"] == 10.50
    assert summary["budget_exhausted"] is True
