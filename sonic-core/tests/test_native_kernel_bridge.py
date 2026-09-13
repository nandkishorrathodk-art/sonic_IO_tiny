"""Tests for the SONIC Native Rust Kernel Bridge."""

import json
from unittest.mock import MagicMock, patch
import pytest

from sonic.kernel.native_bridge import NativeKernelClient, NativeKernelVerdict


def test_native_kernel_client_graceful_absence():
    """Client reports is_available=False when binary is absent."""
    client = NativeKernelClient(binary_path="/nonexistent/sonic-kernel")
    # Even if path is set, if it does not execute cleanly it returns None
    assert client.health() is None
    assert client.authorize("TERMINAL_EXEC", "ls") is None


def test_native_kernel_authorize_rpc():
    """Client correctly parses NativeKernelVerdict from JSON-RPC output."""
    client = NativeKernelClient(binary_path="/mock/sonic-kernel")

    mock_resp = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "verdict": "Allow",
            "reason": "Action permitted within safe envelope.",
            "action_type": "TERMINAL_EXEC",
            "audit_id": "audit-001",
            "seal_intact": True,
            "timestamp": "2026-09-11T12:00:00Z",
        },
    }

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(mock_resp) + "\n",
            stderr="",
        )

        verdict = client.authorize("TERMINAL_EXEC", "nmap -sV target", is_isolated=True)
        assert verdict is not None
        assert verdict.is_allowed
        assert verdict.verdict == "Allow"
        assert verdict.seal_intact
        assert verdict.audit_id == "audit-001"


def test_native_kernel_perception_rpc():
    """Client correctly queries perception fusion."""
    client = NativeKernelClient(binary_path="/mock/sonic-kernel")

    mock_resp = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "url": "https://ctf.local",
            "title": "Login",
            "page_state": "flag_captured",
            "controls": [{"control_id": "input-0", "tag": "input", "role": "textbox", "label": "flag", "selector": "input[name='flag']"}],
            "visible_text": ["flag{test_win}"],
            "screenshot_hash": "abc123hash",
        },
    }

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(mock_resp) + "\n",
            stderr="",
        )

        state = client.fuse_perception("https://ctf.local", "Login", "<html>flag{test_win}</html>")
        assert state is not None
        assert state["page_state"] == "flag_captured"
        assert len(state["controls"]) == 1
        assert state["controls"][0]["label"] == "flag"


def test_native_kernel_desktop_snapshot_and_action_check_rpc():
    """Client publishes whole-computer state and checks snapshot freshness."""
    client = NativeKernelClient(binary_path="/mock/sonic-kernel")
    responses = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "version": 7,
                "width": 1280,
                "height": 800,
                "active_window": "Terminal",
                "windows": ["Terminal", "Desktop"],
                "processes": ["wm", "terminal"],
                "publish_latency_ns": 900,
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "allowed": False,
                "reason": "stale desktop snapshot",
                "current_version": 8,
            },
        },
    ]

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps(responses[0]) + "\n", stderr=""),
            MagicMock(returncode=0, stdout=json.dumps(responses[1]) + "\n", stderr=""),
        ]
        snapshot = client.desktop_snapshot(
            width=1280,
            height=800,
            active_window="Terminal",
            windows=["Terminal", "Desktop"],
            processes=["wm", "terminal"],
            visible_text=["Ready"],
            controls=["prompt"],
            screenshot="frame-a",
        )
        check = client.desktop_action_check(7)

    assert snapshot["version"] == 7
    assert snapshot["active_window"] == "Terminal"
    assert check["allowed"] is False


def test_native_kernel_evaluate_probe_rpc():
    """Client correctly queries empirical probe evaluation."""
    client = NativeKernelClient(binary_path="/mock/sonic-kernel")

    mock_resp = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "experiment_id": "exp-1",
            "hypothesis_id": "hyp-1",
            "specialist": "Pwn",
            "status": "completed",
            "baseline_observation": "Denied",
            "probe_observation": "flag{pwn_flag}",
            "behavioral_difference_detected": True,
            "difference_description": "Critical leak detected",
            "secret_or_flag_detected": True,
            "evidence_payload": {"extracted_artifact": "flag{pwn_flag}"},
        },
    }

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(mock_resp) + "\n",
            stderr="",
        )

        res = client.evaluate_probe("pwn", "Denied", "flag{pwn_flag}")
        assert res is not None
        assert res["behavioral_difference_detected"] is True
        assert res["secret_or_flag_detected"] is True
        assert res["evidence_payload"]["extracted_artifact"] == "flag{pwn_flag}"


