"""
Tests for Cognitive State Machine (World Model & Epistemic Distinctions).
"""

import pytest
from sonic.agents.cognitive_state import (
    CognitiveState,
    EpistemicType,
    HypothesisLifecycle,
    Observation,
    Fact,
    Assumption,
    CognitiveHypothesis,
    Inference,
    Unknown,
    Attempt,
    EvidenceRef,
    Provenance,
    NextBestActionDecision,
    CandidateAction,
    EngagementBudget,
    CognitiveEventType,
)


def test_cognitive_state_creation_and_tenant():
    state = CognitiveState(
        engagement_id="eng-101",
        tenant_id="tenant-alpha",
        goal="Audit target.com",
    )
    assert state.engagement_id == "eng-101"
    assert state.tenant_id == "tenant-alpha"
    assert state.goal == "Audit target.com"
    assert len(state.event_log) == 0


def test_world_model_epistemic_distinctions():
    state = CognitiveState(engagement_id="eng-101", tenant_id="tenant-alpha")

    # 1. Observation (Raw data)
    obs = Observation(
        description="Endpoint /api/users returned HTTP 403",
        raw_data="HTTP/1.1 403 Forbidden",
        provenance=Provenance(source_agent="recon-1", tool="httpx"),
    )
    state.add_observation(obs, agent_id="recon-1")
    assert len(state.observations) == 1
    assert state.observations[0].epistemic_type == EpistemicType.OBSERVATION

    # 2. Inference (Derived conclusion - explicitly NOT a fact)
    inf = Inference(
        description="Authorization might be checked by middleware",
        reasoning="All /api/* routes returned 403 without token",
        derived_from=[obs.id],
    )
    state.add_inference(inf, agent_id="static-1")
    assert len(state.inferences) == 1
    assert state.inferences[0].epistemic_type == EpistemicType.INFERENCE

    # 3. Hypothesis (Testable theory)
    hyp = CognitiveHypothesis(
        title="Auth bypass via X-Original-URL header",
        description="Check if reverse proxy allows path override",
        vulnerability_class="Auth Bypass",
        expected_observation="HTTP 200 OK with user list",
    )
    state.add_hypothesis(hyp, agent_id="hypo-1")
    assert len(state.hypotheses) == 1
    assert state.hypotheses[0].lifecycle == HypothesisLifecycle.PROPOSED

    # 4. Unknown (First-class uncertainty)
    unk = Unknown(
        question="Does /api/v2 share the same auth gateway as /api/v1?",
        possible_actions=["fuzz headers", "compare response headers"],
        estimated_importance=0.8,
    )
    state.add_unknown(unk, agent_id="director")
    assert len(state.unknowns) == 1
    assert not state.unknowns[0].resolved

    # 5. Fact (Verified truth with evidence)
    fact = Fact(
        description="Target runs nginx 1.18 behind Cloudflare",
        evidence_ids=["ev-001"],
    )
    state.add_fact(fact, agent_id="recon-1")
    assert len(state.known_facts) == 1
    assert state.known_facts[0].epistemic_type == EpistemicType.FACT


def test_fact_correction_and_superseding():
    state = CognitiveState(engagement_id="eng-101", tenant_id="tenant-alpha")
    
    fact1 = Fact(description="Server banner indicates Apache 2.4")
    state.add_fact(fact1)

    fact2 = Fact(description="Server banner was spoofed; real server is Nginx 1.20")
    state.correct_fact(fact1.id, fact2, agent_id="verifier-1")

    assert len(state.known_facts) == 2
    assert state.known_facts[0].superseded_by == fact2.id
    active_facts = state.get_active_facts()
    assert len(active_facts) == 1
    assert active_facts[0].id == fact2.id


def test_assumption_invalidation():
    state = CognitiveState(engagement_id="eng-101", tenant_id="tenant-alpha")

    assump = Assumption(description="Port 8443 is an administrative console", rationale="Common admin port")
    state.add_assumption(assump)
    assert len(state.get_valid_assumptions()) == 1

    state.invalidate_assumption(assump.id, evidence_id="ev-8443-probe", agent_id="dynamic-1")
    assert len(state.get_valid_assumptions()) == 0
    assert not state.assumptions[0].is_valid
    assert state.assumptions[0].invalidated_by == "ev-8443-probe"


