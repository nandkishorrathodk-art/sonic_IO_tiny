"""
SONIC RESEARCHER BEHAVIOR REBUILD — Acceptance Test Suite (Sections 12 and 13)
=============================================================================
Verifies truthful runtime behavior across the 8 failure modes:
1. Healthy environment -> Truthful SUCCEEDED
2. Tool missing -> TOOL_FAILURE + strategy exhausted after budget
3. Tool failure -> TOOL_FAILURE diagnosis
4. Network failure -> NETWORK_FAILURE diagnosis
5. Timeout -> TIMEOUT diagnosis + TIMED_OUT status
6. Blocked action -> POLICY_BLOCK diagnosis + BLOCKED status (Exit 125/126)
7. Partial target failure -> TARGET_FAILURE diagnosis
8. One specialist failure while others continue -> Worker failure isolation

Section 13:
Final Acceptance: Intentionally break Worker A -> Worker A fails/blocked,
Workers B and C continue running in parallel, Central Brain diagnoses failure,
Falsification continues, State is preserved, Restore Worker A and resume from
preserved state.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest

from sonic.computer.models import ScreenObservation
from sonic.computer_use.models import (
    ActionExecutionStatus,
    ComputerActionType,
    ComputerDecisionTrace,
    FailureClassification,
    StrategyState,
)
from sonic.computer_use.agent import ComputerUseAgent
from sonic.research.event_bus import ResearchEventBus
from sonic.research.failure_classifier import classify_failure
from sonic.research.failure_budget import FailureBudgetTracker
from sonic.research.orchestrator import AsyncResearchOrchestrator, ResearchBlackboard
from sonic.research.specialist import (
    NetworkSpecialist,
    WebSpecialist,
    ApiSpecialist,
    FalsificationSpecialist,
    SpecialistState,
    SpecialistAgent,
    SpecialistBlockedError,
)


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


class TestResearcherBehaviorRebuildAcceptance:
    """Acceptance tests verifying all 8 failure modes and Section 13 acceptance flow."""

    # -------------------------------------------------------------
    # 1. Healthy Environment
    # -------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_mode1_healthy_environment_produces_truthful_success(self):
        """Healthy command execution results in SUCCEEDED status (truthful, no false fails)."""
        provider = _mock_provider()
        provider.terminal.return_value = MagicMock(
            stdout="Target 127.0.0.1 responded with 200 OK",
            stderr="",
            exit_code=0,
        )
        agent = ComputerUseAgent(computer_provider=provider)

        trace = await agent.execute_action(
            workspace_id="ws-1",
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="curl http://127.0.0.1",
            payload={"command": "curl http://127.0.0.1"},
            predicted_outcome="Target response",
        )

        assert trace.status in (ActionExecutionStatus.COMPLETED, ActionExecutionStatus.SUCCESS, ActionExecutionStatus.SUCCEEDED)
        assert trace.status != ActionExecutionStatus.FAILED
        assert trace.status != ActionExecutionStatus.BLOCKED

    # -------------------------------------------------------------
    # 2. Tool Missing
    # -------------------------------------------------------------
    def test_mode2_tool_missing_classified_as_tool_failure_and_exhausts_budget(self):
        """Exit 127 (command not found) classifies as TOOL_FAILURE and exhausts budget after 3 attempts."""
        err_cls, diag = classify_failure(
            exit_code=127,
            stderr="bash: nmap: command not found",
            tool="nmap",
            provider="headless",
        )
        assert err_cls == FailureClassification.TOOL_FAILURE
        assert "command not found" in diag.lower() or "tool" in diag.lower()

        budget = FailureBudgetTracker(max_budget=3)
        # Attempt 1
        rec1 = budget.record_failure("nmap", "headless", err_cls, diag)
        assert budget.strategy_states[("nmap", "headless", err_cls)] == StrategyState.DEGRADED
        assert not budget.is_strategy_exhausted("nmap", "headless")

        # Attempt 2
        rec2 = budget.record_failure("nmap", "headless", err_cls, diag)
        assert budget.strategy_states[("nmap", "headless", err_cls)] == StrategyState.DEGRADED
        assert not budget.is_strategy_exhausted("nmap", "headless")

        # Attempt 3 -> Exhausted!
        rec3 = budget.record_failure("nmap", "headless", err_cls, diag)
        assert budget.strategy_states[("nmap", "headless", err_cls)] == StrategyState.EXHAUSTED
        assert budget.is_strategy_exhausted("nmap", "headless")

    # -------------------------------------------------------------
    # 3. Tool Failure
    # -------------------------------------------------------------
    def test_mode3_tool_failure_diagnosed_correctly(self):
        """Tool internal crash/error classifies as TOOL_FAILURE."""
        err_cls, diag = classify_failure(
            exit_code=2,
            stderr="nmap: FATAL: Failed to determine route to target",
            tool="nmap",
        )
        assert err_cls in (FailureClassification.TOOL_FAILURE, FailureClassification.NETWORK_FAILURE)
        assert len(diag) > 0

    # -------------------------------------------------------------
    # 4. Network Failure
    # -------------------------------------------------------------
    def test_mode4_network_failure_diagnosed_correctly(self):
        """Connection refused / network unreachable classifies as NETWORK_FAILURE."""
        err_cls, diag = classify_failure(
            exit_code=7,
            stderr="curl: (7) Failed to connect to 10.0.0.1 port 80: Connection refused",
            tool="curl",
        )
        assert err_cls == FailureClassification.NETWORK_FAILURE
        assert "connection refused" in diag.lower() or "network" in diag.lower()

    # -------------------------------------------------------------
    # 5. Timeout
    # -------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_mode5_timeout_results_in_timed_out_status(self):
        """Exit 124 maps to TIMEOUT and TIMED_OUT status."""
        provider = _mock_provider()
        provider.terminal.return_value = MagicMock(
            stdout="",
            stderr="timeout: command timed out after 10s",
            exit_code=124,
        )
        agent = ComputerUseAgent(computer_provider=provider, max_recovery_attempts=0)

        trace = await agent.execute_action(
            workspace_id="ws-1",
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="slow_scan",
            payload={"command": "slow_scan"},
            predicted_outcome="expect finish",
        )
        assert trace.status == ActionExecutionStatus.TIMED_OUT
        err_cls, _ = classify_failure(124, stderr="timeout: command timed out")
        assert err_cls == FailureClassification.TIMEOUT

    # -------------------------------------------------------------
    # 6. Blocked Action (Exit 125/126)
    # -------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_mode6_blocked_action_and_exit_125_never_mapped_to_success(self):
        """Exit 125 strictly maps to BLOCKED/FAILED, never SUCCESS."""
        provider = _mock_provider()
        provider.terminal.return_value = MagicMock(
            stdout="",
            stderr="container sonic-desktop-workstation is not running; command blocked fail-closed",
            exit_code=125,
        )
        agent = ComputerUseAgent(computer_provider=provider)

        trace = await agent.execute_action(
            workspace_id="ws-1",
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="nmap 10.0.0.1",
            payload={"command": "nmap 10.0.0.1"},
            predicted_outcome="scan ports",
        )

        assert trace.status in (ActionExecutionStatus.BLOCKED, ActionExecutionStatus.FAILED)
        assert trace.status != "SUCCESS"
        assert trace.status != ActionExecutionStatus.SUCCESS
        assert trace.status != ActionExecutionStatus.COMPLETED

        err_cls, diag = classify_failure(125, stderr="container not running")
        assert err_cls in (FailureClassification.PROVIDER_FAILURE, FailureClassification.SANDBOX_FAILURE)

    # -------------------------------------------------------------
    # 7. Partial Target Failure
    # -------------------------------------------------------------
    def test_mode7_partial_target_failure_diagnosed(self):
        """HTTP 500 / 502 / 503 target errors classify as TARGET_FAILURE."""
        err_cls, diag = classify_failure(
            exit_code=22,
            stderr="curl: (22) The requested URL returned error: 502 Bad Gateway",
            stdout="502 Bad Gateway",
        )
        assert err_cls == FailureClassification.TARGET_FAILURE
        assert "502" in diag

    # -------------------------------------------------------------
    # 8 and Section 13: Final Acceptance Test (Fault Isolation and State Resumption)
    # -------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_mode8_and_section13_final_acceptance_fault_isolation_and_resumption(self):
        """
        Final Acceptance Test:
        1. Spawn Worker A (NetworkSpecialist), Worker B (WebSpecialist), Worker C (ApiSpecialist), FalsificationSpecialist.
        2. Worker A encounters a substrate failure (exit 125 / PROVIDER_FAILURE).
        3. Worker A fails/blocked cleanly.
        4. Worker B and Worker C CONTINUE executing concurrently and succeed.
        5. Central Brain diagnoses Worker A's failure on the blackboard.
        6. Falsification continues where appropriate.
        7. Research state and attack graph are preserved.
        8. Restore Worker A: resume_specialist() resumes Worker A from preserved state.
        9. Worker A completes successfully.
        """
        bus = ResearchEventBus()
        blackboard = ResearchBlackboard()
        orchestrator = AsyncResearchOrchestrator(
            event_bus=bus,
            blackboard=blackboard,
            max_concurrent_specialists=10,
        )

        # Pre-seed existing finding on blackboard
        blackboard.custom_data["initial_target"] = {"host": "10.0.0.1"}

        # Worker A: Initially fails with PROVIDER_FAILURE
        async def failing_worker_a(agent: SpecialistAgent, ctx: dict, eb: ResearchEventBus):
            await asyncio.sleep(0.01)
            raise SpecialistBlockedError(
                "Container dropped: docker exit 125",
                reason="PROVIDER_FAILURE",
                diagnostic="dockerd daemon connection reset",
            )

        worker_a = NetworkSpecialist(
            name="WorkerA_Network",
            target="10.0.0.1",
            investigation_fn=failing_worker_a,
        )

        # Worker B: Succeeds
        async def working_worker_b(agent: SpecialistAgent, ctx: dict, eb: ResearchEventBus):
            await asyncio.sleep(0.05)
            blackboard.custom_data["web_route"] = {"path": "/login", "status": 200}

        worker_b = WebSpecialist(name="WorkerB_Web", target_url="http://10.0.0.1", investigation_fn=working_worker_b)

        # Worker C: Succeeds
        async def working_worker_c(agent: SpecialistAgent, ctx: dict, eb: ResearchEventBus):
            await asyncio.sleep(0.05)
            blackboard.custom_data["api_endpoint"] = {"endpoint": "/api/v1/auth"}

        worker_c = ApiSpecialist(name="WorkerC_Api", target_url="http://10.0.0.1/api", investigation_fn=working_worker_c)

        # Falsifier: Succeeds
        falsifier = FalsificationSpecialist(name="Falsifier")

        # Step 1: Run parallel orchestrator with failing Worker A
        result = await orchestrator.run(
            initial_specialists=[worker_a, worker_b, worker_c, falsifier],
            initial_context={"target": "10.0.0.1"},
            timeout_seconds=5.0,
        )

        # Verify Worker A failed/blocked
        assert worker_a.state == SpecialistState.BLOCKED
        assert "WorkerA_Network" in result.specialists_blocked

        # Verify Worker B and Worker C CONTINUED and SUCCEEDED
        assert worker_b.state == SpecialistState.COMPLETED
        assert worker_c.state == SpecialistState.COMPLETED
        assert falsifier.state == SpecialistState.COMPLETED

        assert "WorkerB_Web" in result.specialists_succeeded
        assert "WorkerC_Api" in result.specialists_succeeded

        # Verify Central Brain diagnosed failure on blackboard
        assert "WorkerA_Network" in blackboard.failed_workers
        diag = blackboard.diagnose_failure("WorkerA_Network")
        assert diag["reason"] == "PROVIDER_FAILURE"
        assert diag["substrate_issue"] == "provider_failure"
        assert diag["can_resume"] is True

        # Verify research state was preserved (all findings remain)
        findings = blackboard.custom_data
        assert "initial_target" in findings
        assert "web_route" in findings
        assert "api_endpoint" in findings

        # Step 2: Restore Worker A (substrate fixed)
        async def recovered_worker_a(agent: SpecialistAgent, ctx: dict, eb: ResearchEventBus):
            await asyncio.sleep(0.02)
            blackboard.custom_data["open_ports"] = {"ports": [80, 443]}

        worker_a._investigation_fn = recovered_worker_a

        # Resume Worker A from preserved state
        resumed = orchestrator.resume_specialist("WorkerA_Network", {"target": "10.0.0.1"})
        assert resumed is not None
        assert resumed.state == SpecialistState.IDLE
        assert "WorkerA_Network" not in blackboard.failed_workers

        # Run orchestrator to execute the resumed Worker A
        result_p2 = await orchestrator.run(timeout_seconds=5.0)
        assert resumed.state == SpecialistState.COMPLETED
        assert "WorkerA_Network" in result_p2.specialists_succeeded

        # Verify new finding was added alongside preserved findings
        all_findings = blackboard.custom_data
        assert "open_ports" in all_findings
        assert "web_route" in all_findings
        assert "api_endpoint" in all_findings
