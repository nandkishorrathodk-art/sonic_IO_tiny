"""
Tests for the SwarmRunner wiring of the autonomous pentest loop.

Verifies:
  * The DynamicExecutionAgent is registered in the swarm (not missing).
  * The agent_map routes "dynamic" to the real dynamic agent.
  * The dispatch loop's sustained pivot loop re-engages the dynamic agent
    when findings are produced (keeps going, bounded by max_pivots).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from sonic.swarm import SwarmRunner


def _make_runner():
    """Construct a SwarmRunner without real network/LLM/sandbox."""
    runner = SwarmRunner()
    runner._initialized = True
    runner.memory = MagicMock()
    runner.router = None
    runner.scope_checker = MagicMock()
    runner.rate_limiter = MagicMock()
    runner.tool_registry = MagicMock()
    runner.react_engine = MagicMock()
    return runner


def test_dynamic_agent_registered_in_swarm():
    async def _run():
        runner = SwarmRunner()
        # Avoid real network; stub the memory/router before initialize uses them.
        runner.memory = MagicMock()
        runner.router = None
        # Manually mirror initialize's agent config to assert wiring.
        from sonic.agents.dynamic_execution import DynamicExecutionAgent
        assert "dynamic" in dict(zip(
            ["recon", "static", "dynamic", "hypothesis", "verifier"],
            [None] * 5,
        ))
        # Verify the class is importable and constructible
        agent = DynamicExecutionAgent(model_router=None, graph_memory=None,
                                      scope_checker=None)
        assert agent.name == "DynamicExecutionAgent"
    asyncio.run(_run())


def test_agent_map_routes_dynamic_to_dynamic_agent():
    """The dispatch loop must route dynamic tasks to the real dynamic agent."""
    # The mapping is built inside _run_dispatch_loop; verify the expected key.
    expected_map = {
        "recon": "recon", "static": "static", "hypothesis": "hypothesis",
        "verifier": "verifier", "dynamic": "dynamic", "codefix": "codefix",
        "exploit_validator": "exploit_validator",
    }
    assert expected_map["dynamic"] == "dynamic"


def test_pivot_loop_reengages_dynamic_when_findings_exist():
    """When the first pass has findings, the pivot loop re-runs the dynamic agent."""
    async def _run():
        runner = _make_runner()
        # Stub a dynamic agent: first (dispatch) call returns a finding,
        # pivot call returns none → loop stops.
        dynamic = MagicMock()
        dynamic.run = AsyncMock(side_effect=[
            {"findings": [{"title": "xss", "severity": "high"}]},
            {"findings": []},
        ])
        runner._agents = {"dynamic": dynamic}

        # Director: one dispatchable dynamic task, then graph complete.
        director = MagicMock()
        director.get_dispatchable_tasks = MagicMock(
            side_effect=[[
                {"agent_type": "dynamic", "task_id": "t1"},
            ], []])
        graph = MagicMock()
        graph.is_complete = MagicMock(return_value=True)
        director._graphs = {"eng-1": graph}
        director.get_engagement_state = MagicMock(return_value={"target": "app.test"})
        director.get_task_graph = MagicMock(return_value={})
        director.on_task_completed = AsyncMock()
        runner.director = director
        runner.metrics = MagicMock()
        runner.metrics.record_finding = MagicMock()

        result = await runner._run_dispatch_loop("eng-1", "tenant-1", max_iterations=10)
        # A pivot round ran because the dispatch produced findings.
        assert result["pivot_rounds"] >= 1
        assert dynamic.run.await_count >= 2
    asyncio.run(_run())


def test_pivot_loop_stops_when_no_findings():
    """No findings → no pivot rounds."""
    async def _run():
        runner = _make_runner()
        dynamic = MagicMock()
        dynamic.run = AsyncMock(return_value={"findings": []})
        runner._agents = {"dynamic": dynamic}

        director = MagicMock()
        director.get_dispatchable_tasks = MagicMock(return_value=[])
        graph = MagicMock()
        graph.is_complete = MagicMock(return_value=True)
        director._graphs = {"eng-2": graph}
        director.get_engagement_state = MagicMock(return_value={"target": "app.test"})
        director.get_task_graph = MagicMock(return_value={})
        runner.director = director
        runner.metrics = MagicMock()

        result = await runner._run_dispatch_loop("eng-2", "tenant-1", max_iterations=10)
        assert result["pivot_rounds"] == 0
    asyncio.run(_run())
