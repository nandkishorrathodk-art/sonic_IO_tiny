"""Tests for the Boss Agent + SubAgents orchestration system."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sonic.computer_use.boss import BossAgent
from sonic.computer_use.models import (
    ActionExecutionStatus,
    ComputerActionType,
    ComputerDecisionTrace,
)
from sonic.computer_use.models_boss import (
    BossReport,
    BossThinking,
    Phase,
    SubMission,
    SubMissionResult,
)


def _make_llm_mock(responses: list[str]):
    """Create a mock LLM router that returns responses in order."""
    mock = AsyncMock()
    results = []
    for r in responses:
        resp = MagicMock()
        resp.content = r
        resp.reasoning_content = ""
        resp.latency_ms = 100
        results.append(resp)
    mock.complete = AsyncMock(side_effect=results)
    return mock


def _make_computer_mock():
    computer = AsyncMock()
    computer.terminal = AsyncMock(return_value=MagicMock(stdout="output", exit_code=0))
    computer.screenshot = AsyncMock(return_value=MagicMock(data=b"fake"))
    computer.gui_action = AsyncMock()
    computer.status = AsyncMock(
        return_value=MagicMock(
            active_window="Desktop",
            terminal_output="$ ",
            running_processes=[],
        )
    )
    return computer


def _make_trace(
    action_type=ComputerActionType.TERMINAL_EXEC,
    target="test_target",
    observation="command output",
    status="COMPLETED",
):
    return ComputerDecisionTrace(
        action_type=action_type,
        target_resource=target,
        predicted_outcome="expected outcome",
        actual_observation=observation,
        status=ActionExecutionStatus.COMPLETED
        if status == "COMPLETED"
        else ActionExecutionStatus.FAILED,
    )


@pytest.mark.asyncio
async def test_boss_strategic_decomposition_creates_phase():
    """Boss deep-thinks and decomposes objective into sub-missions."""
    decomp_json = json.dumps({
        "thinking": "We need reconnaissance first: endpoints, tech stack, and input forms.",
        "phase_name": "Reconnaissance",
        "sub_missions": [
            {"goal": "Find endpoints", "max_steps": 3, "priority": 2},
            {"goal": "Identify tech stack", "max_steps": 3, "priority": 1},
            {"goal": "Map input forms", "max_steps": 4, "priority": 1},
        ],
    })
    llm = _make_llm_mock([decomp_json])
    computer = _make_computer_mock()

    boss = BossAgent(computer_provider=computer, llm_router=llm)
    phase = await boss._strategic_decomposition("find SQL injection in target.com")

    assert phase is not None
    assert phase.phase_number == 1
    assert phase.name == "Reconnaissance"
    assert len(phase.sub_missions) == 3
    assert phase.sub_missions[0].goal == "Find endpoints"
    assert len(boss.thinking_log) == 1
    assert boss.thinking_log[0].thinking_type == "strategic_decomposition"
    assert "reconnaissance" in boss.thinking_log[0].content.lower()


@pytest.mark.asyncio
async def test_boss_sub_agent_dispatch_creates_focused_agent():
    """Dispatching a sub-mission creates a focused ComputerUseAgent."""
    summary_json = "Found 3 endpoints with parameters."
    llm = _make_llm_mock([summary_json])
    computer = _make_computer_mock()

    mock_trace = _make_trace(target="curl target.com", observation="endpoints found")

    with patch("sonic.computer_use.agent.ComputerUseAgent") as MockAgentClass:
        mock_agent = MagicMock()
        mock_agent.run_mission = AsyncMock(return_value=[mock_trace])
        MockAgentClass.return_value = mock_agent

        boss = BossAgent(computer_provider=computer, llm_router=llm)
        sub_mission = SubMission(id="sub-1", goal="scan target endpoints", max_steps=3)

        result = await boss._dispatch_sub_agent("ws-1", sub_mission)

        assert isinstance(result, SubMissionResult)
        assert result.sub_mission_id == "sub-1"
        assert result.success is True
        assert len(result.traces) == 1
        assert result.actions_taken == 1
        # Verify ComputerUseAgent was instantiated with focused max_actions
        MockAgentClass.assert_called_once()
        _, kwargs = MockAgentClass.call_args
        assert kwargs["max_actions"] == 3
        assert kwargs["agent_id"] == "sub-agent-0"


@pytest.mark.asyncio
async def test_boss_collects_all_sub_agent_reports():
    """Boss runs sub-missions, collects reports, and tracks all traces."""
    decomp_json = json.dumps({
        "thinking": "Run two recon tasks.",
        "phase_name": "Recon",
        "sub_missions": [
            {"goal": "Check ports", "max_steps": 3, "priority": 2},
            {"goal": "Check headers", "max_steps": 3, "priority": 1},
        ],
    })
    sub1_summary = "Port 80 and 443 open."
    sub2_summary = "Apache 2.4 server detected."
    phase_analysis = "Both tasks completed. Ports open, Apache detected."
    completion_json = json.dumps({"complete": True, "reason": "Basic recon complete."})
    final_report_text = "Reconnaissance report: Port 80/443 open with Apache 2.4."

    llm = _make_llm_mock([
        decomp_json,
        sub1_summary,
        sub2_summary,
        phase_analysis,
        completion_json,
        final_report_text,
    ])
    computer = _make_computer_mock()

    trace1 = _make_trace(target="nmap -p 80,443", observation="80/tcp open, 443/tcp open")
    trace2 = _make_trace(target="curl -I", observation="Server: Apache/2.4")

    with patch("sonic.computer_use.agent.ComputerUseAgent") as MockAgentClass:
        mock_agent1 = MagicMock()
        mock_agent1.run_mission = AsyncMock(return_value=[trace1])
        mock_agent2 = MagicMock()
        mock_agent2.run_mission = AsyncMock(return_value=[trace2])
        MockAgentClass.side_effect = [mock_agent1, mock_agent2]

        boss = BossAgent(computer_provider=computer, llm_router=llm)
        report = await boss.run(workspace_id="ws-1", objective="perform recon on target.com")

        assert isinstance(report, BossReport)
        assert report.status == "COMPLETE"
        assert len(report.phases) == 1
        assert len(report.phases[0].results) == 2
        assert report.total_sub_agents == 2
        assert len(report.all_traces) == 2


@pytest.mark.asyncio
async def test_boss_multi_phase_findings_drive_next_phase():
    """Phase 1 findings feed into LLM to plan Phase 2."""
    phase1_decomp = json.dumps({
        "thinking": "Phase 1: Discover attack surface.",
        "phase_name": "Discovery",
        "sub_missions": [
            {"goal": "Find parameters", "max_steps": 3, "priority": 1},
        ],
    })
    sub1_summary = "Found /search?q= parameter."
    phase1_analysis = "Found parameter /search?q=, suitable for SQLi testing."
    completion1_json = json.dumps({"complete": False, "reason": "Need to test the parameter."})

    phase2_plan = json.dumps({
        "thinking": "Phase 2: Test the /search?q= parameter found in Phase 1.",
        "phase_name": "SQLi Testing",
        "sub_missions": [
            {"goal": "Test /search?q= for SQLi", "max_steps": 4, "priority": 1},
        ],
    })
    sub2_summary = "SQL injection confirmed on /search?q= with payload ' OR 1=1--"
    phase2_analysis = "Confirmed SQL injection vulnerability."
    completion2_json = json.dumps({"complete": True, "reason": "Vulnerability identified and verified."})
    final_summary = "SQL injection confirmed on /search?q=."

    llm = _make_llm_mock([
        phase1_decomp,
        sub1_summary,
        phase1_analysis,
        completion1_json,
        phase2_plan,
        sub2_summary,
        phase2_analysis,
        completion2_json,
        final_summary,
    ])
    computer = _make_computer_mock()

    trace1 = _make_trace(target="curl /search?q=test", observation="/search?q= exists")
    trace2 = _make_trace(target="sqlmap -u /search?q=1", observation="sqlmap identified SQLi")

    with patch("sonic.computer_use.agent.ComputerUseAgent") as MockAgentClass:
        mock_agent1 = MagicMock()
        mock_agent1.run_mission = AsyncMock(return_value=[trace1])
        mock_agent2 = MagicMock()
        mock_agent2.run_mission = AsyncMock(return_value=[trace2])
        MockAgentClass.side_effect = [mock_agent1, mock_agent2]

        boss = BossAgent(computer_provider=computer, llm_router=llm, max_phases=3)
        report = await boss.run(workspace_id="ws-1", objective="find SQLi in target.com")

        assert len(report.phases) == 2
        assert report.phases[0].name == "Discovery"
        assert report.phases[1].name == "SQLi Testing"
        assert report.total_sub_agents == 2
        assert report.status == "COMPLETE"


@pytest.mark.asyncio
async def test_boss_objective_completion_stops_loop():
    """Completion check returning True stops orchestration immediately."""
    decomp_json = json.dumps({
        "thinking": "Single phase is sufficient.",
        "phase_name": "Hostname Check",
        "sub_missions": [{"goal": "Get hostname", "max_steps": 2, "priority": 1}],
    })
    sub_summary = "Hostname is 8e8d478afea9."
    phase_analysis = "Hostname retrieved."
    completion_json = json.dumps({"complete": True, "reason": "Hostname already found."})
    final_summary = "Hostname: 8e8d478afea9."

    llm = _make_llm_mock([
        decomp_json,
        sub_summary,
        phase_analysis,
        completion_json,
        final_summary,
    ])
    computer = _make_computer_mock()
    trace = _make_trace(target="hostname", observation="8e8d478afea9")

    with patch("sonic.computer_use.agent.ComputerUseAgent") as MockAgentClass:
        mock_agent = MagicMock()
        mock_agent.run_mission = AsyncMock(return_value=[trace])
        MockAgentClass.return_value = mock_agent

        boss = BossAgent(computer_provider=computer, llm_router=llm, max_phases=5)
        report = await boss.run(workspace_id="ws-1", objective="get hostname")

        assert len(report.phases) == 1
        assert report.status == "COMPLETE"


@pytest.mark.asyncio
async def test_boss_safety_inherited_by_sub_agents():
    """Safety policy is propagated to all SubAgents with self_host=True."""
    decomp_json = json.dumps({
        "thinking": "Check files.",
        "phase_name": "File Check",
        "sub_missions": [{"goal": "Read config", "max_steps": 3, "priority": 1}],
    })
    llm = _make_llm_mock([decomp_json, "summary", "analysis", json.dumps({"complete": True}), "done"])
    computer = _make_computer_mock()
    mock_safety = MagicMock()

    with patch("sonic.computer_use.agent.ComputerUseAgent") as MockAgentClass:
        mock_agent = MagicMock()
        mock_agent.run_mission = AsyncMock(return_value=[_make_trace()])
        MockAgentClass.return_value = mock_agent

        boss = BossAgent(computer_provider=computer, llm_router=llm, safety=mock_safety)
        await boss.run(workspace_id="ws-1", objective="check config")

        MockAgentClass.assert_called_once()
        _, kwargs = MockAgentClass.call_args
        assert kwargs["safety"] is mock_safety
        assert kwargs["self_host"] is True


def test_boss_never_executes_directly():
    """BossAgent has no terminal or GUI execution methods."""
    computer = _make_computer_mock()
    llm = _make_llm_mock([])
    boss = BossAgent(computer_provider=computer, llm_router=llm)

    # Boss should NOT have action execution primitives
    assert not hasattr(boss, "execute_action")
    assert not hasattr(boss, "terminal")
    assert not hasattr(boss, "gui_action")
    assert not hasattr(boss, "browser_action")
    # Boss SHOULD have orchestration primitives
    assert hasattr(boss, "run")
    assert hasattr(boss, "_strategic_decomposition")
    assert hasattr(boss, "_dispatch_sub_agent")
    assert hasattr(boss, "_aggregate_findings")
    assert hasattr(boss, "_plan_next_phase")


@pytest.mark.asyncio
async def test_boss_phase_callback_streams_events():
    """Phase callback receives real-time orchestration events."""
    decomp_json = json.dumps({
        "thinking": "Two quick tasks.",
        "phase_name": "Quick Tasks",
        "sub_missions": [
            {"goal": "Task 1", "max_steps": 2, "priority": 2},
            {"goal": "Task 2", "max_steps": 2, "priority": 1},
        ],
    })
    llm = _make_llm_mock([
        decomp_json,
        "Task 1 done",
        "Task 2 done",
        "All done",
        json.dumps({"complete": True}),
        "Final report",
    ])
    computer = _make_computer_mock()

    events = []

    async def _on_event(event_type, data):
        events.append(event_type)

    with patch("sonic.computer_use.agent.ComputerUseAgent") as MockAgentClass:
        mock_agent = MagicMock()
        mock_agent.run_mission = AsyncMock(return_value=[_make_trace()])
        MockAgentClass.return_value = mock_agent

        boss = BossAgent(computer_provider=computer, llm_router=llm)
        await boss.run(workspace_id="ws-1", objective="run tasks", phase_callback=_on_event)

        assert "boss_thinking" in events
        assert "sub_dispatch" in events
        assert "sub_report" in events
        assert "phase_complete" in events
        assert "boss_report" in events


@pytest.mark.asyncio
async def test_boss_sub_agent_failure_graceful_degradation():
    """If one SubAgent crashes, Boss continues with remaining sub-missions."""
    decomp_json = json.dumps({
        "thinking": "Task 1 will fail, Task 2 will succeed.",
        "phase_name": "Mixed Phase",
        "sub_missions": [
            {"goal": "Failing task", "max_steps": 2, "priority": 2},
            {"goal": "Succeeding task", "max_steps": 2, "priority": 1},
        ],
    })
    llm = _make_llm_mock([
        decomp_json,
        "Task 2 output summary",
        "Analysis of mixed results",
        json.dumps({"complete": True}),
        "Final summary of partial success",
    ])
    computer = _make_computer_mock()

    trace_success = _make_trace(target="echo ok", observation="ok")

    with patch("sonic.computer_use.agent.ComputerUseAgent") as MockAgentClass:
        mock_agent_fail = MagicMock()
        mock_agent_fail.run_mission = AsyncMock(side_effect=RuntimeError("Container connection dropped"))
        mock_agent_ok = MagicMock()
        mock_agent_ok.run_mission = AsyncMock(return_value=[trace_success])

        MockAgentClass.side_effect = [mock_agent_fail, mock_agent_ok]

        boss = BossAgent(computer_provider=computer, llm_router=llm)
        report = await boss.run(workspace_id="ws-1", objective="mixed tasks")

        assert len(report.phases[0].results) == 2
        assert report.phases[0].results[0].success is False
        assert "failed" in report.phases[0].results[0].findings_summary.lower()
        assert report.phases[0].results[1].success is True
        assert report.status in ("PARTIAL", "COMPLETE")


@pytest.mark.asyncio
async def test_boss_final_report_synthesis():
    """BossReport contains all required telemetry, summaries, and phases."""
    decomp_json = json.dumps({
        "thinking": "Single task.",
        "phase_name": "Audit",
        "sub_missions": [{"goal": "Audit system", "max_steps": 3, "priority": 1}],
    })
    llm = _make_llm_mock([
        decomp_json,
        "System is healthy.",
        "Audit completed successfully.",
        json.dumps({"complete": True}),
        "Full audit report: System clean.",
    ])
    computer = _make_computer_mock()

    with patch("sonic.computer_use.agent.ComputerUseAgent") as MockAgentClass:
        mock_agent = MagicMock()
        mock_agent.run_mission = AsyncMock(return_value=[_make_trace()])
        MockAgentClass.return_value = mock_agent

        boss = BossAgent(computer_provider=computer, llm_router=llm)
        report = await boss.run(workspace_id="ws-1", objective="audit system")

        assert report.objective == "audit system"
        assert report.status == "COMPLETE"
        assert report.total_phases == 1
        assert report.total_sub_agents == 1
        assert report.total_actions == 1
        assert "Full audit report" in report.findings_summary
        assert report.duration_seconds >= 0.0
        assert len(report.thinking_log) >= 2
