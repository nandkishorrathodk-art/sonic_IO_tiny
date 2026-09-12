"""Comprehensive integration tests for BossAgent with Workstation API and MissionDirector."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sonic.api.routes.workstation import (
    _get_or_create_session,
    _is_complex_or_multi_part_objective,
    _run_prompt_reasoning,
)
from sonic.computer_use.models import (
    ComputerActionType,
    ComputerAutonomyLevel,
    ComputerDecisionTrace,
)
from sonic.computer_use.models_boss import (
    BossReport,
    BossThinking,
    Phase,
    SubMission,
    SubMissionResult,
)
from sonic.mission_engine.director import MissionDirector


def test_is_complex_or_multi_part_objective_distinguishes_goals():
    """Verify classification logic accurately routes complex vs simple prompts."""
    # Complex / Security objectives -> True
    assert _is_complex_or_multi_part_objective("find SQL injection in target.com") is True
    assert _is_complex_or_multi_part_objective("audit web application for vulnerabilities") is True
    assert _is_complex_or_multi_part_objective("check system hostname and disk space and list running services") is True
    assert _is_complex_or_multi_part_objective("launch subagent to investigate") is True
    assert _is_complex_or_multi_part_objective("run phase 1 recon") is True
    assert _is_complex_or_multi_part_objective("deep dive into attack surface") is True
    assert _is_complex_or_multi_part_objective("investigate sql injection") is True

    # Simple queries -> False
    assert _is_complex_or_multi_part_objective("hostname") is False
    assert _is_complex_or_multi_part_objective("pwd") is False
    assert _is_complex_or_multi_part_objective("whoami") is False
    assert _is_complex_or_multi_part_objective("date") is False
    assert _is_complex_or_multi_part_objective("ls -la") is False


@pytest.mark.asyncio
async def test_workstation_routes_complex_prompt_to_boss_agent(monkeypatch):
    """Verify that a complex prompt in Workstation triggers BossAgent and streams all events."""
    tenant_id = "test-tenant-boss-int"
    session_id = "boss-int-sess-1"
    state = _get_or_create_session(tenant_id, session_id)
    state["desktop"] = {"workspace_id": "ws-int-boss"}
    state["worklog"] = []

    mock_screen = MagicMock(desktop_state="LIVE", width=1280, height=800, visible_text="", detected_controls=[])
    mock_computer = MagicMock()
    mock_computer.screenshot = AsyncMock(return_value=mock_screen)
    mock_computer.terminal = AsyncMock(side_effect=[MagicMock(stdout="/root"), MagicMock(stdout="file.txt")])
    monkeypatch.setattr("sonic.api.routes.workstation.get_daytona_computer", lambda: mock_computer)

    mock_trace = ComputerDecisionTrace(
        action_type=ComputerActionType.TERMINAL_EXEC,
        target_resource="curl target.com",
        predicted_outcome="response",
        actual_observation="HTTP 200 OK with PHP/7.4",
        status="SUCCESS",
    )
    mock_report = BossReport(
        objective="find SQL injection in target.com",
        status="COMPLETE",
        phases=[Phase(phase_number=1, name="Recon", sub_missions=[SubMission(goal="Discover endpoints")])],
        thinking_log=[BossThinking(phase=1, thinking_type="strategic_decomposition", content="Decomposing target into sub-tasks")],
        all_traces=[mock_trace],
        total_sub_agents=1,
        total_actions=1,
        total_phases=1,
        findings_summary="Recon completed: Apache 2.4 + PHP 7.4 found.",
    )

    with patch("sonic.computer_use.boss.BossAgent") as mock_boss_cls:
        mock_boss = MagicMock()

        async def fake_run(workspace_id, objective, phase_callback=None, interrupt_check=None):
            if phase_callback:
                await phase_callback("boss_thinking", {"content": "Planning attack phases", "thinking_type": "strategic_decomposition"})
                await phase_callback("sub_dispatch", {"sub_agent_number": 1, "goal": "Discover endpoints", "max_steps": 5})
                await phase_callback("sub_report", {"sub_agent_number": 1, "findings_summary": "Found 12 endpoints"})
                await phase_callback("phase_complete", {"phase_number": 1, "name": "Recon", "results_count": 1, "success_count": 1})
                await phase_callback("boss_report", {"findings_summary": "Recon completed: Apache 2.4 + PHP 7.4 found."})
            return mock_report

        mock_boss.run = AsyncMock(side_effect=fake_run)
        mock_boss_cls.return_value = mock_boss

        await _run_prompt_reasoning(tenant_id, session_id, "find SQL injection in target.com")

        assert mock_boss_cls.called
        assert mock_boss.run.called
        assert state["status"] == "IDLE"
        assert state["thought_summary"] == "Recon completed: Apache 2.4 + PHP 7.4 found."

        titles = [w.get("title") for w in state.get("worklog", [])]
        assert any("Boss Thinking" in t for t in titles)
        assert any("Dispatching SubAgent #1" in t for t in titles)
        assert any("SubAgent #1 Report" in t for t in titles)
        assert any("Phase 1 Complete" in t for t in titles)
        assert any("SONIC Boss Report" in t for t in titles)


@pytest.mark.asyncio
async def test_workstation_routes_simple_prompt_to_single_agent(monkeypatch):
    """Verify that a simple prompt bypasses BossAgent and uses ComputerUseAgent."""
    tenant_id = "test-tenant-simple-int"
    session_id = "simple-int-sess-1"
    state = _get_or_create_session(tenant_id, session_id)
    state["desktop"] = {"workspace_id": "ws-simple-int"}

    mock_computer = MagicMock()
    mock_screen = MagicMock(desktop_state="LIVE", width=1280, height=800, visible_text="", detected_controls=[])
    mock_computer.screenshot = AsyncMock(return_value=mock_screen)
    mock_computer.terminal = AsyncMock(side_effect=[MagicMock(stdout="/root"), MagicMock(stdout="file.txt")])
    monkeypatch.setattr("sonic.api.routes.workstation.get_daytona_computer", lambda: mock_computer)

    mock_agent_inst = MagicMock()
    mock_agent_inst.max_actions = 8
    mock_agent_inst.run_mission = AsyncMock(return_value=[])
    mock_agent_cls = MagicMock(return_value=mock_agent_inst)
    monkeypatch.setattr("sonic.computer_use.agent.ComputerUseAgent", mock_agent_cls)

    mock_boss_cls = MagicMock()
    monkeypatch.setattr("sonic.computer_use.boss.BossAgent", mock_boss_cls)

    await _run_prompt_reasoning(tenant_id, session_id, "hostname")

    mock_boss_cls.assert_not_called()
    mock_agent_cls.assert_called_once()
    assert state["status"] == "IDLE"


@pytest.mark.asyncio
async def test_director_coordinates_with_boss_agent():
    """Verify that MissionDirector uses BossAgent for complex missions and stashes all traces."""
    class _MockWs:
        id = "ws-dir-test"
        workspace_id = "ws-dir-test"

    class _MockComputer:
        async def create(self, **kw):
            return _MockWs()
        compute = MagicMock()
        terminal = AsyncMock(return_value=MagicMock(stdout="ok", exit_code=0))
        screenshot = AsyncMock(return_value=MagicMock(data=b""))

    director = MissionDirector(
        computer_provider=_MockComputer(),
        autonomy_level=ComputerAutonomyLevel.L3_AUTONOMOUS,
    )
    state = await director.create_mission(
        tenant_id="tenant-boss-dir",
        goal="Audit and remediate multi-step vulnerability in auth service",
    )

    mock_traces = [
        ComputerDecisionTrace(
            action_type=ComputerActionType.FILE_READ,
            target_resource="auth.py",
            predicted_outcome="inspect",
            actual_observation="found vulnerability",
            status="SUCCESS",
        ),
        ComputerDecisionTrace(
            action_type=ComputerActionType.FILE_WRITE,
            target_resource="auth.py",
            predicted_outcome="patch",
            actual_observation="patched",
            status="SUCCESS",
        ),
    ]
    mock_report = BossReport(
        objective=state.objective.goal,
        status="COMPLETE",
        all_traces=mock_traces,
        total_sub_agents=2,
        total_actions=2,
        total_phases=2,
        findings_summary="Vulnerability resolved across 2 phases.",
    )

    with patch("sonic.computer_use.boss.BossAgent.run", new=AsyncMock(return_value=mock_report)) as mock_boss_run, \
         patch("sonic.agents.browser_agent.BrowserAgent.launch", new=AsyncMock()):
        result_state = await director.coordinate(state.mission_id)

        assert mock_boss_run.called
        stashed = getattr(result_state, "_last_traces", [])
        assert len(stashed) == 2
        assert stashed[0].target_resource == "auth.py"
        assert stashed[1].target_resource == "auth.py"

        summary = director.get_knowledge_summary(state.mission_id)
        assert summary.confidence == 1.0
        assert any("found vulnerability" in k for k in summary.what_we_know)


@pytest.mark.asyncio
async def test_boss_emits_sub_agent_number_in_sub_report():
    """Verify that BossAgent.run emits sub_agent_number in the sub_report event payload."""
    from sonic.computer_use.boss import BossAgent
    import json

    decomp_json = json.dumps({
        "thinking": "Single task phase",
        "phase_name": "Testing",
        "sub_missions": [
            {"goal": "Check target status", "max_steps": 2, "priority": 1},
        ],
    })
    llm = AsyncMock()
    llm.complete = AsyncMock(side_effect=[
        MagicMock(content=decomp_json, reasoning_content="", latency_ms=10),
        MagicMock(content="Found 200 OK", reasoning_content="", latency_ms=10),
        MagicMock(content="Phase done", reasoning_content="", latency_ms=10),
        MagicMock(content=json.dumps({"complete": True}), reasoning_content="", latency_ms=10),
        MagicMock(content="Final report", reasoning_content="", latency_ms=10),
    ])
    computer = AsyncMock()

    emitted_sub_reports = []

    async def _on_event(event_type, data):
        if event_type == "sub_report":
            emitted_sub_reports.append(data)

    mock_trace = ComputerDecisionTrace(
        action_type=ComputerActionType.TERMINAL_EXEC,
        target_resource="curl target.com",
        predicted_outcome="response",
        actual_observation="HTTP 200 OK with PHP/7.4",
        status="SUCCESS",
    )

    with patch("sonic.computer_use.agent.ComputerUseAgent") as MockAgentClass:
        mock_agent = MagicMock()
        mock_agent.run_mission = AsyncMock(return_value=[mock_trace])
        MockAgentClass.return_value = mock_agent

        boss = BossAgent(computer_provider=computer, llm_router=llm)
        report = await boss.run(workspace_id="ws-sub-num", objective="Check target status", phase_callback=_on_event)

        assert len(emitted_sub_reports) == 1
        assert "sub_agent_number" in emitted_sub_reports[0]
        assert emitted_sub_reports[0]["sub_agent_number"] == 1


def test_boss_extract_key_discoveries_filters_diagnostic_commands_and_raw_ips():
    """Verify that _extract_key_discoveries filters local diagnostic commands and raw IPs."""
    from sonic.computer_use.boss import BossAgent

    boss = BossAgent(computer_provider=AsyncMock(), llm_router=AsyncMock())

    diag_traces = [
        ComputerDecisionTrace(
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="curl ifconfig.me",
            predicted_outcome="ip",
            actual_observation="198.51.100.22",
            status="SUCCESS",
        ),
        ComputerDecisionTrace(
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="curl -s icanhazip.com",
            predicted_outcome="ip",
            actual_observation="198.51.100.22",
            status="SUCCESS",
        ),
        ComputerDecisionTrace(
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="whoami",
            predicted_outcome="user",
            actual_observation="root_user_1234",
            status="SUCCESS",
        ),
        ComputerDecisionTrace(
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="uname -a",
            predicted_outcome="kernel",
            actual_observation="Linux workstation 5.15.0-generic x86_64",
            status="SUCCESS",
        ),
        ComputerDecisionTrace(
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="pwd",
            predicted_outcome="dir",
            actual_observation="/home/daytona/workspace",
            status="SUCCESS",
        ),
        ComputerDecisionTrace(
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="hostname",
            predicted_outcome="host",
            actual_observation="workstation-box-1",
            status="SUCCESS",
        ),
        ComputerDecisionTrace(
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="ip addr show",
            predicted_outcome="net",
            actual_observation="1: lo: <LOOPBACK> inet 127.0.0.1/8",
            status="SUCCESS",
        ),
        ComputerDecisionTrace(
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="ip a",
            predicted_outcome="net",
            actual_observation="2: eth0: <BROADCAST> inet 10.0.0.5/24",
            status="SUCCESS",
        ),
        ComputerDecisionTrace(
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="ifconfig",
            predicted_outcome="net",
            actual_observation="eth0: flags=4163<UP,BROADCAST>",
            status="SUCCESS",
        ),
        ComputerDecisionTrace(
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="route -n",
            predicted_outcome="route",
            actual_observation="Kernel IP routing table 0.0.0.0 10.0.0.1",
            status="SUCCESS",
        ),
        # Dict trace with payload matching diagnostic command
        {
            "target_resource": "bash",
            "payload": "whoami",
            "actual_observation": "root_user_admin",
            "status": "SUCCESS",
        },
        # Legitimate security discovery
        ComputerDecisionTrace(
            action_type=ComputerActionType.TERMINAL_EXEC,
            target_resource="curl http://target.com/api/users",
            predicted_outcome="leak",
            actual_observation="Vulnerability found: SQL injection at /api/users\nDetails...",
            status="SUCCESS",
        ),
    ]

    discoveries = boss._extract_key_discoveries(diag_traces)
    assert len(discoveries) == 1
    assert "SQL injection at /api/users" in discoveries[0]


@pytest.mark.asyncio
async def test_boss_sub_goal_filters_raw_ips_and_diagnostic_context():
    """Verify that _dispatch_sub_agent does not append raw IPs or diagnostic strings to sub_goal."""
    from sonic.computer_use.boss import BossAgent

    boss = BossAgent(computer_provider=AsyncMock(), llm_router=AsyncMock())
    boss._accumulated_context = [
        "198.51.100.22",
        "curl ifconfig.me: 198.51.100.22",
        "whoami: root",
        "http://10.0.0.5:8080",
        "Found open port 8080 with vulnerable web server",
    ]

    dispatched_goals = []

    with patch("sonic.computer_use.agent.ComputerUseAgent") as MockAgentClass:
        mock_agent = MagicMock()
        async def fake_run_mission(workspace_id, goal, steps, step_callback=None):
            dispatched_goals.append(goal)
            return []
        mock_agent.run_mission = AsyncMock(side_effect=fake_run_mission)
        MockAgentClass.return_value = mock_agent

        sub_mission = SubMission(id="sub-ctx-test", goal="Attack target service", max_steps=2)
        await boss._dispatch_sub_agent("ws-1", sub_mission)

        assert len(dispatched_goals) == 1
        goal = dispatched_goals[0]
        # Raw IP addresses and diagnostic strings must not be in the goal
        assert "198.51.100.22" not in goal
        assert "whoami" not in goal
        assert "10.0.0.5" not in goal
        # Legitimate discovery should be present
        assert "Found open port 8080 with vulnerable web server" in goal


