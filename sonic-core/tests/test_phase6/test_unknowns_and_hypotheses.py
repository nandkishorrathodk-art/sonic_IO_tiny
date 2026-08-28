"""
Tests for Phase 6: Unknown-First Reasoning, Competing Hypotheses, and Adversarial Challenges.
"""

import pytest
from sonic.research.epistemic import (
    Unknown,
    UnknownStatus,
    CompetingHypothesis,
    HypothesisStatus,
)
from sonic.research.experiment_designer import AdversarialChallenger


def test_unknown_creation_and_resolution():
    unk = Unknown(
        question="Does /api/v2/tokens enforce signature verification?",
        category="authorization",
        importance=0.9,
        possible_actions=["send alg=none token", "tamper payload without resign"],
    )
    assert unk.status == UnknownStatus.UNRESOLVED
    assert unk.importance == 0.9

    unk.resolve(
        resolution="Endpoint accepts unsigned tokens when alg=None",
        resolved_by="task-jwt-fuzz-01",
    )
    assert unk.status == UnknownStatus.RESOLVED
    assert unk.resolved_by == "task-jwt-fuzz-01"
    assert unk.resolved_at is not None


def test_competing_hypotheses_and_evidence_tracking():
    # Hypothesis A: Real Vulnerability
    h_a = CompetingHypothesis(
        statement="Endpoint /api/v2/tokens has authentication bypass via alg=None",
        vulnerability_class="Auth Bypass",
        confidence=0.5,
        falsification_criteria="Server rejects token with 401 Unauthorized",
    )

    # Hypothesis B: Intended Guest Mechanism (Non-vulnerable explanation)
    h_b = CompetingHypothesis(
        statement="Endpoint /api/v2/tokens is an intended public guest renewal service",
        vulnerability_class="Design Feature",
        confidence=0.5,
        falsification_criteria="Returned token has elevated admin claims",
    )

    # Add supporting and contradicting evidence
    h_a.add_support("ev-admin-token-returned")
    h_b.add_contradiction("ev-admin-token-returned")

    assert len(h_a.supporting_evidence) == 1
    assert len(h_b.contradicting_evidence) == 1


def test_adversarial_self_challenge_generation():
    h = CompetingHypothesis(
        statement="Server is vulnerable to blind SQL injection on /search?q=",
        vulnerability_class="SQLi",
        falsification_criteria="Sleep payload responds in normal baseline time (<200ms)",
    )

    candidate, prediction = AdversarialChallenger.generate_falsification_challenge(
        hypothesis=h,
        target="target.com",
    )

    assert candidate.agent_type == "verifier"
    assert candidate.is_discriminating_test is True
    assert "falsify" in candidate.description.lower()
    assert prediction.falsification_observation == h.falsification_criteria
