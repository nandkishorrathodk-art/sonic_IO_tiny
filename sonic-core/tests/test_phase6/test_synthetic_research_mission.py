"""
Synthetic Mission Test: Complete Phase 6 Research & Critical Thinking Lifecycle.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from sonic.agents.director import Director, AgentInput, AgentOutput
from sonic.agents.cognitive_state import CognitiveState, EngagementBudget
from sonic.agents.task_graph import TaskGraph
from sonic.agents.state_store import StateStore
from sonic.memory.inmemory import InMemoryGraph
from sonic.safety.scope import ScopeChecker
from sonic.llm.router import ModelRouter
from sonic.llm.schemas import LLMResponse
from tests.test_phase5.test_director_integration import get_mock_router


def test_synthetic_research_mission_lifecycle():
    async def _run():
        mock_router = get_mock_router()
        memory = InMemoryGraph()
        await memory.init_schema()
        scope = ScopeChecker()
        state_store = StateStore(redis_client=None)

        director = Director(
            model_router=mock_router,
            graph_memory=memory,
            scope_checker=scope,
            state_store=state_store,
            max_parallel=2,
        )

        # 1. Start mission
        engagement_id = await director.start_engagement(
            target="target-api.corp",
            scope={"target": "target-api.corp"},
            tenant_id="tenant-research",
            created_by="researcher@corp.org",
        )

        state = director._states[engagement_id]
        graph = director._graphs[engagement_id]

        # 2. Get ready tasks — verify Prediction and Decision Trace were recorded
        dispatchable = director.get_dispatchable_tasks(engagement_id)
        assert len(dispatchable) > 0
        assert len(state.predictions) > 0
        assert len(state.decision_traces) > 0

        # Verify Decision Trace content
        trace = state.decision_traces[0]
        assert trace.selected_action != ""
        assert trace.expected_information_gain > 0

        # 3. Simulate completion for initial dispatched tasks
        result_1 = AgentOutput(
            observations=[{"description": "Endpoint /api/v2/tokens responded with HTTP 200"}],
            facts=[{"description": "Server runs Node.js express behind proxy"}],
            hypotheses=[{"title": "JWT None Algorithm Bypass", "vulnerability_class": "Auth Bypass"}],
        )

        for task_info in dispatchable:
            await director.on_task_completed(
                engagement_id=engagement_id,
                task_id=task_info["task_id"],
                result=result_1.to_dict(),
            )

        # 4. Verify Prediction Comparison recorded
        assert len(state.prediction_comparisons) > 0
        comp = state.prediction_comparisons[0]
        assert comp.prediction_error <= 0.5

        # 5. Verify transparent confidence recalculation
        assert state.confidence > 0.0
        assert state.confidence_breakdown is not None

        # 6. Drain any remaining injected tasks
        loop_count = 0
        while not graph.is_complete() and loop_count < 10:
            loop_count += 1
            ready = director.get_dispatchable_tasks(engagement_id)
            if not ready:
                break
            for t in ready:
                await director.on_task_completed(
                    engagement_id=engagement_id,
                    task_id=t["task_id"],
                    result=AgentOutput().to_dict(),
                )

        assert graph.is_complete() is True

    asyncio.run(_run())
