"""
Tests for Phase 5: Subordinated Specialist Pool
================================================
Verifies:
1. Specialists execute bounded experiments without independent goal drift.
2. Recon, Web, API, Auth, and Logic specialists test hypotheses and detect behavioral differences.
3. SpecialistPool dispatching and EventBus event delivery.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sonic.agents.specialist import (
    APISpecialist,
    AuthSpecialist,
    LogicSpecialist,
    ReconSpecialist,
    SpecialistPool,
    SpecialistResult,
    WebSpecialist,
)
from sonic.brain.experiment import Experiment
from sonic.kernel.action_broker import ActionBroker
from sonic.kernel.event_bus import EventBus, EventTopic
from sonic.safety.kernel import SafetyKernel


@pytest.mark.no_live_infra
def test_recon_specialist_execution():
    kernel = SafetyKernel(tenant_id="test-tenant")
    broker = ActionBroker(safety_kernel=kernel, tenant_id="test-tenant")
    bus = EventBus()

    mock_provider = MagicMock()
    mock_exec = MagicMock()
    mock_exec.exit_code = 0
    mock_exec.stdout = "HTTP/1.1 200 OK\nServer: nginx/1.24\nContent-Type: text/html\n"
    mock_exec.stderr = ""
    mock_provider.execute.return_value = mock_exec

    recon = ReconSpecialist(action_broker=broker, event_bus=bus, provider=mock_provider)

    exp = Experiment(
        hypothesis_id="hyp-101",
        target_asset="http://localhost/api",
        specialist_type="recon",
        action_intent="Discover server banner",
    )

    res: SpecialistResult = recon.run_experiment(exp)

    assert res.status == "completed"
    assert res.behavioral_difference_detected is True
    assert "Server: nginx" in res.probe_observation
    assert len(bus.get_events(EventTopic.EXPERIMENT_RESULT)) == 1


@pytest.mark.no_live_infra
def test_auth_specialist_behavioral_diff_detection():
    kernel = SafetyKernel(tenant_id="test-tenant")
    broker = ActionBroker(safety_kernel=kernel, tenant_id="test-tenant")
    bus = EventBus()

    auth_spec = AuthSpecialist(action_broker=broker, event_bus=bus)

    # Case A: Identity cross detected (Different from baseline)
    exp_leak = Experiment(
        hypothesis_id="hyp-idor",
        target_asset="/api/users/42",
        specialist_type="auth",
        action_intent="Test IDOR by swapping token",
        parameters={
            "baseline": "HTTP 403 Forbidden: Access denied",
            "simulated_probe": "HTTP 200 OK: User 42 Profile Data",
        },
    )
    res_leak = auth_spec.run_experiment(exp_leak)
    assert res_leak.behavioral_difference_detected is True
    assert "crossed authorization boundary" in res_leak.difference_description

    # Case B: Gating properly enforced (Same as baseline)
    exp_safe = Experiment(
        hypothesis_id="hyp-idor-safe",
        target_asset="/api/users/42",
        specialist_type="auth",
        action_intent="Test IDOR on hardened endpoint",
        parameters={
            "baseline": "HTTP 403 Forbidden: Access denied",
            "simulated_probe": "HTTP 403 Forbidden: Access denied",
        },
    )
    res_safe = auth_spec.run_experiment(exp_safe)
    assert res_safe.behavioral_difference_detected is False


@pytest.mark.no_live_infra
def test_specialist_pool_dispatch():
    kernel = SafetyKernel(tenant_id="test-tenant")
    broker = ActionBroker(safety_kernel=kernel, tenant_id="test-tenant")
    bus = EventBus()

    pool = SpecialistPool(action_broker=broker, event_bus=bus)

    exp_logic = Experiment(
        hypothesis_id="hyp-logic",
        target_asset="/orders/checkout",
        specialist_type="logic",
        action_intent="Test race condition on coupon redemption",
        parameters={
            "baseline": "Coupon redeemed once: Balance $90",
            "simulated_probe": "Coupon redeemed twice: Balance $80",
        },
    )

    res = pool.execute_experiment(exp_logic)
    assert res.specialist_type == "logic"
    assert res.behavioral_difference_detected is True
    assert "Unexpected state transition" in res.difference_description
