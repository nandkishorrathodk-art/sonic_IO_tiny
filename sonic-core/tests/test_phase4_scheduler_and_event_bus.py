"""
Tests for Phase 4: Scheduler, Event Bus & Blackboard Coordination
==================================================================
Verifies:
1. EventBus typed topic publish/subscribe and delivery guarantees.
2. InformationGainCostScheduler mathematical priority calculation.
3. Scheduler concurrency bounds and task completion flow.
4. Shared Blackboard inter-specialist state sharing.
"""

from __future__ import annotations

import pytest

from sonic.kernel.event_bus import EventBus, EventTopic
from sonic.kernel.scheduler import Blackboard, InformationGainCostScheduler, ScheduledTask


@pytest.mark.no_live_infra
def test_event_bus_delivery():
    bus = EventBus()
    received_payloads = []

    def on_experiment_res(event):
        received_payloads.append(event.payload)

    bus.subscribe(EventTopic.EXPERIMENT_RESULT, on_experiment_res)

    bus.publish(
        topic=EventTopic.EXPERIMENT_RESULT,
        sender="web_specialist",
        payload={"exp_id": "exp-1", "status": "completed"},
    )

    assert len(received_payloads) == 1
    assert received_payloads[0]["exp_id"] == "exp-1"
    assert len(bus.get_events(EventTopic.EXPERIMENT_RESULT)) == 1


@pytest.mark.no_live_infra
def test_scheduler_priority_scoring_and_ordering():
    scheduler = InformationGainCostScheduler(max_concurrency=2)

    # Task A: High Info Gain, Low Cost (Should pop FIRST)
    task_a = ScheduledTask.create(
        name="IDOR probe on /api/profile",
        specialist_type="auth",
        expected_info_gain=5.0,
        impact_potential=4.0,
        confidence_opportunity=3.0,
        cost=1.0,
        estimated_time=1.0,
        risk=1.0,
        task_id="task-a",
    )  # Score = 5 * 4 * 3 / 1 = 60.0

    # Task B: Low Info Gain, High Cost, High Risk (Should pop SECOND)
    task_b = ScheduledTask.create(
        name="Brute force directory discovery",
        specialist_type="recon",
        expected_info_gain=1.0,
        impact_potential=1.0,
        confidence_opportunity=1.0,
        cost=10.0,
        estimated_time=5.0,
        risk=2.0,
        task_id="task-b",
    )  # Score = 1 / (10 * 5 * 2) = 0.01

    scheduler.enqueue(task_b)
    scheduler.enqueue(task_a)

    popped_1 = scheduler.pop_next()
    assert popped_1 is not None
    assert popped_1.task_id == "task-a"
    assert popped_1.score > 50.0

    popped_2 = scheduler.pop_next()
    assert popped_2 is not None
    assert popped_2.task_id == "task-b"


@pytest.mark.no_live_infra
def test_scheduler_concurrency_capping():
    scheduler = InformationGainCostScheduler(max_concurrency=1)

    t1 = ScheduledTask.create("T1", "web", task_id="t1")
    t2 = ScheduledTask.create("T2", "api", task_id="t2")

    scheduler.enqueue(t1)
    scheduler.enqueue(t2)

    active_1 = scheduler.pop_next()
    assert active_1.task_id == "t1"

    # Concurrency limit is 1, so pop_next() must return None while t1 is active
    assert scheduler.pop_next() is None
    assert scheduler.active_count() == 1

    # Complete t1
    scheduler.complete_task("t1")
    assert scheduler.active_count() == 0

    # Now t2 can pop
    active_2 = scheduler.pop_next()
    assert active_2.task_id == "t2"


@pytest.mark.no_live_infra
def test_blackboard_state_sharing():
    bb = Blackboard()
    bb.post("active_session_cookie", "session=abc123xyz")
    bb.post("open_ports", [80, 443, 8080])

    assert bb.get("active_session_cookie") == "session=abc123xyz"
    assert 8080 in bb.get("open_ports")
    assert bb.get("nonexistent", "default_val") == "default_val"
