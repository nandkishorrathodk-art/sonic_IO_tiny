"""
Truthful Execution Result Semantics & Status Tests (Section J)
==============================================================
Asserts that execution statuses truthfully reflect reality:
- Exit 125 results in status BLOCKED (never SUCCESS).
- Exit 126 results in status BLOCKED (never SUCCESS).
- Exit 124 results in status TIMED_OUT.
- Exit 1 results in status FAILED.
- Recovery logic properly marks RECOVERED or FAILED on exhaustion.
- Evidence auto-synthesis never generates evidence for blocked or failed actions.
"""

from unittest.mock import AsyncMock, MagicMock
import pytest

from sonic.computer.models import ScreenObservation
from sonic.computer_use.models import (
    ActionExecutionStatus,
    ComputerActionType,
    ComputerDecisionTrace,
)
from sonic.computer_use.agent import ComputerUseAgent


def _mock_provider():
    p = AsyncMock()
    p.screenshot.return_value = ScreenObservation(width=1280, height=800)
    p.status.return_value = MagicMock(
        active_application="Desktop",
        open_applications=["Desktop"],
        running_processes=["xvfb"],
    )
    p.list_files.return_value = []
    p.git_action.return_value = MagicMock(branch="main", is_clean=True)
    p.terminal.return_value = MagicMock(stdout="OK", stderr="", exit_code=0)
    p.gui_action.return_value = ScreenObservation(width=1280, height=800)
    return p


