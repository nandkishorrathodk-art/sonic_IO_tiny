"""
Tests for Phase 6: Unknown-First Reasoning, Competing Hypotheses, and Adversarial Challenges.
"""

from sonic.agents.cognitive_state import (
    Attempt,
    CognitiveHypothesis,
    CognitiveState,
    EngagementBudget,
    HypothesisLifecycle,
)
from sonic.agents.cognitive_state import (
    Unknown as CogUnknown,
)
from sonic.research.epistemic import (
    CompetingHypothesis,
    Unknown,
    UnknownStatus,
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


# =====================================================================
# Round 7 — Epistemic awareness + falsification mindset wiring
# =====================================================================
# CognitiveState (cognitive_state.py) uses its OWN Unknown/CognitiveHypothesis
# models (not the research/epistemic ones), so we exercise the controller-side
# ranking + leading-hypothesis selection here, plus the falsification mindset
# that auto-targets the leading hypothesis for active disproof.


def _state():
    s = CognitiveState(
        goal="assess target auth",
        target="target.com",
        engagement_id="eng-1",
        tenant_id="t-1",
        budget=EngagementBudget(),
    )
    return s


class TestEpistemicAwareness:
    """'Mujhe kya nahi pata' made explicit and actionable: rank unresolved
    unknowns so the highest-information gap drives the next action."""

    def test_top_epistemic_gap_ranks_by_importance(self):
        s = _state()
        s.add_unknown(CogUnknown(question="low value?", estimated_importance=0.1))
        s.add_unknown(CogUnknown(question="high value?", estimated_importance=0.9))
        s.add_unknown(CogUnknown(question="mid value?", estimated_importance=0.5))
        gaps = s.get_top_epistemic_gap()
        assert [g.question for g in gaps] == ["high value?", "mid value?", "low value?"]

    def test_top_epistemic_gap_excludes_dead_ends(self):
        """An unknown whose every possible_action already failed is a dead-end
        — the agent must NOT re-chase a question it cannot answer with the
        methods it has tried."""
        s = _state()
        u = CogUnknown(
            question="does X leak?", estimated_importance=0.95,
            possible_actions=["probe_x", "brute_x"],
        )
        s.add_unknown(u)
        # Both candidate methods have already failed.
        for method in ("probe_x", "brute_x"):
            s.record_attempt(Attempt(method=method, success=False, failure_reason="blocked"))
        gaps = s.get_top_epistemic_gap()
        assert all(g.question != "does X leak?" for g in gaps), "dead-end unknown must not be surfaced"

    def test_top_epistemic_gap_keeps_partially_live_unknown(self):
        """If at least one candidate action is still live, the unknown stays
        ranked (the agent can still make progress on it)."""
        s = _state()
        u = CogUnknown(
            question="does Y leak?", estimated_importance=0.8,
            possible_actions=["probe_y", "fuzz_y"],
        )
        s.add_unknown(u)
        s.record_attempt(Attempt(method="probe_y", success=False, failure_reason="timeout"))
        # fuzz_y is still live.
        gaps = s.get_top_epistemic_gap()
        assert any(g.question == "does Y leak?" for g in gaps)

    def test_top_epistemic_gap_excludes_resolved(self):
        s = _state()
        s.add_unknown(CogUnknown(question="answered?", estimated_importance=0.9))
        s.unknowns[0].resolved = True
        assert s.get_top_epistemic_gap() == []

    def test_top_epistemic_gap_empty_when_no_unknowns(self):
        """Honesty: never invents an unknown; [] when there's genuinely nothing open."""
        assert _state().get_top_epistemic_gap() == []

    def test_top_k_limit(self):
        s = _state()
        for i in range(5):
            s.add_unknown(CogUnknown(question=f"q{i}?", estimated_importance=0.5))
        assert len(s.get_top_epistemic_gap(top_k=2)) == 2


class TestLeadingHypothesis:
    """The falsification mindset needs a concrete next target — the strongest
    active hypothesis to actively try to *disprove*."""

    def test_leading_hypothesis_picks_lowest_priority(self):
        """Priority 1 (critical) wins over priority 5 — the agent targets the
        most critical theory first."""
        s = _state()
        s.add_hypothesis(CognitiveHypothesis(title="low pri", description="d", priority=5))
        s.add_hypothesis(CognitiveHypothesis(title="crit pri", description="d", priority=1))
        lead = s.leading_hypothesis()
        assert lead is not None
        assert lead.priority == 1

    def test_leading_hypothesis_none_when_no_active(self):
        assert _state().leading_hypothesis() is None

    def test_leading_hypothesis_only_among_active(self):
        """A DISPROVED hypothesis is not a falsification target — it's already
        disproven."""
        s = _state()
        h = CognitiveHypothesis(title="dead", description="d", priority=1)
        h.lifecycle = HypothesisLifecycle.DISPROVED
        s.add_hypothesis(h)
        assert s.leading_hypothesis() is None


class TestFalsificationMindsetWiring:
    """AdversarialChallenger.challenge_leading_hypothesis auto-targets the
    leading hypothesis for active disproof — anti-confirmation-bias."""

    def test_challenge_leading_hypothesis_targets_strongest(self):
        s = _state()
        s.add_hypothesis(CognitiveHypothesis(
            title="auth bypass via alg=none", description="jwt tamper",
            priority=1, expected_observation="server rejects with 401",
        ))
        # a weaker competing theory that should NOT be picked
        s.add_hypothesis(CognitiveHypothesis(
            title="slow sql", description="timing", priority=5,
        ))
        result = AdversarialChallenger.challenge_leading_hypothesis(s, "target.com")
        assert result is not None
        candidate, prediction = result
        assert candidate.is_discriminating_test is True
        # The challenge must be aimed at the LEADING (critical) hypothesis.
        assert "auth bypass via alg=none" in candidate.description
        assert prediction.falsification_observation == "server rejects with 401"

    def test_challenge_leading_hypothesis_none_when_no_target(self):
        """No active hypothesis → None, not a fabricated challenge."""
        s = _state()
        assert AdversarialChallenger.challenge_leading_hypothesis(s, "target.com") is None

