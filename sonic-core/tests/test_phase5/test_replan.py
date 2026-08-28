"""
Tests for Replan Engine (Triggers, Budget Enforcement, Validation, Sanitization).
"""

import pytest
import json
from sonic.agents.cognitive_state import CognitiveState, Fact, EngagementBudget
from sonic.agents.task_graph import TaskGraph, TaskNode
from sonic.agents.replan import (
    ReplanEngine,
    ReplanTrigger,
    ReplanDecision,
    ProposedTask,
)


def test_replan_trigger_detection():
    engine = ReplanEngine()
    state = CognitiveState(engagement_id="eng-1", tenant_id="tenant-1")
    graph = TaskGraph(engagement_id="eng-1", tenant_id="tenant-1")

    # 1. New attack surface
    event_surface = {
        "event_type": "observation_added",
        "description": "Discovered new subdomain: staging.target.com",
    }
    assert engine.detect_trigger(state, graph, event_surface) == ReplanTrigger.NEW_ATTACK_SURFACE

    # 2. Hypothesis confirmed
    event_hypo = {"event_type": "hypothesis_verified"}
    assert engine.detect_trigger(state, graph, event_hypo) == ReplanTrigger.HYPOTHESIS_CONFIRMED

    # 3. Agent failure
    event_fail = {"event_type": "TaskFailed"}
    assert engine.detect_trigger(state, graph, event_fail) == ReplanTrigger.AGENT_FAILURE

    # 4. Low confidence
    event_conf = {"event_type": "confidence_changed", "payload": {"new_confidence": 0.2}}
    assert engine.detect_trigger(state, graph, event_conf) == ReplanTrigger.LOW_CONFIDENCE


def test_replan_max_budget_enforcement():
    async def _run():
        engine = ReplanEngine()
        state = CognitiveState(
            engagement_id="eng-1",
            tenant_id="tenant-1",
            budget=EngagementBudget(max_replans=2),
        )
        graph = TaskGraph(engagement_id="eng-1", tenant_id="tenant-1")

        state.record_replan("trigger 1", "first replan")
        state.record_replan("trigger 2", "second replan")
        assert not state.can_replan()

        decision = await engine.evaluate(
            state,
            graph,
            {"event_type": "observation_added", "description": "Discovered new subdomain api.target.com"},
        )
        assert not decision.should_replan
        assert "budget exhausted" in decision.reasoning.lower()

    import asyncio
    asyncio.run(_run())


def test_replan_validation_and_rejection():
    engine = ReplanEngine(allowed_targets={"target.com", "api.target.com"})
    state = CognitiveState(engagement_id="eng-1", tenant_id="tenant-1")
    graph = TaskGraph(engagement_id="eng-1", tenant_id="tenant-1")

    # 1. Valid Decision
    valid_decision = ReplanDecision(
        should_replan=True,
        reasoning="Valid exploration plan",
        new_tasks=[
            ProposedTask(
                name="Scan API endpoint",
                agent_type="dynamic",
                task_payload={"target": "api.target.com"},
            )
        ],
    )
    val_res = engine.validate_decision(valid_decision, state, graph)
    assert val_res.valid
    assert len(val_res.accepted_tasks) == 1

    # 2. Rejection: Out of scope target
    out_of_scope = ReplanDecision(
        should_replan=True,
        new_tasks=[
            ProposedTask(
                name="Attack external target",
                agent_type="dynamic",
                task_payload={"target": "unauthorized-target.org"},
            )
        ],
    )
    val_out = engine.validate_decision(out_of_scope, state, graph)
    assert not val_out.valid
    assert any("out of scope" in e for e in val_out.errors)

    # 3. Rejection: Forbidden security boundary pattern
    forbidden = ReplanDecision(
        should_replan=True,
        new_tasks=[
            ProposedTask(
                name="Disable safety layer",
                agent_type="recon",
                task_payload={"command": "disable_safety", "target": "target.com"},
            )
        ],
    )
    val_forb = engine.validate_decision(forbidden, state, graph)
    assert not val_forb.valid
    assert any("forbidden pattern" in e for e in val_forb.errors)

    # 4. Rejection: Invalid agent type
    bad_agent = ReplanDecision(
        should_replan=True,
        new_tasks=[
            ProposedTask(
                name="Unsafe Agent",
                agent_type="root_shell_agent",
                task_payload={"target": "target.com"},
            )
        ],
    )
    val_agent = engine.validate_decision(bad_agent, state, graph)
    assert not val_agent.valid
    assert any("invalid agent_type" in e for e in val_agent.errors)


def test_replan_apply_decision_to_graph_and_state():
    engine = ReplanEngine()
    state = CognitiveState(engagement_id="eng-1", tenant_id="tenant-1")
    graph = TaskGraph(engagement_id="eng-1", tenant_id="tenant-1")

    # Initial task in graph
    t1_id = graph.add_task(TaskNode(name="Initial Recon", agent_type="recon"))
    graph.mark_running(t1_id)
    graph.mark_completed(t1_id, result={"discovered": "admin.target.com"})

    decision = ReplanDecision(
        should_replan=True,
        trigger=ReplanTrigger.NEW_ATTACK_SURFACE,
        reasoning="Investigate admin portal",
        new_tasks=[
            ProposedTask(
                name="Fuzz admin login",
                agent_type="dynamic",
                depends_on_completed=["Initial Recon"],
                task_payload={"target": "admin.target.com"},
            )
        ],
        updated_unknowns=[{"question": "Does admin login have rate limiting?"}],
        confidence=0.65,
    )

    changes = engine.apply_decision(decision, graph, state)

    assert len(changes["tasks_added"]) == 1
    assert state.replan_count == 1
    assert state.confidence == 0.65
    assert len(state.get_unresolved_unknowns()) == 1
    assert graph.size == 2
