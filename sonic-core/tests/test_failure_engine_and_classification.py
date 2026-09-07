"""
Tests for SONIC Failure Engine & Classification (Sections 1-7 Rebuild)
======================================================================
Verifies:
1. ActionExecutionStatus truthful states and equality aliases (SUCCEEDED, COMPLETED, SUCCESS).
2. FailureClassification, StrategyState, and FailureRecord models.
3. failure_classifier semantic classification across exit codes, signals, and errors.
4. FailureBudgetTracker failure counting, strategy exhaustion, and substrate outage detection.
5. ComputerUseAgent cognitive reasoning context, UNKNOWN outputs, strategy tracking, and fail-safe execution.
"""

from unittest.mock import AsyncMock, MagicMock
import pytest

from sonic.computer.models import ScreenObservation
from sonic.computer_use.models import (
    ActionExecutionStatus,
    ComputerActionType,
    FailureClassification,
    FailureRecord,
    StrategyState,
)
from sonic.computer_use.agent import ComputerUseAgent
from sonic.research.failure_budget import FailureBudgetTracker
from sonic.research.failure_classifier import classify_failure


# =====================================================================
# 1. Models & Status Semantics Tests
# =====================================================================

class TestModelsAndStatusSemantics:
    """Verify Section 1 models, enums, and truthful status behavior."""

    def test_action_execution_status_truthful_states(self):
        """ActionExecutionStatus must include all required states."""
        assert ActionExecutionStatus.RUNNING == "RUNNING"
        assert ActionExecutionStatus.SUCCEEDED == "SUCCEEDED"
        assert ActionExecutionStatus.COMPLETED == "COMPLETED"
        assert ActionExecutionStatus.SUCCESS == "SUCCESS"
        assert ActionExecutionStatus.FAILED == "FAILED"
        assert ActionExecutionStatus.TIMED_OUT == "TIMED_OUT"
        assert ActionExecutionStatus.BLOCKED == "BLOCKED"
        assert ActionExecutionStatus.CANCELLED == "CANCELLED"
        assert ActionExecutionStatus.RECOVERED == "RECOVERED"
        assert ActionExecutionStatus.VERIFIED == "VERIFIED"
        assert ActionExecutionStatus.UNVERIFIED == "UNVERIFIED"

    def test_action_execution_status_aliases(self):
        """SUCCEEDED, COMPLETED, and SUCCESS must be mutually equal."""
        assert ActionExecutionStatus.SUCCEEDED == ActionExecutionStatus.COMPLETED
        assert ActionExecutionStatus.SUCCEEDED == ActionExecutionStatus.SUCCESS
        assert ActionExecutionStatus.COMPLETED == ActionExecutionStatus.SUCCESS
        assert ActionExecutionStatus.SUCCEEDED == "COMPLETED"
        assert ActionExecutionStatus.SUCCEEDED == "SUCCESS"
        assert ActionExecutionStatus.COMPLETED == "SUCCEEDED"
        assert ActionExecutionStatus.SUCCESS == "SUCCEEDED"
        assert "SUCCEEDED" == ActionExecutionStatus.COMPLETED
        assert "SUCCESS" == ActionExecutionStatus.SUCCEEDED

        # Must never equal failed/blocked
        assert ActionExecutionStatus.SUCCEEDED != ActionExecutionStatus.FAILED
        assert ActionExecutionStatus.SUCCESS != ActionExecutionStatus.BLOCKED
        assert ActionExecutionStatus.COMPLETED != ActionExecutionStatus.TIMED_OUT

    def test_failure_classification_values(self):
        """FailureClassification must have all 10 required failure types."""
        expected = {
            "TARGET_FAILURE",
            "TOOL_FAILURE",
            "PROVIDER_FAILURE",
            "SANDBOX_FAILURE",
            "NETWORK_FAILURE",
            "PERMISSION_FAILURE",
            "POLICY_BLOCK",
            "TIMEOUT",
            "INVALID_COMMAND",
            "UNKNOWN_FAILURE",
        }
        actual = {item.value for item in FailureClassification}
        assert expected == actual

    def test_strategy_state_values(self):
        """StrategyState must contain ACTIVE, DEGRADED, EXHAUSTED, ABANDONED."""
        assert StrategyState.ACTIVE == "ACTIVE"
        assert StrategyState.DEGRADED == "DEGRADED"
        assert StrategyState.EXHAUSTED == "EXHAUSTED"
        assert StrategyState.ABANDONED == "ABANDONED"

    def test_failure_record_model(self):
        """FailureRecord must populate required and default fields correctly."""
        rec = FailureRecord(
            tool="nmap",
            provider="docker",
            error_class=FailureClassification.TOOL_FAILURE,
            raw_error="nmap: command not found",
        )
        assert rec.tool == "nmap"
        assert rec.provider == "docker"
        assert rec.error_class == FailureClassification.TOOL_FAILURE
        assert rec.environment == "sandbox"
        assert rec.count == 1
        assert rec.raw_error == "nmap: command not found"
        assert rec.timestamp != ""


