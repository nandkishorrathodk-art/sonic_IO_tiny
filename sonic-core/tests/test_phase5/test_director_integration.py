"""
End-to-End Integration Tests for Director, Event-Driven Scheduling, Replan Loop, and State Recovery.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from sonic.agents.director import Director, AgentInput, AgentOutput
from sonic.agents.cognitive_state import CognitiveState, EngagementBudget
from sonic.agents.task_graph import TaskGraph, TaskStatus
from sonic.agents.state_store import StateStore
from sonic.memory.inmemory import InMemoryGraph
from sonic.safety.scope import ScopeChecker
from sonic.llm.router import ModelRouter
from sonic.llm.schemas import LLMResponse


def get_mock_router():
    router = MagicMock(spec=ModelRouter)
    # Default mock response returning valid JSON plan/replan
    async def _complete(req, task_type="planning"):
        if "replan" in req.messages[-1].content.lower() or "trigger" in req.messages[-1].content.lower():
            return LLMResponse(
                content="""```json
{
    "should_replan": true,
    "reasoning": "New endpoint /api/v2/tokens discovered. Need auth analysis.",
    "new_tasks": [
        {
            "name": "Dynamic: Test /api/v2/tokens",
            "agent_type": "dynamic",
            "task_payload": {"target": "target.com/api/v2/tokens"},
            "depends_on_completed": [],
            "priority": "high"
        }
    ],
    "tasks_to_skip": [],
    "updated_unknowns": [{"question": "Is /api/v2/tokens authenticated?"}],
    "updated_next_action": "Execute token testing",
    "confidence": 0.8
}
```""",
                model="test-model",
            )
        return LLMResponse(
            content="""```json
{
    "assumptions": ["target.com has REST APIs"],
    "unknowns": ["What subdomains exist?"],
    "tasks": [
        {
            "name": "Recon-A: Subdomain Enumeration",
            "agent_type": "recon",
            "priority": "high",
            "depends_on": [],
            "payload": {"target": "target.com", "task": "subdomains"}
        },
        {
            "name": "Recon-B: Port Scan",
            "agent_type": "recon",
            "priority": "medium",
            "depends_on": [],
            "payload": {"target": "target.com", "task": "ports"}
        }
    ]
}
```""",
            model="test-model",
        )
    router.complete = AsyncMock(side_effect=_complete)
    return router


def test_director_deterministic_e2e_flow():
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

        # 1. Start engagement
        engagement_id = await director.start_engagement(
            target="target.com",
            scope={"allowed_domains": ["target.com"]},
            tenant_id="tenant-acme",
            created_by="auditor@acme.org",
        )
        assert engagement_id.startswith("eng-")

        # Verify initial state and graph
        state_summary = director.get_engagement_state(engagement_id)
        assert state_summary is not None
        assert state_summary["unresolved_unknowns_count"] >= 1

        graph = director._graphs[engagement_id]
        assert graph.size == 2

        # 2. Scheduler finds ready tasks
        dispatchable = director.get_dispatchable_tasks(engagement_id)
        assert len(dispatchable) == 2
        task1 = dispatchable[0]
        assert task1["tenant_id"] == "tenant-acme"
        assert task1["engagement_id"] == engagement_id

        # 3. Simulate Recon-A completing with new discovery
        recon_a_output = AgentOutput(
            observations=[
                {"description": "Discovered new endpoint /api/v2/tokens", "raw_data": "HTTP 200 OK"}
            ],
            facts=[
                {"description": "Target hosts /api/v2/tokens on port 443", "evidence_ids": ["ev-1"]}
            ],
            hypotheses=[
                {
                    "title": "Unauthenticated Token Leakage",
                    "description": "Tokens can be fetched without auth header",
                    "vulnerability_class": "Auth Bypass",
                }
            ],
            evidence_refs=[
                {"evidence_type": "request", "description": "GET /api/v2/tokens", "storage_key": "s3://ev-1"}
            ],
        )

        res1 = await director.on_task_completed(
            engagement_id=engagement_id,
            task_id=task1["task_id"],
            result=recon_a_output.to_dict(),
        )

        # Verify replan was triggered and injected new task
        assert res1["facts_ingested"] == 1
        assert res1["hypotheses_ingested"] == 1
        assert "tasks_added" in res1["replan"]
        assert len(res1["replan"]["tasks_added"]) == 1

        # Graph size should now be 3 (2 initial + 1 injected)
        assert graph.size == 3

        # 4. Simulate Recon-B completing
        task2 = dispatchable[1]
        recon_b_output = AgentOutput(
            facts=[{"description": "Ports 80, 443 open"}],
        )
        res2 = await director.on_task_completed(
            engagement_id=engagement_id,
            task_id=task2["task_id"],
            result=recon_b_output.to_dict(),
        )

        # 5. Simulate the injected Dynamic tasks completing until graph is complete
        loop_guard = 0
        while not graph.is_complete() and loop_guard < 10:
            loop_guard += 1
            injected_ready = director.get_dispatchable_tasks(engagement_id)
            if not injected_ready:
                break
            for inj_task in injected_ready:
                dynamic_output = AgentOutput(
                    facts=[{"description": "Token leakage confirmed with HTTP 200"}],
                    findings=[
                        {
                            "title": "Critical Token Leak on /api/v2/tokens",
                            "severity": "critical",
                            "vulnerability_class": "Auth Bypass",
                        }
                    ],
                )
                await director.on_task_completed(
                    engagement_id=engagement_id,
                    task_id=inj_task["task_id"],
                    result=dynamic_output.to_dict(),
                )

        final_summary = director.get_engagement_state(engagement_id)
        assert final_summary["facts_count"] >= 3
        assert final_summary["replan_count"] >= 1
        assert graph.is_complete() is True

    asyncio.run(_run())


def test_director_concurrency_limit():
    async def _run():
        mock_router = get_mock_router()
        memory = InMemoryGraph()
        scope = ScopeChecker()
        state_store = StateStore(redis_client=None)

        director = Director(
            model_router=mock_router,
            graph_memory=memory,
            scope_checker=scope,
            state_store=state_store,
            max_parallel=1,  # Max 1 concurrent task
        )

        engagement_id = await director.start_engagement(
            target="target.com",
            scope={},
            tenant_id="tenant-concurrency",
        )

        # Even though 2 tasks are ready, only 1 should be dispatched due to max_parallel=1
        dispatchable = director.get_dispatchable_tasks(engagement_id)
        assert len(dispatchable) == 1

        # Second call should return 0 since 1 is running and max_parallel=1
        dispatchable_2 = director.get_dispatchable_tasks(engagement_id)
        assert len(dispatchable_2) == 0

    asyncio.run(_run())


def test_director_pause_and_resume():
    async def _run():
        mock_router = get_mock_router()
        memory = InMemoryGraph()
        scope = ScopeChecker()
        state_store = StateStore(redis_client=None)

        director = Director(
            model_router=mock_router,
            graph_memory=memory,
            scope_checker=scope,
            state_store=state_store,
        )

        engagement_id = await director.start_engagement(
            target="target.com",
            scope={},
            tenant_id="tenant-pause",
        )

        paused = await director.pause_engagement(engagement_id)
        assert paused is True

        resumed = await director.resume_engagement(engagement_id)
        assert resumed is True

    asyncio.run(_run())
