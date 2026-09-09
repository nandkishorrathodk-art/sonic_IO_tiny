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
    ResearchBlackboard,
    ResearchResult,
)
from sonic.research.specialist import (
    ApiSpecialist,
    AuthSpecialist,
    FalsificationSpecialist,
    NetworkSpecialist,
    SpecialistAgent,
    SpecialistBlockedError,
    SpecialistBudget,
    SpecialistState,
    SpecialistTimeoutError,
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
    # Caller-supplied recon: a discovered login endpoint — WebSpecialist points
    # at it, never invents one out of thin air.
    result = await orchestrator.run(
        initial_specialists=[recon],
        initial_context={
            "endpoints": [{"url": "http://10.10.10.5:8080/login", "method": "GET"}],
        },
        timeout_seconds=5.0,
    )

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

    # Caller-supplied recon: a discovered /api/v1/user endpoint (no invented
    # routes) — WebSpecialist re-publishes it, which then spawns Api+Auth.

    result = await orchestrator.run(
        initial_specialists=[initial_recon],
        initial_context={
            "open_ports": [{"port": 8080, "service": "http"}],
            "endpoints": [{"url": "http://10.0.0.99:8080/api/v1/user", "method": "GET", "auth_required": True}],
        },
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


# =====================================================================
# 7. Worker Failure Isolation, Diagnosis & Resumption (Sections 8, 9, 10, 11)
# =====================================================================

@pytest.mark.asyncio
async def test_worker_failure_isolation_in_parallelism():
    """
    Section 8: When multiple specialists are running in parallel:
    If Specialist A (NetworkSpecialist) fails/gets BLOCKED due to PROVIDER_FAILURE:
      - Specialist A transitions to SpecialistState.BLOCKED
      - Diagnostic details and failure are recorded on ResearchBlackboard
      - CRITICAL: Specialists B (WebSpecialist), C (ApiSpecialist), D (FalsificationSpecialist)
        MUST CONTINUE running independently without interruption!
    """
    bus = ResearchEventBus()
    blackboard = ResearchBlackboard()
    orchestrator = AsyncResearchOrchestrator(
        event_bus=bus,
        blackboard=blackboard,
        max_concurrent_specialists=10,
        decomposition_rules=[],
    )

    # Specialist A: Fails immediately with PROVIDER_FAILURE (exit 125 / sandbox dropped)
    async def failing_network(agent: SpecialistAgent, ctx: dict, eb: ResearchEventBus):
        await asyncio.sleep(0.02)
        raise SpecialistBlockedError(
            "Docker daemon unreachable: container terminated unexpectedly",
            reason="PROVIDER_FAILURE",
            diagnostic="Container runtime exit 125: dockerd connection reset",
        )

    network_spec = NetworkSpecialist(
        name="NetworkSpecialist",
        target="10.0.0.1",
        investigation_fn=failing_network,
    )

    # Specialist B: WebSpecialist runs concurrently and succeeds after 0.08s
    web_spec = WebSpecialist(name="WebSpecialist", target_url="http://10.0.0.1")

    # Specialist C: ApiSpecialist runs concurrently and succeeds after 0.08s
    api_spec = ApiSpecialist(name="ApiSpecialist", target_url="http://10.0.0.1/api")

    # Specialist D: FalsificationSpecialist runs concurrently and succeeds
    falsifier = FalsificationSpecialist(name="FalsificationSpecialist")

    specialists = [network_spec, web_spec, api_spec, falsifier]
    context = {"delay": 0.08, "target": "10.0.0.1"}

    result: ResearchResult = await orchestrator.run(
        initial_specialists=specialists,
        initial_context=context,
        timeout_seconds=5.0,
    )

    # 1. Specialist A is BLOCKED
    assert network_spec.state == SpecialistState.BLOCKED
    assert "NetworkSpecialist" in result.specialists_blocked
    assert "NetworkSpecialist" not in result.specialists_succeeded

    # 2. Specialists B, C, D continued without interruption and SUCCEEDED
    assert web_spec.state == SpecialistState.COMPLETED
    assert api_spec.state == SpecialistState.COMPLETED
    assert falsifier.state == SpecialistState.COMPLETED

    assert "WebSpecialist" in result.specialists_succeeded
    assert "ApiSpecialist" in result.specialists_succeeded
    assert "FalsificationSpecialist" in result.specialists_succeeded
    assert result.completed_specialists >= 3
    assert result.total_specialists >= 4
    assert result.status == "completed"

    # 3. Blackboard state verification
    assert "NetworkSpecialist" in blackboard.failed_workers
    assert "WebSpecialist" not in blackboard.failed_workers
    assert "ApiSpecialist" not in blackboard.failed_workers
    assert len(blackboard.active_workers) == 0

    # 4. Diagnostic details on blackboard
    assert "NetworkSpecialist" in blackboard.worker_failures
    failures = blackboard.worker_failures["NetworkSpecialist"]
    assert len(failures) >= 1
    f_diag = failures[-1]
    assert f_diag["reason"] == "PROVIDER_FAILURE"
    assert f_diag["substrate_issue"] == "provider_failure"
    assert "Docker daemon unreachable" in f_diag["error"]
    assert "exit 125" in str(f_diag["diagnostic"])


@pytest.mark.asyncio
async def test_worker_timeout_failure_isolation():
    """
    Section 8: Specialist A times out (TIMEOUT), but Specialist B continues running.
    """
    bus = ResearchEventBus()
    blackboard = ResearchBlackboard()
    orchestrator = AsyncResearchOrchestrator(
        event_bus=bus,
        blackboard=blackboard,
        max_concurrent_specialists=5,
        decomposition_rules=[],
    )

    async def timing_out_worker(agent: SpecialistAgent, ctx: dict, eb: ResearchEventBus):
        await asyncio.sleep(0.02)
        raise SpecialistTimeoutError(
            "Service probe timed out after 30s deadline",
            reason="TIMEOUT",
            diagnostic="Probe deadline exceeded against 192.168.1.50:80",
        )

    timed_spec = NetworkSpecialist(
        name="TimedNetwork",
        target="192.168.1.50",
        investigation_fn=timing_out_worker,
    )
    web_spec = WebSpecialist(name="NormalWeb", target_url="http://192.168.1.50")

    result = await orchestrator.run(
        initial_specialists=[timed_spec, web_spec],
        initial_context={"delay": 0.05},
        timeout_seconds=5.0,
    )

    assert timed_spec.state in (SpecialistState.FAILED, SpecialistState.BLOCKED)
    assert web_spec.state == SpecialistState.COMPLETED
    assert "TimedNetwork" in blackboard.failed_workers
    assert "NormalWeb" not in blackboard.failed_workers
    assert "TimedNetwork" in blackboard.worker_failures
    f_entry = blackboard.worker_failures["TimedNetwork"][-1]
    assert f_entry["reason"] == "TIMEOUT"
    assert f_entry["substrate_issue"] == "timeout"


@pytest.mark.asyncio
async def test_central_brain_failure_diagnosis_on_blackboard():
    """
    Section 9: Central brain inspects ResearchBlackboard and recognizes:
      - active_workers, failed_workers, worker_failures
      - Which specialist failed
      - Why it failed (reason)
      - What substrate or tool issue occurred (substrate_issue, tool_issue)
      - FalsificationSpecialist operates normally
    """
    bus = ResearchEventBus()
    blackboard = ResearchBlackboard()
    orchestrator = AsyncResearchOrchestrator(
        event_bus=bus,
        blackboard=blackboard,
        max_concurrent_specialists=10,
        decomposition_rules=[],
    )

    # 1. Simulate failure of NetworkSpecialist with exit 126 / permission denied
    async def permission_fail(agent: SpecialistAgent, ctx: dict, eb: ResearchEventBus):
        raise SpecialistBlockedError(
            "bash: ./nmap: Permission denied (exit 126)",
            reason="BLOCKED",
            diagnostic="Substrate security policy blocked execution",
        )

    net_spec = NetworkSpecialist(name="NetPermFail", investigation_fn=permission_fail)
    auth_spec = AuthSpecialist(name="AuthWorking", target_url="http://target/auth")
    falsifier = FalsificationSpecialist(name="TruthChecker")

    await orchestrator.run(
        initial_specialists=[net_spec, auth_spec, falsifier],
        initial_context={
            "delay": 0.04,
            # AuthSpecialist only reports a verified vuln when the caller supplies
            # REAL reproduction evidence — never a fabricated alg=none finding.


            "verification_evidence": "Reproduced: unsigned JWT with alg=none returned 200 OK on sandboxed probe",
        },
        timeout_seconds=5.0,
    )

    # 2. Central brain queries the blackboard
    failed = blackboard.get_failed_workers()
    assert "NetPermFail" in failed
    assert "AuthWorking" not in failed
    assert "TruthChecker" not in failed

    diag = blackboard.diagnose_failure("NetPermFail")
    assert diag is not None
    assert diag["worker"] == "NetPermFail"
    assert diag["state"] == "blocked"
    assert diag["reason"] in ("BLOCKED", "PROVIDER_FAILURE")
    assert diag["substrate_issue"] == "permission_denied"
    assert "Permission denied" in diag["error"]
    assert diag["can_resume"] is True

    # 3. Snapshot includes worker tracking
    snap = blackboard.snapshot()
    assert "active_workers" in snap
    assert "failed_workers" in snap
    assert "worker_failures" in snap
    assert "NetPermFail" in snap["failed_workers"]
    assert "NetPermFail" in snap["worker_failures"]

    # 4. FalsificationSpecialist continued and verified findings
    assert falsifier.state == SpecialistState.COMPLETED
    assert len(blackboard.verified_vulnerabilities) > 0


@pytest.mark.asyncio
async def test_state_resumption_preserving_findings_and_attack_graph():
    """
    Section 10 & 11: State Resumption:
    When a failed/blocked specialist's environment is restored or recovered:
    orchestrator.resume_specialist(specialist_name, ...) can restart or resume
    that specialist using the preserved research state on the blackboard without
    losing any previous findings, attack graph nodes, or active tasks.
    """
    from sonic.research.attack_graph import AttackGraph, AttackNodeType

    bus = ResearchEventBus()
    blackboard = ResearchBlackboard()
    attack_graph = AttackGraph()
    blackboard.attach_attack_graph(attack_graph)

    # Seed attack graph node and blackboard endpoint from previous research
    attack_graph.add_node("target-web", "Target Web (:80)", AttackNodeType.ENTRY_POINT)
    await bus.publish(TargetDiscoveredEvent(target="10.10.10.1", port=80, service="http"))
    await bus.publish(EndpointDiscoveredEvent(url="http://10.10.10.1/api/v1", method="GET"))
    await blackboard.record_event(TargetDiscoveredEvent(target="10.10.10.1", port=80, service="http"))
    await blackboard.record_event(EndpointDiscoveredEvent(url="http://10.10.10.1/api/v1", method="GET"))

    orchestrator = AsyncResearchOrchestrator(
        event_bus=bus,
        blackboard=blackboard,
        max_concurrent_specialists=5,
        decomposition_rules=[],
    )

    # Phase 1: NetworkSpecialist fails due to temporary PROVIDER_FAILURE
    provider_online = False

    async def flaky_recon(agent: SpecialistAgent, ctx: dict, eb: ResearchEventBus):
        nonlocal provider_online
        if not provider_online:
            raise SpecialistBlockedError(
                "Substrate connection refused: sandbox agent down",
                reason="PROVIDER_FAILURE",
            )
        # Once restored: discover port 8080 and publish
        await eb.publish(
            TargetDiscoveredEvent(
                source=agent.name,
                target="10.10.10.1",
                port=8080,
                service="http-alt",
            )
        )
        return {"ports_found": [8080]}

    recon_spec = NetworkSpecialist(
        name="FlakyRecon",
        target="10.10.10.1",
        investigation_fn=flaky_recon,
    )

    result_p1 = await orchestrator.run(initial_specialists=[recon_spec], timeout_seconds=5.0)
    assert recon_spec.state == SpecialistState.BLOCKED
    assert "FlakyRecon" in blackboard.failed_workers
    assert "FlakyRecon" in result_p1.specialists_blocked

    # Verify previous findings on blackboard and attack graph were preserved
    assert len(blackboard.endpoints) >= 1
    assert len(attack_graph.nodes) == 1
    assert "target-web" in attack_graph.nodes

    # Phase 2: Environment restored. Central brain resumes the specialist!
    provider_online = True

    # Test both sync return and state reset
    resumed = orchestrator.resume_specialist("FlakyRecon", context={"environment": "restored"})
    assert resumed.name == "FlakyRecon"
    assert resumed.state == SpecialistState.IDLE
    assert "FlakyRecon" not in blackboard.failed_workers
    # Failure history is still preserved for auditing
    assert "FlakyRecon" in blackboard.worker_failures

    # Run orchestrator to execute the resumed specialist
    result_p2 = await orchestrator.run(timeout_seconds=5.0)
    assert resumed.state == SpecialistState.COMPLETED
    assert "FlakyRecon" in result_p2.specialists_succeeded
    assert "FlakyRecon" not in result_p2.specialists_failed
    assert "FlakyRecon" not in result_p2.specialists_blocked

    # Verify all previous findings and attack graph nodes were preserved AND augmented
    assert len(blackboard.endpoints) >= 1
    assert any(t.port == 8080 for t in blackboard.targets.values())
    assert "target-web" in attack_graph.nodes


