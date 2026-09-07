"""
Tests for SONIC's Asynchronous Multi-Agent Research Framework:
  1. ResearchEventBus typed pub/sub and history.
  2. SpecialistAgent execution, state transitions, and budget enforcement.
  3. AsyncResearchOrchestrator concurrent parallel execution ("Sab kaam at the same time").
  4. Dynamic task decomposition (discoveries triggering specialized investigators).
  5. Priority scheduling, cancellation, and shared blackboard state.
"""

from __future__ import annotations

import asyncio

import pytest

from sonic.research.event_bus import (
    AnomalyDetectedEvent,
    EndpointDiscoveredEvent,
    HypothesisFalsifiedEvent,
    ResearchEvent,
    ResearchEventBus,
    TargetDiscoveredEvent,
    VulnerabilityVerifiedEvent,
)
from sonic.research.orchestrator import (
    AsyncResearchOrchestrator,
    ResearchResult,
)
from sonic.research.specialist import (
    FalsificationSpecialist,
    NetworkSpecialist,
    SpecialistAgent,
    SpecialistBudget,
    SpecialistState,
    WebSpecialist,
)

# =====================================================================
# 1. Event Bus Tests
# =====================================================================

@pytest.mark.asyncio
async def test_event_bus_typed_pub_sub():
    bus = ResearchEventBus()
    received_targets = []
    received_endpoints = []
    received_all = []

    async def on_target(evt: TargetDiscoveredEvent):
        received_targets.append(evt)

    async def on_endpoint(evt: EndpointDiscoveredEvent):
        received_endpoints.append(evt)

    async def on_any(evt: ResearchEvent):
        received_all.append(evt)

    bus.subscribe(TargetDiscoveredEvent, on_target)
    bus.subscribe(EndpointDiscoveredEvent, on_endpoint)
    bus.subscribe_topic("*", on_any)

    # Publish events
    t_evt = TargetDiscoveredEvent(target="https://target.corp", port=443, service="https")
    e_evt = EndpointDiscoveredEvent(url="https://target.corp/api/v1/auth", method="POST")

    await bus.publish(t_evt)
    await bus.publish(e_evt)

    assert len(received_targets) == 1
    assert received_targets[0].target == "https://target.corp"
    assert len(received_endpoints) == 1
    assert received_endpoints[0].url == "https://target.corp/api/v1/auth"
    assert len(received_all) == 2

    # Check history
    history = bus.get_history()
    assert len(history) == 2
    assert bus.get_history(TargetDiscoveredEvent)[0].target == "https://target.corp"


# =====================================================================
# 2. Specialist Agents & Budget Tests
# =====================================================================

@pytest.mark.asyncio
async def test_specialist_agent_lifecycle_and_budget():
    bus = ResearchEventBus()
    budget = SpecialistBudget(max_actions=5, timeout_seconds=10.0)

    class FastTestSpecialist(SpecialistAgent):
        async def _execute(self, context: dict, event_bus: ResearchEventBus):
            self.budget.record_action()
            await event_bus.publish(
                EndpointDiscoveredEvent(url="https://target.corp/login", method="GET")
            )

    agent = FastTestSpecialist(
        name="FastWeb",
        specialty="web",
        objective="Find login page",
        budget=budget,
    )

    assert agent.state == SpecialistState.IDLE
    await agent.run({}, bus)
    assert agent.state == SpecialistState.COMPLETED
    assert agent.budget.actions_used == 1

    # Test budget limit enforcement
    small_budget = SpecialistBudget(max_actions=1)

    class OverBudgetSpecialist(SpecialistAgent):
        async def _execute(self, context: dict, event_bus: ResearchEventBus):
            self.budget.record_action()
            self.budget.record_action()  # Exceeds max_actions=1

    greedy_agent = OverBudgetSpecialist(
        name="Greedy",
        specialty="fuzzing",
        objective="Run too many actions",
        budget=small_budget,
    )

    await greedy_agent.run({}, bus)
    assert greedy_agent.state == SpecialistState.FAILED


# =====================================================================
# 3. Parallel Multi-Agent Execution ("Sab Kaam At The Same Time")
# =====================================================================