def test_inference_promotion_to_fact():
    state = CognitiveState(engagement_id="eng-101", tenant_id="tenant-alpha")
    
    inf = Inference(description="Target uses JWT authentication")
    state.add_inference(inf)

    fact = Fact(description="Confirmed JWT auth via Authorization Bearer token in response", evidence_ids=["ev-jwt"])
    state.promote_inference_to_fact(inf.id, fact, agent_id="verifier-1")

    assert state.inferences[0].promoted_to_fact == fact.id
    assert fact.derived_from == [inf.id]
    assert len(state.get_active_facts()) == 1


def test_unknown_resolution():
    state = CognitiveState(engagement_id="eng-101", tenant_id="tenant-alpha")
    
    unk = Unknown(question="Is debug mode active on /debug endpoint?")
    state.add_unknown(unk)
    assert len(state.get_unresolved_unknowns()) == 1

    state.resolve_unknown(unk.id, resolved_by="fact-debug-tested", resolution="Endpoint returns 404", agent_id="dynamic-1")
    assert len(state.get_unresolved_unknowns()) == 0
    assert state.unknowns[0].resolved
    assert state.unknowns[0].resolution == "Endpoint returns 404"


def test_append_only_event_audit_trail():
    state = CognitiveState(engagement_id="eng-101", tenant_id="tenant-alpha")
    
    state.add_fact(Fact(description="Domain is target.com"))
    state.add_hypothesis(CognitiveHypothesis(title="XSS on /search", description="Reflected parameter"))
    state.update_confidence(0.75, "Discovered multiple input surfaces")
    state.record_replan("new_attack_surface", "Adding tasks for newly found subdomains")

    assert len(state.event_log) == 4
    event_types = [e.event_type for e in state.event_log]
    assert event_types == [
        CognitiveEventType.FACT_CREATED,
        CognitiveEventType.HYPOTHESIS_CREATED,
        CognitiveEventType.CONFIDENCE_CHANGED,
        CognitiveEventType.REPLAN_OCCURRED,
    ]
    for event in state.event_log:
        assert event.tenant_id == "tenant-alpha"
        assert event.engagement_id == "eng-101"


def test_failed_and_successful_attempts():
    state = CognitiveState(engagement_id="eng-101", tenant_id="tenant-alpha")

    # Failed attempt
    fail_att = Attempt(
        method="SQLi on /search via payload ' OR 1=1--",
        success=False,
        failure_reason="WAF blocked with 406 Not Acceptable",
        lesson="WAF filters standard boolean SQLi keywords",
    )
    state.record_attempt(fail_att)

    # Successful attempt
    succ_att = Attempt(
        method="SSTI on /template with {{7*7}}",
        success=True,
        result_summary="Output evaluated to 49",
    )
    state.record_attempt(succ_att)

    assert len(state.failed_attempts) == 1
    assert len(state.successful_attempts) == 1
    assert "SQLi on /search via payload ' OR 1=1--" in state.get_failed_methods()


def test_next_best_action_decision():
    state = CognitiveState(engagement_id="eng-101", tenant_id="tenant-alpha")

    c1 = CandidateAction(
        action="Fuzz API parameters",
        expected_information_gain=0.9,
        cost=0.2,
        risk=0.1,
    )
    c2 = CandidateAction(
        action="Port scan entire /24 subnet",
        expected_information_gain=0.3,
        cost=0.8,
        risk=0.7,
    )

    decision = NextBestActionDecision(
        candidate_actions=[c1, c2],
        selected_action=c1,
        reason="Higher information gain and minimal risk",
        engagement_id="eng-101",
        tenant_id="tenant-alpha",
    )
    state.update_next_action(decision, agent_id="director")

    assert state.next_best_action == "Fuzz API parameters"
    assert state.last_decision.selected_action.action == "Fuzz API parameters"


def test_serialization_and_deserialization():
    state = CognitiveState(
        engagement_id="eng-101",
        tenant_id="tenant-alpha",
        goal="Find security vulnerabilities",
    )
    state.add_fact(Fact(description="Server is Ubuntu 22.04"))
    state.add_hypothesis(CognitiveHypothesis(title="Weak password policy", description="Check auth endpoint"))
    
    data = state.model_dump()
    reconstructed = CognitiveState(**data)

    assert reconstructed.engagement_id == "eng-101"
    assert reconstructed.tenant_id == "tenant-alpha"
    assert len(reconstructed.known_facts) == 1
    assert reconstructed.known_facts[0].description == "Server is Ubuntu 22.04"
    assert len(reconstructed.hypotheses) == 1
    assert len(reconstructed.event_log) == 2