# =====================================================================
# 2. Failure Classifier Tests
# =====================================================================

class TestFailureClassifier:
    """Verify Section 2 failure classification rules."""

    def test_exit_125_provider_or_sandbox_failure(self):
        """Exit 125 maps to PROVIDER_FAILURE or SANDBOX_FAILURE."""
        c1, _ = classify_failure(125, stderr="docker: Error response from daemon: Container is not running")
        assert c1 in (FailureClassification.PROVIDER_FAILURE, FailureClassification.SANDBOX_FAILURE)

        c2, _ = classify_failure(125, stderr="cannot connect to the docker daemon")
        assert c2 == FailureClassification.PROVIDER_FAILURE

        c3, _ = classify_failure(1, stderr="container 83a71b... is not running")
        assert c3 == FailureClassification.SANDBOX_FAILURE

    def test_exit_126_policy_block_or_permission_denied(self):
        """Exit 126 maps to POLICY_BLOCK or PERMISSION_FAILURE."""
        c1, _ = classify_failure(126, stderr="bash: ./script.sh: Permission denied")
        assert c1 == FailureClassification.PERMISSION_FAILURE

        c2, _ = classify_failure(126, stderr="Command blocked by security policy")
        assert c2 == FailureClassification.POLICY_BLOCK

        c3, _ = classify_failure(126, stderr="Fail-closed: execution denied")
        assert c3 == FailureClassification.POLICY_BLOCK

    def test_exit_124_timeout(self):
        """Exit 124 maps to TIMEOUT."""
        c, reason = classify_failure(124, stderr="timeout: command timed out after 10s")
        assert c == FailureClassification.TIMEOUT
        assert "timed out" in reason.lower()

    def test_exit_127_tool_failure(self):
        """Exit 127 or missing binary maps to TOOL_FAILURE."""
        c1, _ = classify_failure(127, stderr="bash: ffuf: command not found", tool="ffuf")
        assert c1 == FailureClassification.TOOL_FAILURE

        c2, _ = classify_failure(1, stderr="nmap: no such file or directory", tool="nmap")
        assert c2 == FailureClassification.TOOL_FAILURE

    def test_network_failures(self):
        """Network unreachable, connection refused, DNS errors map to NETWORK_FAILURE."""
        errors = [
            "curl: (7) Failed to connect: Connection refused",
            "connect: Network is unreachable",
            "ping: connect: No route to host",
            "curl: (6) Could not resolve host: target.local (temporary failure in name resolution)",
        ]
        for err in errors:
            c, _ = classify_failure(1, stderr=err)
            assert c == FailureClassification.NETWORK_FAILURE, f"Failed for {err}"

    def test_target_failures(self):
        """HTTP 404, 500, 502, 503, connection reset, host down map to TARGET_FAILURE."""
        cases = [
            ("curl output", "HTTP/1.1 500 Internal Server Error"),
            ("curl output", "HTTP/1.1 404 Not Found"),
            ("curl output", "502 Bad Gateway"),
            ("curl output", "503 Service Unavailable"),
            ("curl: (56) Recv failure: Connection reset by peer", ""),
            ("nmap: Note: Host down", ""),
        ]
        for stderr_msg, stdout_msg in cases:
            c, _ = classify_failure(1, stdout=stdout_msg, stderr=stderr_msg)
            assert c == FailureClassification.TARGET_FAILURE, f"Failed for {stderr_msg} / {stdout_msg}"

    def test_invalid_command_syntax(self):
        """Syntax errors and unrecognized options map to INVALID_COMMAND."""
        errors = [
            "nmap: unrecognized option '--bad-flag'",
            "curl: option -Z: is unknown",
            "bash: syntax error near unexpected token `fi'",
        ]
        for err in errors:
            c, _ = classify_failure(2, stderr=err)
            assert c == FailureClassification.INVALID_COMMAND, f"Failed for {err}"

    def test_never_map_failures_to_success(self):
        """Failure classifier must never return SUCCESS or COMPLETED."""
        c1, _ = classify_failure(0, stdout="unknown unexpected behavior")
        assert c1 != "SUCCESS" and c1 != "COMPLETED"
        assert c1 == FailureClassification.UNKNOWN_FAILURE

        c2, _ = classify_failure(1, stdout="general error")
        assert c2 != "SUCCESS" and c2 != "COMPLETED"


# =====================================================================
# 3. Failure Budget Tracker Tests
# =====================================================================