@pytest.mark.asyncio
async def test_concurrent_specialist_execution():
    """
    Proves that multiple specialists run concurrently rather than sequentially.
    5 specialists sleeping for 0.1s in parallel must finish in << 0.5s.
    """
    bus = ResearchEventBus()
    orchestrator = AsyncResearchOrchestrator(event_bus=bus, max_concurrent_specialists=10)

    class TimedSpecialist(SpecialistAgent):
        def __init__(self, name: str, sleep_dur: float = 0.1):
            super().__init__(name=name, specialty="timed", objective="Run concurrent sleep")
            self.sleep_dur = sleep_dur

        async def _execute(self, context: dict, event_bus: ResearchEventBus):
            await asyncio.sleep(self.sleep_dur)
            self.budget.record_action()
            await event_bus.publish(
                AnomalyDetectedEvent(
                    anomaly_type="concurrent_discovery",
                    observation=f"{self.name} completed successfully",
                )
            )

    specialists = [TimedSpecialist(f"Worker-{i}", sleep_dur=0.1) for i in range(5)]

    start = asyncio.get_event_loop().time()
    result: ResearchResult = await orchestrator.run(initial_specialists=specialists, timeout_seconds=5.0)
    elapsed = asyncio.get_event_loop().time() - start

    assert result.success is True
    assert result.completed_specialists >= 5
    # If sequential, 5 * 0.1s would take > 0.5s. Concurrently, it takes ~0.15s
    assert elapsed < 0.45, f"Execution was sequential ({elapsed:.2f}s), expected parallel (< 0.45s)"

    # Verify findings are aggregated in the shared blackboard
    assert len(orchestrator.blackboard.anomalies) == 5


# =====================================================================
# 4. Dynamic Decomposition (Events Triggering New Specialists)
# =====================================================================

@pytest.mark.asyncio
async def test_dynamic_decomposition_reactive_spawning():
    """
    Tests dynamic decomposition:
    A NetworkSpecialist discovers port 8080 -> Triggers a WebSpecialist.
    The WebSpecialist discovers /api/v1/user -> Triggers an ApiSpecialist.
    """
    bus = ResearchEventBus()
    orchestrator = AsyncResearchOrchestrator(event_bus=bus, max_concurrent_specialists=10)

    # 1. Define Network Discovery Specialist
    class InitialReconSpecialist(SpecialistAgent):
        async def _execute(self, context: dict, event_bus: ResearchEventBus):
            self.budget.record_action()
            # Discover web port 8080
            await event_bus.publish(
                TargetDiscoveredEvent(
                    target="10.10.10.5",
                    port=8080,
                    service="http",
                    target_type="network_service",
                )
            )

    # 2. Rule: Discovering HTTP port -> Spawns WebSpecialist
    def spawn_web_on_http_port(event: TargetDiscoveredEvent) -> SpecialistAgent | None:
        if event.port in (80, 443, 8080) or event.service in ("http", "https"):
            target_url = f"http://{event.target}:{event.port}"
            return WebSpecialist(
                name=f"Web-{event.port}",
                target_url=target_url,
                objective=f"Analyze web application at {target_url}",
            )
        return None

    orchestrator.register_decomposition_rule(TargetDiscoveredEvent, spawn_web_on_http_port)

    # Run orchestrator starting ONLY with InitialReconSpecialist
    recon = InitialReconSpecialist(name="PortScanner", specialty="network", objective="Scan ports")
    result = await orchestrator.run(initial_specialists=[recon], timeout_seconds=5.0)

    assert result.success is True
    # Initial recon + dynamically spawned WebSpecialist both executed
    assert result.completed_specialists >= 2
    # Verify the target was recorded in the blackboard
    assert "10.10.10.5" in orchestrator.blackboard.targets
    # Verify endpoints discovered by the dynamically spawned WebSpecialist
    assert len(orchestrator.blackboard.endpoints) > 0


# =====================================================================
# 5. Falsification & Adversarial Self-Challenge
# =====================================================================

@pytest.mark.asyncio
async def test_falsification_specialist_challenges_hypothesis():
    """
    Verifies that a FalsificationSpecialist actively challenges hypotheses,
    disproving false ones and verifying true ones.
    """
    bus = ResearchEventBus()
    falsified_events = []
    verified_events = []

    bus.subscribe(HypothesisFalsifiedEvent, lambda e: falsified_events.append(e))
    bus.subscribe(VulnerabilityVerifiedEvent, lambda e: verified_events.append(e))

    # Test 1: Disproving a false hypothesis
    falsifier = FalsificationSpecialist(
        name="RedTeamCritic",
        target_hypothesis_id="hyp-fake-idor",
        falsification_plan={"should_falsify": True, "disproving_evidence": "Found rigid tenant isolation filter"},
    )

    await falsifier.run({"hypotheses": [{"id": "hyp-fake-idor", "statement": "User ID parameter allows cross-tenant IDOR"}]}, bus)
    assert len(falsified_events) == 1
    assert falsified_events[0].hypothesis_id == "hyp-fake-idor"

    # Test 2: Verifying a surviving hypothesis
    verifier = FalsificationSpecialist(
        name="TruthVerifier",
        target_hypothesis_id="hyp-real-sqli",
        falsification_plan={"should_falsify": False, "verification_details": "SQL error reproducibly triggered across multiple probes"},
    )

    await verifier.run({"hypotheses": [{"id": "hyp-real-sqli", "statement": "Unescaped search parameter allows SQL Injection"}]}, bus)
    assert len(verified_events) == 1
    assert verified_events[0].vulnerability_class == "SQL Injection"


