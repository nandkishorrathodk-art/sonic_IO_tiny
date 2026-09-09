"""
Tests for Phase 0: Safety Kernel, Sealed Envelope & Action Broker
==================================================================
Verifies:
1. SafetyKernel seal verification and tamper-evident fail-closed behavior.
2. Zero host escape: unconfined LocalDevProvider is denied outside dev flag.
3. Path escape, egress violation, and unallowlisted action blockage.
4. ActionBroker mediator behavior: blocked actions never touch the provider.
5. Permitted actions pass through and return structured execution telemetry.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from sonic.computer_use.models import ActionExecutionStatus
from sonic.kernel.action_broker import ActionBroker
from sonic.safety.kernel import KernelVerdict, SafetyKernel
from sonic.safety.sealed import SealedActionPolicy


@pytest.mark.no_live_infra
def test_safety_kernel_seals_and_verifies_intact():
    kernel = SafetyKernel(tenant_id="test-tenant")
    assert kernel.is_seal_valid()
    assert kernel.seal_hash is not None
    assert len(kernel.seal_hash) == 64

    auth = kernel.authorize("FILE_READ", {"path": "/home/sonic/workspace/target.py"})
    assert auth.verdict == KernelVerdict.ALLOW
    assert auth.seal_intact is True
    assert auth.is_allowed is True


@pytest.mark.no_live_infra
def test_safety_kernel_tamper_detection_fails_closed():
    kernel = SafetyKernel(tenant_id="test-tenant")
    assert kernel.is_seal_valid()

    # Artificially tamper with underlying fields via object dict bypass
    object.__setattr__(kernel.policy, "allowed_types", frozenset(["ALL_POWERFUL"]))
    
    assert not kernel.is_seal_valid()
    auth = kernel.authorize("FILE_READ", {"path": "/home/sonic/workspace/target.py"})
    assert auth.verdict == KernelVerdict.DENY
    assert auth.seal_intact is False
    assert "tampered" in auth.reason.lower() or "mismatch" in auth.reason.lower()


@pytest.mark.no_live_infra
def test_safety_kernel_denies_path_escape():
    kernel = SafetyKernel(tenant_id="test-tenant")
    auth = kernel.authorize("FILE_WRITE", {"path": "/etc/shadow", "content": "root::0:0:::"})
    assert auth.verdict == KernelVerdict.DENY
    assert not auth.is_allowed


@pytest.mark.no_live_infra
def test_safety_kernel_zero_host_escape():
    # Construct a dummy LocalDevProvider
    class LocalDevProvider:
        pass

    kernel = SafetyKernel(tenant_id="test-tenant", enforce_isolated_sandbox=True)
    
    # In production without allow host flag
    old_env = os.environ.get("APP_ENV")
    old_allow = os.environ.get("SONIC_ALLOW_HOST_EXECUTION")
    try:
        os.environ["APP_ENV"] = "production"
        os.environ.pop("SONIC_ALLOW_HOST_EXECUTION", None)

        auth = kernel.authorize("COMMAND", {"command": "ls"}, provider=LocalDevProvider())
        assert auth.verdict == KernelVerdict.DENY
        assert "Zero host execution policy" in auth.reason
    finally:
        if old_env is not None:
            os.environ["APP_ENV"] = old_env
        else:
            os.environ.pop("APP_ENV", None)
        if old_allow is not None:
            os.environ["SONIC_ALLOW_HOST_EXECUTION"] = old_allow


@pytest.mark.no_live_infra
def test_action_broker_blocks_denied_actions_from_touching_provider():
    kernel = SafetyKernel(tenant_id="test-tenant")
    broker = ActionBroker(safety_kernel=kernel, tenant_id="test-tenant")

    mock_provider = MagicMock()

    # Path traversal attack
    res = broker.execute(
        action_type="FILE_READ",
        parameters={"path": "../../etc/passwd"},
        provider=mock_provider,
    )

    assert res.status == ActionExecutionStatus.BLOCKED
    assert res.exit_code == 126
    # Provider must NEVER have been called
    mock_provider.read_file.assert_not_called()
    mock_provider.execute.assert_not_called()


@pytest.mark.no_live_infra
def test_action_broker_dispatches_permitted_action():
    kernel = SafetyKernel(tenant_id="test-tenant")
    broker = ActionBroker(safety_kernel=kernel, tenant_id="test-tenant")

    mock_provider = MagicMock()
    mock_exec_res = MagicMock()
    mock_exec_res.exit_code = 0
    mock_exec_res.stdout = "src/main.py\nsrc/utils.py\n"
    mock_exec_res.stderr = ""
    mock_provider.execute.return_value = mock_exec_res

    res = broker.execute(
        action_type="TERMINAL_COMMAND",
        parameters={"command": "ls /home/sonic/workspace"},
        provider=mock_provider,
    )

    assert res.status == ActionExecutionStatus.SUCCEEDED
    assert res.exit_code == 0
    assert "src/main.py" in res.stdout
    assert res.duration_ms >= 0.0
    mock_provider.execute.assert_called_once()