class TestFailureBudgetTracker:
    """Verify Section 3 FailureBudgetTracker functionality."""

    def test_failure_counting_and_strategy_exhaustion(self):
        """Tracker increments counts and marks strategy EXHAUSTED upon reaching max_budget."""
        tracker = FailureBudgetTracker(max_budget=3)
        tool, provider = "nmap", "docker"

        assert tracker.is_strategy_exhausted(tool, provider) is False
        assert tracker.get_strategy_state(tool, provider) == StrategyState.ACTIVE

        # Attempt 1
        r1 = tracker.record_failure(tool, provider, FailureClassification.TOOL_FAILURE, raw_error="not found")
        assert r1.count == 1
        assert tracker.is_strategy_exhausted(tool, provider) is False
        assert tracker.get_strategy_state(tool, provider) == StrategyState.DEGRADED

        # Attempt 2
        r2 = tracker.record_failure(tool, provider, FailureClassification.TOOL_FAILURE, raw_error="not found")
        assert r2.count == 2
        assert tracker.is_strategy_exhausted(tool, provider) is False

        # Attempt 3: Exhausted
        r3 = tracker.record_failure(tool, provider, FailureClassification.TOOL_FAILURE, raw_error="not found")
        assert r3.count == 3
        assert tracker.is_strategy_exhausted(tool, provider) is True
        assert tracker.get_strategy_state(tool, provider) == StrategyState.EXHAUSTED

    def test_substrate_outage_detection_on_three_consecutive_failures(self):
        """3 consecutive PROVIDER_FAILURE or SANDBOX_FAILURE must trigger substrate_outage."""
        tracker = FailureBudgetTracker(max_budget=5)
        assert tracker.substrate_outage is False
        assert tracker.diagnostic_status == "HEALTHY"

        # 1st provider error
        tracker.record_failure("probe", "docker", FailureClassification.PROVIDER_FAILURE, "daemon down")
        assert tracker.substrate_outage is False
        assert tracker.consecutive_provider_failures == 1

        # 2nd sandbox error
        tracker.record_failure("probe", "docker", FailureClassification.SANDBOX_FAILURE, "container died")
        assert tracker.substrate_outage is False
        assert tracker.consecutive_provider_failures == 2

        # Interleaved non-provider failure resets consecutive counter
        tracker.record_failure("curl", "docker", FailureClassification.TARGET_FAILURE, "404 not found")
        assert tracker.consecutive_provider_failures == 0
        assert tracker.substrate_outage is False

        # Now 3 consecutive provider/sandbox errors
        tracker.record_failure("probe", "docker", FailureClassification.PROVIDER_FAILURE, "daemon down")
        tracker.record_failure("probe", "docker", FailureClassification.PROVIDER_FAILURE, "daemon down")
        tracker.record_failure("probe", "docker", FailureClassification.SANDBOX_FAILURE, "crashed")

        assert tracker.consecutive_provider_failures == 3
        assert tracker.substrate_outage is True
        assert tracker.diagnostic_status == "SUBSTRATE_OUTAGE_DETECTED"

        health = tracker.diagnose_substrate_health()
        assert health["substrate_outage"] is True
        assert health["diagnostic_status"] == "SUBSTRATE_OUTAGE_DETECTED"
        assert health["consecutive_provider_failures"] == 3


# =====================================================================
# 4. Agent Integration & Fail-Safe Execution Tests
# =====================================================================

def _mock_provider():
    p = AsyncMock()
    p.screenshot.return_value = ScreenObservation(width=1280, height=800)
    p.status.return_value = MagicMock(
        active_application="Desktop",
        open_applications=["Desktop"],
        running_processes=["bash"],
        working_directory="/home/daytona",
    )
    p.list_files.return_value = []
    p.git_action.return_value = MagicMock(branch="main", is_clean=True)
    p.terminal.return_value = MagicMock(stdout="OK", stderr="", exit_code=0)
    p.gui_action.return_value = ScreenObservation(width=1280, height=800)
    return p