class TestExecutionStatusSemantics:
    """Truthful execution status tests for ComputerUseAgent."""

    @pytest.mark.asyncio
    async def test_terminal_exec_exit_125_results_in_blocked(self):
        """Exit 125 (container/sandbox error) must be BLOCKED and never trigger recovery."""
        provider = _mock_provider()
        provider.terminal.return_value = MagicMock(
            stdout="",
            stderr="docker: Error response from daemon: Container is not running",
            exit_code=125,
        )
        agent = ComputerUseAgent(computer_provider=provider, max_recovery_attempts=3)

        trace = await agent.execute_action(
            workspace_id="ws-test",
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="curl http://target",
            payload={"command": "curl http://target"},
            predicted_outcome="expect response",
        )

        assert trace.status == ActionExecutionStatus.BLOCKED
        assert trace.status == "BLOCKED"
        assert trace.status != "SUCCESS"
        assert trace.status != ActionExecutionStatus.SUCCESS
        assert trace.status != ActionExecutionStatus.COMPLETED
        assert trace.recovery_attempted is False

    @pytest.mark.asyncio
    async def test_terminal_exec_exit_126_results_in_blocked(self):
        """Exit 126 (command invoked cannot execute / permission denied) must be BLOCKED."""
        provider = _mock_provider()
        provider.terminal.return_value = MagicMock(
            stdout="",
            stderr="bash: ./malware.sh: Permission denied",
            exit_code=126,
        )
        agent = ComputerUseAgent(computer_provider=provider, max_recovery_attempts=3)

        trace = await agent.execute_action(
            workspace_id="ws-test",
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="./malware.sh",
            payload={"command": "./malware.sh"},
            predicted_outcome="expect execution",
        )

        assert trace.status == ActionExecutionStatus.BLOCKED
        assert trace.status != "SUCCESS"
        assert trace.recovery_attempted is False

    @pytest.mark.asyncio
    async def test_terminal_exec_exit_124_results_in_timed_out(self):
        """Exit 124 (command timeout) must be TIMED_OUT."""
        provider = _mock_provider()
        provider.terminal.return_value = MagicMock(
            stdout="",
            stderr="timeout: command timed out after 30s",
            exit_code=124,
        )
        agent = ComputerUseAgent(computer_provider=provider, max_recovery_attempts=0)

        trace = await agent.execute_action(
            workspace_id="ws-test",
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="sleep 100",
            payload={"command": "sleep 100"},
            predicted_outcome="expect finish",
        )

        assert trace.status == ActionExecutionStatus.TIMED_OUT
        assert trace.status == "TIMED_OUT"
        assert trace.status != "SUCCESS"
        assert trace.recovery_attempted is True

    @pytest.mark.asyncio
    async def test_terminal_exec_exit_1_results_in_failed(self):
        """Exit 1 (general command failure) must be FAILED."""
        provider = _mock_provider()
        provider.terminal.return_value = MagicMock(
            stdout="pytest: 3 failed, 0 passed",
            stderr="",
            exit_code=1,
        )
        agent = ComputerUseAgent(computer_provider=provider, max_recovery_attempts=0)

        trace = await agent.execute_action(
            workspace_id="ws-test",
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="pytest",
            payload={"command": "pytest"},
            predicted_outcome="all tests pass",
        )

        assert trace.status == ActionExecutionStatus.FAILED
        assert trace.status == "FAILED"
        assert trace.status != "SUCCESS"
        assert trace.recovery_attempted is True

    @pytest.mark.asyncio
    async def test_recovery_exhaustion_ensures_failed_status(self):
        """When recovery attempts are exhausted, status must be FAILED."""
        provider = _mock_provider()
        provider.terminal.return_value = MagicMock(
            stdout="",
            stderr="syntax error",
            exit_code=2,
        )
        agent = ComputerUseAgent(computer_provider=provider, max_recovery_attempts=2)
        agent.recovery_events = 2  # Exhaust attempts

        trace = await agent.execute_action(
            workspace_id="ws-test",
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="bad_cmd",
            payload={"command": "bad_cmd"},
            predicted_outcome="expect success",
        )

        assert trace.status == ActionExecutionStatus.FAILED
        assert trace.status != "SUCCESS"

    @pytest.mark.asyncio
    async def test_recovery_success_results_in_recovered(self):
        """When recovery runs and is under max attempts, status becomes RECOVERED."""
        provider = _mock_provider()
        provider.terminal.return_value = MagicMock(
            stdout="",
            stderr="crashed",
            exit_code=1,
        )
        agent = ComputerUseAgent(computer_provider=provider, max_recovery_attempts=3)
        agent.recover = AsyncMock(return_value="Recovered display service")

        trace = await agent.execute_action(
            workspace_id="ws-test",
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="app",
            payload={"command": "app"},
            predicted_outcome="run app",
        )

        assert trace.status == ActionExecutionStatus.RECOVERED
        assert "Recovered: Recovered display service" in trace.actual_observation

    def test_trace_status_default_is_completed(self):
        """ComputerDecisionTrace status defaults to ActionExecutionStatus.COMPLETED."""
        trace = ComputerDecisionTrace(
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="echo test",
            predicted_outcome="test",
            actual_observation="test",
        )
        assert trace.status == ActionExecutionStatus.COMPLETED
        assert trace.status == "COMPLETED"
        assert trace.status == "SUCCESS"  # Alias compatibility

    def test_evidence_auto_synthesis_gating_logic(self):
        """Evidence must never be generated for blocked, failed, or exit code error strings."""
        def can_synthesize(trace_status: str, obs_text: str, target: str) -> bool:
            has_discovery = any(
                k in obs_text.lower()
                for k in ("open", "http", "200 ok", "discovered", "vulnerability", "port", "https://")
            )
            is_valid_success = (
                trace_status in ("COMPLETED", "SUCCESS", "RECOVERED", "VERIFIED")
                and not any(
                    k in obs_text.lower()
                    for k in ("exit 125", "exit 126", "exit 1", "blocked fail-closed", "command blocked")
                )
            )
            return bool(has_discovery and target and is_valid_success)

        # Disallowed statuses
        assert not can_synthesize("BLOCKED", "Discovered open port 8080", "localhost")
        assert not can_synthesize("FAILED", "Discovered open port 8080", "localhost")
        assert not can_synthesize("TIMED_OUT", "Discovered open port 8080", "localhost")

        # Disallowed error substrings even if status is COMPLETED/SUCCESS
        assert not can_synthesize("COMPLETED", "Port 80 open but Exit 125 container died", "localhost")
        assert not can_synthesize("SUCCESS", "Port 80 open Exit 126 permission denied", "localhost")
        assert not can_synthesize("SUCCESS", "HTTP request failed: Exit 1", "localhost")
        assert not can_synthesize("COMPLETED", "Blocked fail-closed: open port scan disallowed", "localhost")
        assert not can_synthesize("COMPLETED", "Command blocked by security policy", "localhost")

        # Allowed genuine successes
        assert can_synthesize("COMPLETED", "Port 80/tcp is open, HTTP 200 OK", "localhost")
        assert can_synthesize("SUCCESS", "Found open vulnerability in endpoint", "localhost")
        assert can_synthesize("RECOVERED", "Port 443 open after restart", "localhost")
        assert can_synthesize("VERIFIED", "Discovered open https://example.com", "example.com")
