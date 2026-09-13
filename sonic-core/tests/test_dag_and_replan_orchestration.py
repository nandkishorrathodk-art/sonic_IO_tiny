"""Comprehensive tests for TaskGraph, ReplanEngine, MetaOrchestrator, and Director wiring."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from sonic.agents.orchestrator import MetaOrchestrator
from sonic.agents.replan import ReplanEngine, ReplanTrigger
from sonic.agents.task_graph import TaskGraph, TaskNode, TaskPriority, TaskStatus
from sonic.computer_use.boss import BossAgent
from sonic.computer_use.models_boss import Phase, SubMission, SubMissionResult


def _make_llm_mock(responses: list[str]):
    """Create a mock LLM router that returns responses in order."""
    mock = AsyncMock()
    results = []
    for r in responses:
        resp = MagicMock()
        resp.content = r
        resp.reasoning_content = ""
        resp.latency_ms = 50
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


# =====================================================================
# 1. BossAgent + TaskGraph DAG Integration
# =====================================================================

@pytest.mark.asyncio
async def test_boss_agent_populates_task_graph_from_phase():
    """BossAgent synchronizes decomposed phases into a real TaskGraph DAG."""
    decomp_json = json.dumps({
        "thinking": "Recon first then form analysis.",
        "phase_name": "Discovery",
        "sub_missions": [
            {"goal": "Scan ports and services", "max_steps": 3, "priority": 2},
            {"goal": "Map web forms", "max_steps": 3, "priority": 1},
        ],
    })
    llm = _make_llm_mock([decomp_json])
    computer = _make_computer_mock()

    boss = BossAgent(computer_provider=computer, llm_router=llm, tenant_id="tenant-dag")
    phase = await boss._strategic_decomposition("audit target.com")
    assert phase is not None

    boss._sync_phase_to_graph(phase)

    # Verify task_graph contains the sub-missions
    assert boss.task_graph.size == 2
    for sub in phase.sub_missions:
        task = boss.task_graph.get_task(sub.id)
        assert task is not None
        assert task.agent_type == "dynamic"
        assert task.tenant_id == "tenant-dag"
        assert task.status == TaskStatus.READY


@pytest.mark.asyncio
async def test_boss_agent_tracks_task_graph_lifecycle_during_run():
    """BossAgent updates TaskGraph node statuses as SubAgents execute."""
    from unittest.mock import patch
    from sonic.computer_use.models import ComputerActionType, ComputerDecisionTrace, ActionExecutionStatus

    decomp_json = json.dumps({
        "thinking": "Single worker task.",
        "phase_name": "Scan",
        "sub_missions": [
            {"goal": "Enumerate endpoints", "max_steps": 2, "priority": 1},
        ],
    })
    llm = _make_llm_mock([
        decomp_json,
        "Found /login and /api endpoints.",  # sub-agent summary
        json.dumps({"findings": ["2 endpoints discovered"], "next_priorities": []}),  # aggregation
        json.dumps({"complete": True, "reason": "Endpoints mapped"}),  # completion check
        json.dumps({"executive_summary": "Scan complete", "key_findings": ["2 endpoints"]}),  # final report
    ])
    computer = _make_computer_mock()

    trace = ComputerDecisionTrace(
        action_type=ComputerActionType.TERMINAL_EXEC,
        target_resource="curl /api",
        predicted_outcome="Discover endpoints",
        actual_observation="Found /login and /api",
        status=ActionExecutionStatus.COMPLETED,
    )

    with patch("sonic.computer_use.agent.ComputerUseAgent") as MockAgentClass:
        mock_agent = MagicMock()
        mock_agent.run_mission = AsyncMock(return_value=[trace])
        MockAgentClass.return_value = mock_agent

        boss = BossAgent(computer_provider=computer, llm_router=llm)

        events = []
        def on_event(event_type, data):
            events.append((event_type, data))

        report = await boss.run(
            workspace_id="ws-test",
            objective="Find endpoints on target.com",
            phase_callback=on_event,
        )

        assert report.status == "COMPLETE"
        assert boss.task_graph.size >= 1
        # Tasks should be SUCCEEDED in the graph
        ready_tasks = boss.task_graph.get_ready_tasks()
        assert len(ready_tasks) == 0  # no pending ready tasks remaining
        assert boss.task_graph.is_complete()


# =====================================================================
# 2. BossAgent + ReplanEngine Triggers
# =====================================================================

def test_boss_detects_new_attack_surface_trigger():
    """BossAgent detects NEW_ATTACK_SURFACE trigger when endpoints/parameters are found."""
    boss = BossAgent(computer_provider=MagicMock(), llm_router=MagicMock())
    result = SubMissionResult(
        sub_mission_id="sub-1",
        goal="Discover endpoints",
        success=True,
        findings_summary="Discovered 5 new URL endpoints and 3 search parameters.",
        key_discoveries=["/api/v1/search?q= found", "/admin/login route mapped"],
    )
    trigger = boss._detect_sub_mission_trigger(result)
    assert trigger == ReplanTrigger.NEW_ATTACK_SURFACE


def test_boss_detects_high_confidence_finding_trigger():
    """BossAgent detects NEW_HIGH_CONFIDENCE_FINDING when SQLi or vulnerability is found."""
    boss = BossAgent(computer_provider=MagicMock(), llm_router=MagicMock())
    result = SubMissionResult(
        sub_mission_id="sub-2",
        goal="Test login form",
        success=True,
        evidence_verified=True,
        findings_summary="SQL injection confirmed on 'id' parameter with error-based payload.",
        key_discoveries=["SQLi vulnerability exploited"],
    )
    trigger = boss._detect_sub_mission_trigger(result)
    assert trigger == ReplanTrigger.NEW_HIGH_CONFIDENCE_FINDING


def test_boss_detects_agent_failure_trigger():
    """BossAgent detects AGENT_FAILURE trigger when a SubAgent fails."""
    boss = BossAgent(computer_provider=MagicMock(), llm_router=MagicMock())
    result = SubMissionResult(
        sub_mission_id="sub-3",
        goal="Reach internal port",
        success=False,
        findings_summary="Connection timed out on port 8080.",
    )
    trigger = boss._detect_sub_mission_trigger(result)
    assert trigger == ReplanTrigger.AGENT_FAILURE


# =====================================================================
# 3. MetaOrchestrator Execution via TaskGraph
# =====================================================================

@pytest.mark.asyncio
async def test_meta_orchestrator_executes_tasks_with_worker_fn():
    """MetaOrchestrator builds a TaskGraph and executes tasks via worker_fn."""
    plan_json = json.dumps({
        "target_summary": "Test Target",
        "estimated_phases": 2,
        "phases": [
            {
                "name": "Recon",
                "agent": "recon",
                "tasks": ["subdomain_enum"],
                "priority": "high",
            },
            {
                "name": "Testing",
                "agent": "dynamic",
                "tasks": ["sqli_check"],
                "priority": "critical",
            },
        ],
        "priority_vuln_classes": ["SQLi"],
        "estimated_time_minutes": 10,
    })

    eval_json = json.dumps({
        "action": "complete",
        "reason": "Vulnerability found and validated",
        "next_priorities": [],
    })

    llm = _make_llm_mock([plan_json, eval_json])

    executed_tasks = []
    async def dummy_worker(task_data):
        executed_tasks.append(task_data["name"])
        if "sqli_check" in task_data["name"]:
            return {
                "findings": [{"title": "SQL Injection", "severity": "critical"}],
                "status": "success",
            }
        return {"findings": [], "status": "success"}

    orchestrator = MetaOrchestrator(model_router=llm, tenant_id="tenant-orch")
    results = await orchestrator.run({
        "target": "example.com",
        "worker_fn": dummy_worker,
    })

    assert results["target"] == "example.com"
    assert len(results["phases_completed"]) == 2
    assert "Recon" in results["phases_completed"]
    assert "Testing" in results["phases_completed"]
    assert len(results["findings_summary"]) == 1
    assert results["findings_summary"][0]["title"] == "SQL Injection"
    assert len(executed_tasks) == 2
    assert any("subdomain_enum" in t for t in executed_tasks)
    assert any("sqli_check" in t for t in executed_tasks)


# =====================================================================
# 4. Director.run_engagement_loop
# =====================================================================

@pytest.mark.asyncio
async def test_director_run_engagement_loop_completes_graph():
    """Director.run_engagement_loop executes dispatchable tasks and marks graph complete."""
    from sonic.agents.director import Director
    from sonic.agents.state_store import StateStore
    from sonic.memory.inmemory import InMemoryGraph
    from sonic.safety.scope import ScopeChecker

    # Setup Director with in-memory test components
    router = _make_llm_mock([
        json.dumps({
            "assumptions": ["Standard web server"],
            "unknowns": ["What services are exposed?"],
            "tasks": [
                {
                    "name": "Port Scan",
                    "agent_type": "recon",
                    "priority": "high",
                    "depends_on": [],
                    "payload": {"target": "10.0.0.1"},
                },
            ],
        })
    ])
    director = Director(
        model_router=router,
        graph_memory=InMemoryGraph(),
        scope_checker=ScopeChecker(),
        state_store=StateStore(),
    )

    eid = await director.start_engagement(
        target="10.0.0.1",
        scope={"target": "10.0.0.1"},
        tenant_id="test-tenant",
    )

    executed = []
    async def test_worker(payload):
        executed.append(payload["task_id"])
        return {
            "observations": [{"description": "Port 80 open"}],
            "facts": [{"description": "HTTP server running"}],
            "findings": [{"title": "Exposed Port 80", "severity": "low"}],
        }

    loop_res = await director.run_engagement_loop(eid, worker_fn=test_worker)

    assert loop_res["completed"] == 1
    assert loop_res["failed"] == 0
    assert loop_res["graph_complete"] is True
    assert len(loop_res["findings"]) == 1
    assert loop_res["findings"][0]["title"] == "Exposed Port 80"
    assert len(executed) == 1