class TestAgentFailureIntegration:
    """Verify Section 4 ComputerUseAgent failure behavior."""

    @pytest.mark.asyncio
    async def test_reasoning_context_contains_forced_cognitive_fields_and_strategies(self):
        """Reasoning context must contain all mandatory cognitive fields and explicit strategy tracking."""
        provider = _mock_provider()
        agent = ComputerUseAgent(computer_provider=provider)
        obs = await agent.observe("ws-test")

        system_prompt, obs_summary = agent._build_reasoning_context(
            goal="Identify open vulnerabilities",
            observation=obs,
            step_index=1,
            primary_file="scan.py",
            test_file="test_scan.py",
        )

        # Check forced cognitive fields in context
        assert "WHAT DO I KNOW?" in obs_summary
        assert "WHAT DO I NOT KNOW?" in obs_summary
        assert "WHAT FAILED?" in obs_summary
        assert "WHY DID IT FAIL?" in obs_summary
        assert "WHAT HYPOTHESIS DOES THIS SUPPORT/DISPROVE?" in obs_summary
        assert "WHAT IS THE HIGHEST-INFORMATION NEXT ACTION?" in obs_summary

        # Check explicit strategy tracking
        assert "Strategy A:" in obs_summary
        assert "Strategy B:" in obs_summary

        # Check system prompt also enforces these fields
        assert "WHAT DO I KNOW?" in system_prompt
        assert "WHAT FAILED?" in system_prompt
        assert "WHAT HYPOTHESIS DOES THIS SUPPORT/DISPROVE?" in system_prompt

    @pytest.mark.asyncio
    async def test_missing_observation_outputs_unknown(self):
        """Missing or empty observation fields must truthfully render as UNKNOWN (no fake values)."""
        provider = _mock_provider()
        agent = ComputerUseAgent(computer_provider=provider)
        empty_obs = MagicMock(
            visible_text="",
            terminal_output="",
            filesystem_files=[],
            working_directory="",
            active_application="",
            windows=[],
            git_branch="",
            git_clean=True,
            browser_state={},
        )

        _, obs_summary = agent._build_reasoning_context(
            goal="Test unknown",
            observation=empty_obs,
            step_index=1,
            primary_file="",
            test_file="",
        )

        assert "Screen visible text:\nUNKNOWN" in obs_summary
        assert "Terminal output:\nUNKNOWN" in obs_summary
        assert "Files in workspace: UNKNOWN" in obs_summary
        assert "Active window / app: UNKNOWN" in obs_summary

    @pytest.mark.asyncio
    async def test_failure_budget_exhaustion_blocks_retry(self):
        """When strategy budget is exhausted, agent blocks retry with status FAILED."""
        provider = _mock_provider()
        provider.terminal.return_value = MagicMock(
            stdout="",
            stderr="nmap: command not found",
            exit_code=127,
        )
        tracker = FailureBudgetTracker(max_budget=3)
        agent = ComputerUseAgent(
            computer_provider=provider,
            max_recovery_attempts=0,
            failure_budget=tracker,
        )

        # Execute 3 times to exhaust failure budget for 'nmap'
        for _ in range(3):
            await agent.execute_action(
                workspace_id="ws-test",
                action_type=ComputerActionType.TERMINAL_EXEC,
                target_resource="nmap 127.0.0.1",
                payload={"command": "nmap 127.0.0.1"},
                predicted_outcome="expect scan",
            )

        assert tracker.is_strategy_exhausted("nmap", agent._get_provider_name()) is True

        # 4th attempt: must be intercepted and immediately FAILED without calling provider.terminal again
        provider.terminal.reset_mock()
        trace = await agent.execute_action(
            workspace_id="ws-test",
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="nmap 127.0.0.1",
            payload={"command": "nmap 127.0.0.1"},
            predicted_outcome="expect scan",
        )

        assert trace.status == ActionExecutionStatus.FAILED
        assert "Strategy exhausted" in trace.actual_observation
        assert provider.terminal.call_count == 0  # Not retried!

    @pytest.mark.asyncio
    async def test_substrate_outage_halts_target_actions(self):
        """Substrate outage (3 consecutive provider errors) halts target actions and switches to diagnostic."""
        provider = _mock_provider()
        provider.terminal.return_value = MagicMock(
            stdout="",
            stderr="docker: daemon is not running",
            exit_code=125,
        )
        tracker = FailureBudgetTracker(max_budget=5)
        agent = ComputerUseAgent(
            computer_provider=provider,
            max_recovery_attempts=0,
            failure_budget=tracker,
        )

        # Trigger 3 consecutive provider errors (exit 125)
        for _ in range(3):
            trace = await agent.execute_action(
                workspace_id="ws-test",
                action_type=ComputerActionType.TERMINAL_EXEC,
                target_resource="curl http://target",
                payload={"command": "curl http://target"},
                predicted_outcome="expect response",
            )
            # Exit 125 must strictly map to BLOCKED or FAILED
            assert trace.status in (ActionExecutionStatus.BLOCKED, ActionExecutionStatus.FAILED)

        assert tracker.substrate_outage is True
        assert tracker.diagnostic_status == "SUBSTRATE_OUTAGE_DETECTED"

        # Subsequent target action is intercepted and switched to substrate diagnostic
        provider.terminal.reset_mock()
        outage_trace = await agent.execute_action(
            workspace_id="ws-test",
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="curl http://target",
            payload={"command": "curl http://target"},
            predicted_outcome="expect response",
        )

        assert outage_trace.status == ActionExecutionStatus.BLOCKED
        assert "SUBSTRATE_OUTAGE_DETECTED" in outage_trace.actual_observation
        assert provider.terminal.call_count == 0

