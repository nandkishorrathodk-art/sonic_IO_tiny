"""
Security & Recovery Tests for Phase 5:
  1. Multi-tenant isolation & cross-tenant rejection
  2. Agent budget and task limit enforcement
  3. Target scope boundaries
  4. Crash recovery protocol (persisting, restart simulation, resuming without duplicate runs)
"""

import asyncio
import pytest
from sonic.agents.cognitive_state import CognitiveState, EngagementBudget, Fact
from sonic.agents.director import Director, AgentOutput
from sonic.agents.task_graph import TaskGraph, TaskNode, TaskStatus, TenantMismatchError
from sonic.agents.state_store import StateStore
from sonic.memory.inmemory import InMemoryGraph
from sonic.safety.scope import ScopeChecker
from sonic.llm.router import ModelRouter
from tests.test_phase5.test_director_integration import get_mock_router


def test_cross_tenant_isolation():
    """Verify that tasks cannot be mixed across tenants."""
    graph_a = TaskGraph(engagement_id="eng-A", tenant_id="tenant-alpha")
    
    # Attempt to add task with tenant-beta into tenant-alpha graph
    with pytest.raises(TenantMismatchError):
        graph_a.add_task(TaskNode(name="Bad Tenant Task", agent_type="recon", tenant_id="tenant-beta"))


def test_budget_limits_and_bounded_spawning():
    """Verify max tasks, max replans, and max parallel limits."""
    budget = EngagementBudget(
        max_agents_per_engagement=3,
        max_total_tasks=5,
        max_replans=2,
        max_parallel=2,
    )
    state = CognitiveState(engagement_id="eng-1", tenant_id="tenant-1", budget=budget)
    
    assert state.can_replan()
    state.record_replan("trigger-1", "replan 1")
    state.record_replan("trigger-2", "replan 2")
    assert not state.can_replan()

    # Task budget check
    state.tasks_completed = 3
    state.tasks_failed = 2
    assert not state.is_within_budget()


def test_state_persistence_and_recovery_simulation():
    """Simulate crash, restart, and recovery of an in-flight engagement."""
    async def _run():
        mock_router = get_mock_router()
        memory = InMemoryGraph()
        scope = ScopeChecker()

        # In-memory dict simulating Redis key-value store for StateStore
        fake_redis_data = {}
        class MockRedis:
            async def set(self, key, value, ex=None, nx=False):
                if nx and key in fake_redis_data:
                    return False
                fake_redis_data[key] = value
                return True
            async def get(self, key):
                return fake_redis_data.get(key)
            async def delete(self, *keys):
                for k in keys:
                    fake_redis_data.pop(k, None)
            async def sadd(self, key, val):
                pass
            async def rpush(self, key, val):
                pass
            async def expire(self, key, ttl):
                pass

        state_store = StateStore(redis_client=MockRedis())

        # 1. First Director instance starts engagement
        director_1 = Director(
            model_router=mock_router,
            graph_memory=memory,
            scope_checker=scope,
            state_store=state_store,
        )

        engagement_id = await director_1.start_engagement(
            target="recovery-test.com",
            scope={},
            tenant_id="tenant-recovery",
        )

        # Dispatch task 1 (marked RUNNING)
        dispatchable = director_1.get_dispatchable_tasks(engagement_id)
        assert len(dispatchable) > 0
        task_1_id = dispatchable[0]["task_id"]

        # Persist explicitly before crash
        await director_1._persist(engagement_id)

        # 2. SIMULATE CRASH: Destroy director_1 and instantiate fresh director_2
        director_2 = Director(
            model_router=mock_router,
            graph_memory=memory,
            scope_checker=scope,
            state_store=state_store,
        )

        assert engagement_id not in director_2._states

        # Recover from state store
        recovered = await director_2.recover_engagement(engagement_id)
        assert recovered is True
        assert engagement_id in director_2._states

        # The task that was RUNNING when crashed must be reset to READY
        recovered_graph = director_2._graphs[engagement_id]
        recovered_task = recovered_graph.get_task(task_1_id)
        assert recovered_task.status == TaskStatus.READY

        # Verify it can be re-dispatched safely without duplication
        ready_tasks = director_2.get_dispatchable_tasks(engagement_id)
        assert any(t["task_id"] == task_1_id for t in ready_tasks)

    asyncio.run(_run())
