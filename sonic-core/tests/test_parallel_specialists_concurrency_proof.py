"""
SONIC-REDA — Parallel Specialists Concurrency Proof & Epistemic Verification
=============================================================================
Proves:
  1. True concurrent parallel execution of the 6+1 Specialists (parallelism_factor > 1.5)
  2. Exact timeline trace logging (task_id, specialist, start_time, end_time, duration)
  3. Contradictory observation detection, confidence evaluation, and FalsificationSpecialist scheduling
  4. Epistemic unknown formulation and Information Gain prioritization
  5. Workstation prompt routing to parallel swarm with live worklog prefixes and AttackGraph generation
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from sonic.api.routes.workstation import (
    _get_or_create_session,
    _is_research_prompt,
    _run_prompt_reasoning,
)
from sonic.research.event_bus import (
    EndpointDiscoveredEvent,
    HypothesisProposedEvent,
    ResearchEventBus,
    TargetDiscoveredEvent,
)
from sonic.research.orchestrator import (
    AsyncResearchOrchestrator,
    ConflictRecord,
    ObservationClaim,
    ResearchBlackboard,
    ResearchResult,
)
from sonic.research.specialist import (
    ApiSpecialist,
    AuthSpecialist,
    BusinessLogicSpecialist,
    CloudSpecialist,
    FalsificationSpecialist,
    NetworkSpecialist,
    SpecialistAgent,
    SpecialistBlockedError,
    SpecialistState,
    WebSpecialist,
)


# =====================================================================
# 1. Concurrency Proof (All 7 Specialists simultaneously)
# =====================================================================

@pytest.mark.asyncio
async def test_all_seven_specialists_concurrency_proof(capsys: pytest.CaptureFixture[str]):
    """
    Run all 7 specialists (6 domain + 1 falsification) simultaneously against mock services.
    Output exact timeline traces and assert parallelism_factor > 1.5.
    """
    bus = ResearchEventBus()
    blackboard = ResearchBlackboard()
    orchestrator = AsyncResearchOrchestrator(
        event_bus=bus,
        blackboard=blackboard,
        max_concurrent_specialists=10,
        decomposition_rules=[],
    )

    # 7 Parallel Specialists
    specialists = [
        NetworkSpecialist(name="NetworkSpecialist", target="mock.corp.internal", objective="Scan ports"),
        WebSpecialist(name="WebSpecialist", target_url="https://mock.corp.internal", objective="Crawl routes"),
        ApiSpecialist(name="ApiSpecialist", target_url="https://mock.corp.internal/api", objective="Inspect API"),
        AuthSpecialist(name="AuthSpecialist", target_url="https://mock.corp.internal/auth", objective="Test tokens"),
        BusinessLogicSpecialist(name="BusinessLogicSpecialist", target_url="https://mock.corp.internal", objective="Analyze logic"),
        CloudSpecialist(name="CloudSpecialist", target_host="mock.corp.internal", objective="Audit cloud"),
        FalsificationSpecialist(name="FalsificationSpecialist", objective="Adversarial challenge"),
    ]

    # Each specialist takes 0.15s to simulate non-blocking mock service network I/O
    task_delay = 0.15
    context = {
        "target": "mock.corp.internal",
        "target_url": "https://mock.corp.internal",
        "target_host": "mock.corp.internal",
        "delay": task_delay,
    }

    t0 = time.time()
    result: ResearchResult = await orchestrator.run(
        initial_specialists=specialists,
        initial_context=context,
        timeout_seconds=5.0,
    )
    wall_clock = time.time() - t0

    # 1. Output the exact timeline trace
    traces = result.timeline_traces
    print("\n" + "=" * 90)
    print("           6+1 PARALLEL SPECIALISTS TIMELINE TRACE & CONCURRENCY PROOF")
    print("=" * 90)
    print(f"{'TASK ID':<24} | {'SPECIALIST':<24} | {'START TIME':<12} | {'END TIME':<12} | {'DURATION'}")
    print("-" * 90)
    for t in traces:
        print(f"{t['task_id']:<24} | {t['specialist']:<24} | {t['start_time'] - t0:>10.4f}s | {t['end_time'] - t0:>10.4f}s | {t['duration']:>6.4f}s")
    print("-" * 90)
    print(f"Parallel Wall Clock Time : {result.parallel_wall_time:.4f} s (Actual: {wall_clock:.4f} s)")
    print(f"Sum of Individual Tasks  : {result.sum_of_task_times:.4f} s")
    print(f"Measured Parallelism     : {result.parallelism_factor:.2f} x")
    print("=" * 90)

    # 2. Verification of complete execution
    assert result.success is True
    assert result.completed_specialists >= 7
    assert all(s.name in result.specialists_executed for s in specialists)
    assert len(traces) >= 7

    # 3. Mathematical proof of concurrent overlap:
    # If executed sequentially: sum of times would be >= 7 * 0.15s = 1.05s, wall clock >= 1.05s
    # Concurrently: wall clock is ~0.15s - 0.25s, so parallelism factor is >= 4.0x
    assert result.sum_of_task_times >= 7 * (task_delay * 0.8), (
        f"Sum of task times ({result.sum_of_task_times:.4f}s) should be at least {7 * task_delay * 0.8:.4f}s"
    )
    assert result.parallel_wall_time < result.sum_of_task_times * 0.65, (
        f"Wall clock ({result.parallel_wall_time:.4f}s) must be significantly smaller than task sum ({result.sum_of_task_times:.4f}s)"
    )
    assert result.parallelism_factor > 1.5, (
        f"Parallelism factor {result.parallelism_factor} must exceed 1.5 for true concurrency"
    )

    # 4. Temporal overlap proof:
    # Verify that at least 5 pairs of tasks were running concurrently in the exact same time window
    overlapping_pairs = 0
    for i in range(len(traces)):
        for j in range(i + 1, len(traces)):
            t1 = traces[i]
            t2 = traces[j]
            if max(t1["start_time"], t2["start_time"]) < min(t1["end_time"], t2["end_time"]):
                overlapping_pairs += 1

    assert overlapping_pairs >= 10, f"Expected high concurrency overlap, got {overlapping_pairs} overlapping pairs"


# =====================================================================
# 2. Contradictory Observations & Falsification Scheduling
# =====================================================================

@pytest.mark.asyncio
async def test_blackboard_contradictory_observations_falsification_scheduling():
    """
    Test that when specialist A asserts state X and specialist B asserts not-X:
      - Blackboard detects contradiction
      - Evaluates confidence and timestamps
      - Automatically schedules FalsificationSpecialist to resolve the conflict
    """
    bus = ResearchEventBus()
    blackboard = ResearchBlackboard()
    orchestrator = AsyncResearchOrchestrator(event_bus=bus, blackboard=blackboard)

    # Specialist A asserts endpoint requires authentication (confidence=0.6)
    conflict_1 = await blackboard.assert_observation(
        entity="https://app.corp/v1/user:auth_required",
        state=True,
        confidence=0.60,
        source="WebSpecialist",
        orchestrator=orchestrator,
    )
    assert conflict_1 is None  # First claim has no contradiction

    # Specialist B asserts endpoint does NOT require authentication (confidence=0.85)
    conflict_2 = await blackboard.assert_observation(
        entity="https://app.corp/v1/user:auth_required",
        state=False,
        confidence=0.85,
        source="ApiSpecialist",
        orchestrator=orchestrator,
    )

    assert conflict_2 is not None
    assert isinstance(conflict_2, ConflictRecord)
    assert conflict_2.status == "falsification_scheduled"
    assert conflict_2.claim_a.source == "WebSpecialist"
    assert conflict_2.claim_a.state is True
    assert conflict_2.claim_b.source == "ApiSpecialist"
    assert conflict_2.claim_b.state is False

    # Check confidence & timestamp evaluation
    evaluation = conflict_2.evaluation
    assert evaluation["confidence_a"] == 0.60
    assert evaluation["confidence_b"] == 0.85
    assert evaluation["confidence_delta"] == 0.25
    assert evaluation["higher_confidence_source"] == "ApiSpecialist"
    assert evaluation["more_recent_source"] == "ApiSpecialist"
    assert "FalsificationSpecialist scheduled" in evaluation["recommendation"]

    # Check FalsificationSpecialist was scheduled into the orchestrator priority queue
    assert not orchestrator._priority_queue.empty()
    prio, seq, scheduled_agent, ctx = orchestrator._priority_queue.get_nowait()
    assert isinstance(scheduled_agent, FalsificationSpecialist)
    assert prio == 1  # Scheduled with highest priority
    assert scheduled_agent.name == conflict_2.falsifier_agent_name

    # Check resolving the conflict
    resolved = blackboard.resolve_conflict(
        conflict_id=conflict_2.conflict_id,
        winning_claim_or_source="ApiSpecialist",
        resolution_notes="Direct unauthenticated request returned 200 OK with sensitive PII",
    )
    assert resolved is True
    assert conflict_2.status == "resolved"
    assert conflict_2.winning_claim is not None
    assert conflict_2.winning_claim.source == "ApiSpecialist"
    assert len(blackboard.get_unresolved_conflicts()) == 0


# =====================================================================
# 3. Epistemic Inquiry: Unknowns & Information Gain Prioritization
# =====================================================================

@pytest.mark.asyncio
async def test_central_research_loop_unknowns_and_information_gain():
    """
    Test orchestrator formulation:
      - 'What is still unknown?'
      - 'What hypotheses are unresolved?'
      - Prioritization by Information Gain
    """
    bus = ResearchEventBus()
    blackboard = ResearchBlackboard()
    orchestrator = AsyncResearchOrchestrator(event_bus=bus, blackboard=blackboard)

    # Seed discoveries into blackboard
    await bus.publish(TargetDiscoveredEvent(target="api.target.com", port=443, service="https"))
    await bus.publish(EndpointDiscoveredEvent(url="https://api.target.com/v1/orders", method="POST", params=["id", "price"], auth_required=None))
    await bus.publish(TargetDiscoveredEvent(target="target-backups.s3.amazonaws.com", target_type="cloud_resource"))

    # Seed hypotheses
    await bus.publish(HypothesisProposedEvent(
        source="ApiSpecialist",
        hypothesis_id="hypo-idor-01",
        statement="Endpoint /v1/orders allows IDOR price tampering",
        vulnerability_class="idor",
        confidence=0.50,  # Max uncertainty -> highest entropy
    ))
    await bus.publish(HypothesisProposedEvent(
        source="WebSpecialist",
        hypothesis_id="hypo-xss-02",
        statement="Search parameter reflected in comment",
        vulnerability_class="xss",
        confidence=0.90,  # Lower uncertainty
    ))

    # 1. Formulate unknowns
    unknowns = orchestrator.formulate_unknowns()
    assert len(unknowns) >= 2
    questions = [u.question for u in unknowns]
    assert any("authentication" in q.lower() for q in questions)
    assert any("cloud" in q.lower() or "s3" in q.lower() for q in questions)

    # 2. Formulate unresolved hypotheses
    unresolved = orchestrator.get_unresolved_hypotheses()
    assert len(unresolved) == 2
    ids = [h.hypothesis_id for h in unresolved]
    assert "hypo-idor-01" in ids
    assert "hypo-xss-02" in ids

    # 3. Prioritize by Information Gain
    agenda = orchestrator.prioritize_by_information_gain()
    assert len(agenda) >= 3

    # The hypothesis with confidence=0.50 should have higher information gain than confidence=0.90
    idor_entry = next(item for item in agenda if item.get("id") == "hypo-idor-01")
    xss_entry = next(item for item in agenda if item.get("id") == "hypo-xss-02")
    assert idor_entry["information_gain"] > xss_entry["information_gain"]

    # Verify agenda is strictly sorted descending by information_gain
    gains = [item["information_gain"] for item in agenda]
    assert gains == sorted(gains, reverse=True)


# =====================================================================
# 4. Workstation Swarm Wiring & Worklog Live Streaming
# =====================================================================

@pytest.mark.asyncio
async def test_workstation_prompt_triggers_parallel_swarm_and_records_metrics():
    """
    Test that workstation route prompt handling:
      - Detects research/security prompt keywords
      - Bypasses sequential ComputerUseAgent
      - Runs 6+1 Specialists concurrently
      - Streams live worklog entries with required specialist prefixes
      - Populates AttackGraph in state["graph"]
      - Concurrently records parallel_wall_time, sum_of_task_times, parallelism_factor
    """
    tenant_id = "tenant-pentest-team"
    session_id = f"test-swarm-{int(time.time())}"
    state = _get_or_create_session(tenant_id, session_id)

    # Verify prompt keyword detection
    assert _is_research_prompt("Please scan ports on 192.168.1.100") is True
    assert _is_research_prompt("Perform security audit and pentest on https://target.local") is True
    assert _is_research_prompt("Check vulnerability and recon API") is True
    assert _is_research_prompt("git commit changes") is False

    # Execute _run_prompt_reasoning with research prompt
    prompt = "Scan ports and test vulnerability on https://api.production.local"
    await _run_prompt_reasoning(tenant_id, session_id, prompt)

    # 1. Verify required worklog streaming prefixes exist
    worklog_texts = [f"{w.get('title', '')} {w.get('content', '')}" for w in state.get("worklog", [])]
    full_worklog = " ".join(worklog_texts)

    assert "[NetworkSpecialist] Scanning ports..." in full_worklog
    assert "[WebSpecialist] Crawling endpoints..." in full_worklog
    assert "[ApiSpecialist] Analyzing parameters..." in full_worklog
    assert "[AuthSpecialist] Inspecting tokens..." in full_worklog
    assert "[FalsificationSpecialist] Testing hypothesis..." in full_worklog

    # 2. Verify AttackGraph nodes and edges in state["graph"]
    graph_state = state.get("graph")
    assert graph_state is not None
    assert "nodes" in graph_state
    assert "edges" in graph_state
    assert len(graph_state["nodes"]) > 0
    assert "mermaid" in graph_state

    # 3. Verify concurrency execution metrics
    assert "parallel_wall_time" in state
    assert "sum_of_task_times" in state
    assert "parallelism_factor" in state
    assert state["parallel_wall_time"] > 0
    assert state["sum_of_task_times"] > 0
    assert state["parallelism_factor"] > 1.5, (
        f"Expected parallelism_factor > 1.5 in state, got {state['parallelism_factor']}"
    )

    # Verify metrics object in state
    assert "metrics" in state
    assert state["metrics"]["completed_specialists"] >= 7
    assert state["metrics"]["parallelism_factor"] == state["parallelism_factor"]


# =====================================================================
# 5. Parallel Swarm Failure Isolation & State Resumption Proof
# =====================================================================

@pytest.mark.asyncio
async def test_parallel_swarm_failure_isolation_and_resumption():
    """
    Section 8-11: In a 7-specialist swarm where one worker fails with PROVIDER_FAILURE:
      1. Failed specialist transitions to BLOCKED, recorded on blackboard.
      2. The remaining 6 specialists execute concurrently without interruption.
      3. True parallelism holds (parallelism_factor > 1.5).
      4. Central brain resumes the failed specialist upon environment restoration.
      5. Resumed specialist succeeds and all findings/graph state are preserved and augmented.
    """
    bus = ResearchEventBus()
    blackboard = ResearchBlackboard()
    orchestrator = AsyncResearchOrchestrator(
        event_bus=bus,
        blackboard=blackboard,
        max_concurrent_specialists=10,
        decomposition_rules=[],
    )

    provider_online = False

    async def flaky_network_scan(agent: SpecialistAgent, ctx: dict[str, Any], eb: ResearchEventBus):
        nonlocal provider_online
        if not provider_online:
            await asyncio.sleep(0.02)
            raise SpecialistBlockedError(
                "Sandbox provider unreachable: docker daemon reset (exit 125)",
                reason="PROVIDER_FAILURE",
                diagnostic="Substrate container exit 125",
            )
        await asyncio.sleep(0.10)
        await eb.publish(TargetDiscoveredEvent(source=agent.name, target="mock.corp.internal", port=443, service="https"))
        return {"ports": [443]}

    task_delay = 0.15
    network_spec = NetworkSpecialist(
        name="NetworkSpecialist",
        target="mock.corp.internal",
        investigation_fn=flaky_network_scan,
    )
    specialists = [
        network_spec,
        WebSpecialist(name="WebSpecialist", target_url="https://mock.corp.internal"),
        ApiSpecialist(name="ApiSpecialist", target_url="https://mock.corp.internal/api"),
        AuthSpecialist(name="AuthSpecialist", target_url="https://mock.corp.internal/auth"),
        BusinessLogicSpecialist(name="BusinessLogicSpecialist", target_url="https://mock.corp.internal"),
        CloudSpecialist(name="CloudSpecialist", target_host="mock.corp.internal"),
        FalsificationSpecialist(name="FalsificationSpecialist"),
    ]

    context = {
        "target": "mock.corp.internal",
        "target_url": "https://mock.corp.internal",
        "target_host": "mock.corp.internal",
        "delay": task_delay,
    }

    result_p1: ResearchResult = await orchestrator.run(
        initial_specialists=specialists,
        initial_context=context,
        timeout_seconds=5.0,
    )

    # 1. Failure isolation verification
    assert network_spec.state == SpecialistState.BLOCKED
    assert "NetworkSpecialist" in result_p1.specialists_blocked
    assert "NetworkSpecialist" not in result_p1.specialists_succeeded

    # 2. Remaining 6 specialists continued and succeeded
    remaining_names = [
        "WebSpecialist",
        "ApiSpecialist",
        "AuthSpecialist",
        "BusinessLogicSpecialist",
        "CloudSpecialist",
        "FalsificationSpecialist",
    ]
    for s_name in remaining_names:
        assert s_name in result_p1.specialists_succeeded
        agent = orchestrator._all_specialists[s_name]
        assert agent.state == SpecialistState.COMPLETED

    assert result_p1.completed_specialists >= 6
    assert result_p1.total_specialists >= 7

    # 3. Concurrency holds across active workers
    assert result_p1.parallelism_factor > 1.5, (
        f"Expected parallelism_factor > 1.5 with 6 concurrent workers, got {result_p1.parallelism_factor}"
    )

    # 4. Blackboard diagnostics
    assert "NetworkSpecialist" in blackboard.failed_workers
    diag = blackboard.diagnose_failure("NetworkSpecialist")
    assert diag is not None
    assert diag["reason"] == "PROVIDER_FAILURE"
    assert diag["substrate_issue"] == "provider_failure"
    assert "exit 125" in str(diag["diagnostic"])

    # 5. Environment restored: resume NetworkSpecialist
    provider_online = True
    resumed = orchestrator.resume_specialist("NetworkSpecialist", context={"restored": True, "delay": 0.05})
    assert resumed.state == SpecialistState.IDLE
    assert "NetworkSpecialist" not in blackboard.failed_workers

    result_p2: ResearchResult = await orchestrator.run(timeout_seconds=5.0)
    assert resumed.state == SpecialistState.COMPLETED
    assert "NetworkSpecialist" in result_p2.specialists_succeeded
    assert "NetworkSpecialist" not in result_p2.specialists_failed
    assert "NetworkSpecialist" not in result_p2.specialists_blocked
    assert any(t.port == 443 for t in blackboard.targets.values())

