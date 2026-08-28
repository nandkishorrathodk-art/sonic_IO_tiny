"""
Tests for Phase 6: Information Gain Scoring, Action Candidates, and ActionSelector.
"""

import pytest
from sonic.research.information_gain import (
    ActionCandidate,
    ActionSelector,
    DefaultInformationGainScorer,
)
from sonic.research.decision_trace import DecisionTrace


def test_action_candidate_scoring_and_ranking():
    scorer = DefaultInformationGainScorer()

    # Candidate 1: High info gain, low cost, low risk
    c1 = ActionCandidate(
        name="Dynamic: Test JWT Signature Bypass",
        description="Fuzz JWT with alg=None",
        agent_type="dynamic",
        expected_information_gain=0.9,
        expected_confidence_gain=0.5,
        estimated_cost=0.15,
        estimated_time_seconds=60,
        risk=0.05,
        is_discriminating_test=True,
    )

    # Candidate 2: Low info gain, high cost, high risk
    c2 = ActionCandidate(
        name="Mass Port Scan",
        description="Port scan /16 network",
        agent_type="recon",
        expected_information_gain=0.2,
        expected_confidence_gain=0.1,
        estimated_cost=0.8,
        estimated_time_seconds=300,
        risk=0.6,
        is_discriminating_test=False,
    )

    selector = ActionSelector(scorer=scorer)
    ranked = selector.rank_actions([c2, c1])

    # c1 must be ranked higher than c2
    assert len(ranked) == 2
    assert ranked[0].id == c1.id
    assert ranked[0].ranking_score > ranked[1].ranking_score


def test_action_selector_risk_filtering():
    selector = ActionSelector(max_acceptable_risk=0.5)

    dangerous_candidate = ActionCandidate(
        name="Destructive exploit payload",
        description="DROP DATABASE test",
        agent_type="dynamic",
        expected_information_gain=1.0,
        risk=0.95,  # Exceeds max_acceptable_risk
    )

    ranked = selector.rank_actions([dangerous_candidate])
    assert len(ranked) == 0


def test_decision_trace_recording():
    trace = DecisionTrace(
        engagement_id="eng-phase6",
        tenant_id="tenant-alpha",
        unknown_being_addressed="Is endpoint vulnerable to IDOR?",
        competing_hypotheses=["IDOR present", "Strict tenancy enforced"],
        candidate_actions=[{"name": "IDOR Probe A"}, {"name": "IDOR Probe B"}],
        selected_action="IDOR Probe A",
        selection_reason="Highest information gain",
        expected_information_gain=0.85,
        confidence_before=0.40,
    )
    assert trace.decision_id.startswith("dec-")

    trace.record_outcome(
        actual="HTTP 200 OK with cross-tenant data",
        prediction_error=0.0,
        conf_after=0.90,
        what_changed="Confirmed IDOR vulnerability",
    )
    assert trace.confidence_after == 0.90
    assert trace.prediction_error == 0.0