# =====================================================================
# 6. Additional Orchestration & Resilience Tests
# =====================================================================

@pytest.mark.asyncio
async def test_event_bus_queue_and_wildcard_subscriptions():
    bus = ResearchEventBus()
    queue = bus.subscribe_queue("endpoint.*")

    await bus.publish(TargetDiscoveredEvent(target="host.corp"))
    await bus.publish(EndpointDiscoveredEvent(url="http://host.corp/login"))

    event = await queue.get()
    assert isinstance(event, EndpointDiscoveredEvent)
    assert event.url == "http://host.corp/login"
    assert queue.empty()


@pytest.mark.asyncio
async def test_specialist_budget_timeout_enforcement():
    bus = ResearchEventBus()
    budget = SpecialistBudget(timeout_seconds=0.04)

    class SlowSpecialist(SpecialistAgent):
        async def _execute(self, context: dict, event_bus: ResearchEventBus):
            self.budget.record_action()
            await asyncio.sleep(0.08)
            self.budget.check_limits()

    slow_agent = SlowSpecialist(name="SlowAgent", specialty="recon", budget=budget)
    await slow_agent.run({}, bus)
    assert slow_agent.state == SpecialistState.FAILED


@pytest.mark.asyncio
async def test_dynamic_decomposition_multi_level_chain():
    """
    Verifies full multi-stage reactive discovery:
      1. NetworkSpecialist finds port 8080
      2. Spawns WebSpecialist which discovers /api/v1/user
      3. Spawns ApiSpecialist and AuthSpecialist
      4. Spawns FalsificationSpecialist to challenge hypotheses
    """
    orchestrator = AsyncResearchOrchestrator(max_concurrent_specialists=10)
    initial_recon = NetworkSpecialist(
        name="MultiStageRecon",
        target="10.0.0.99",
    )

    result = await orchestrator.run(
        initial_specialists=[initial_recon],
        initial_context={"open_ports": [{"port": 8080, "service": "http"}]},
        timeout_seconds=5.0,
    )

    assert result.success is True
    assert result.completed_specialists >= 3
    executed = result.specialists_executed
    assert any("MultiStageRecon" in name for name in executed)
    assert any("WebSpecialist" in name for name in executed)
    assert any("ApiSpecialist" in name or "AuthSpecialist" in name for name in executed)


@pytest.mark.asyncio
async def test_orchestrator_cancellation_and_priority_queue():
    bus = ResearchEventBus()
    orchestrator = AsyncResearchOrchestrator(
        event_bus=bus,
        max_concurrent_specialists=1,
        decomposition_rules=[],
    )

    order: list[str] = []

    class PriorityAgent(SpecialistAgent):
        async def _execute(self, context: dict, event_bus: ResearchEventBus):
            order.append(self.name)
            await asyncio.sleep(0.03)

    low_agent = PriorityAgent(name="LowAgent", specialty="low", priority=20)
    high_agent = PriorityAgent(name="HighAgent", specialty="high", priority=1)

    orchestrator.schedule_specialist(low_agent)
    orchestrator.schedule_specialist(high_agent)

    result = await orchestrator.run(timeout_seconds=5.0)
    assert result.success is True
    # Priority 1 must execute before Priority 20
    assert order == ["HighAgent", "LowAgent"]

    # Test cancel_all
    long_agent = WebSpecialist(name="LongWeb")
    async def _cancel():
        await asyncio.sleep(0.02)
        orchestrator.cancel_all()

    asyncio.create_task(_cancel())
    cancel_result = await orchestrator.run(
        initial_specialists=[long_agent],
        initial_context={"delay": 2.0},
    )
    assert cancel_result.status == "cancelled"

