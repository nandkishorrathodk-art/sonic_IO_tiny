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