def test_action_broker_native_kernel_deny_blocks_execution():
    """ActionBroker blocks execution and returns exit code 126 when NativeKernel denies."""
    from sonic.computer_use.models import ActionExecutionStatus
    from sonic.kernel.action_broker import ActionBroker

    mock_native_client = MagicMock()
    mock_native_client.authorize.return_value = NativeKernelVerdict(
        verdict="Deny",
        reason="Target IP 10.0.0.1 in forbidden CIDR egress range",
        action_type="TERMINAL_EXEC",
        audit_id="audit-deny-001",
        seal_intact=True,
        timestamp="2026-09-11T12:00:00Z",
    )

    mock_safety_kernel = MagicMock()
    broker = ActionBroker(
        safety_kernel=mock_safety_kernel,
        native_kernel_client=mock_native_client,
        tenant_id="test-tenant",
    )

    mock_provider = MagicMock()
    res = broker.execute(
        action_type="TERMINAL_COMMAND",
        parameters={"command": "curl http://10.0.0.1/admin"},
        provider=mock_provider,
    )

    assert res.status == ActionExecutionStatus.BLOCKED
    assert res.exit_code == 126
    assert "[NativeKernel Deny]" in res.stderr
    assert "forbidden CIDR egress" in res.stderr
    # Must fail-closed before provider execution
    mock_provider.execute.assert_not_called()
    # Python safety kernel does not even need to run if hardware/native gate denies
    mock_safety_kernel.authorize.assert_not_called()


def test_action_broker_native_kernel_require_approval_blocks_when_unapproved():
    """ActionBroker blocks approval-required actions unless approved=True."""
    from sonic.computer_use.models import ActionExecutionStatus
    from sonic.kernel.action_broker import ActionBroker

    mock_native_client = MagicMock()
    mock_native_client.authorize.return_value = NativeKernelVerdict(
        verdict="RequireApproval",
        reason="Potentially destructive file deletion: rm -rf",
        action_type="TERMINAL_EXEC",
        audit_id="audit-appr-001",
        seal_intact=True,
        timestamp="2026-09-11T12:00:00Z",
    )

    mock_safety_kernel = MagicMock()
    broker = ActionBroker(
        safety_kernel=mock_safety_kernel,
        native_kernel_client=mock_native_client,
        tenant_id="test-tenant",
    )

    mock_provider = MagicMock()
    # 1. Unapproved -> Blocked
    res_blocked = broker.execute(
        action_type="TERMINAL_COMMAND",
        parameters={"command": "rm -rf /tmp/test"},
        provider=mock_provider,
        approved=False,
    )
    assert res_blocked.status == ActionExecutionStatus.BLOCKED
    assert res_blocked.exit_code == 126
    assert "[NativeKernel ApprovalRequired]" in res_blocked.stderr
    mock_provider.execute.assert_not_called()

    # 2. Approved -> Passes native pre-screening, proceeds to SafetyKernel
    mock_auth = MagicMock(verdict=MagicMock(value="allow"), is_allowed=True)
    mock_safety_kernel.authorize.return_value = mock_auth
    mock_provider.execute.return_value = MagicMock(exit_code=0, stdout="deleted", stderr="")

    res_approved = broker.execute(
        action_type="TERMINAL_COMMAND",
        parameters={"command": "rm -rf /tmp/test"},
        provider=mock_provider,
        approved=True,
    )
    assert res_approved.status == ActionExecutionStatus.SUCCEEDED
    mock_provider.execute.assert_called_once()


def test_action_broker_native_kernel_seal_tampered_fails_closed():
    """ActionBroker fails-closed immediately if NativeKernel reports seal_intact=False."""
    from sonic.computer_use.models import ActionExecutionStatus
    from sonic.kernel.action_broker import ActionBroker

    mock_native_client = MagicMock()
    mock_native_client.authorize.return_value = NativeKernelVerdict(
        verdict="Allow",
        reason="Tamper detected in kernel safety registry",
        action_type="TERMINAL_EXEC",
        audit_id="audit-tamper-001",
        seal_intact=False,
        timestamp="2026-09-11T12:00:00Z",
    )

    broker = ActionBroker(
        native_kernel_client=mock_native_client,
        tenant_id="test-tenant",
    )

    mock_provider = MagicMock()
    res = broker.execute(
        action_type="TERMINAL_COMMAND",
        parameters={"command": "ls /home/sonic/workspace"},
        provider=mock_provider,
    )

    assert res.status == ActionExecutionStatus.BLOCKED
    assert res.exit_code == 126
    assert "seal tampered" in res.stderr.lower()
    mock_provider.execute.assert_not_called()


def test_native_kernel_persistent_daemon_streaming():
    """Client streams requests over persistent daemon pipe without process-per-call overhead."""
    client = NativeKernelClient(binary_path="/mock/sonic-kernel")
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.stdin = MagicMock()
    mock_proc.stdout = MagicMock()
    mock_proc.stdout.readline.return_value = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"status": "healthy", "version": "0.2.0"},
    }) + "\n"

    with patch("subprocess.Popen", return_value=mock_proc), \
         patch("pathlib.Path.is_file", return_value=True):
        res = client.health()
        assert res is not None
        assert res["status"] == "healthy"
        assert mock_proc.stdin.write.called
        assert mock_proc.stdout.readline.called

    client.close()
    assert mock_proc.terminate.called

