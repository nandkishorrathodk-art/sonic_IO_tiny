"""
Tests for Phase 6: Experiment Designer, Transparent Confidence Model, and WorldModel Stop Conditions.
"""

import pytest
from sonic.research.epistemic import (
    CompetingHypothesis,
    Unknown,
    EvidenceWeight,
    EvidenceSourceType,
    ConfidenceCalculator,
    Contradiction,
    ContradictionSeverity,
)
from sonic.research.experiment_designer import ExperimentDesigner
from sonic.research.world_model import (
    WorldModel,
    StopCondition,
    StopConditionEvaluator,
)


def test_experiment_designer_discriminating_test():
    ha = CompetingHypothesis(statement="JWT is vulnerable to alg=None", falsification_criteria="401 error")
    hb = CompetingHypothesis(statement="JWT is valid guest session", falsification_criteria="No admin rights")

    candidate, prediction = ExperimentDesigner.design_discriminating_experiment(
        hypothesis_a=ha,
        hypothesis_b=hb,
        target="api.target.com",
    )

    assert candidate.is_discriminating_test is True
    assert "discriminating" in candidate.name.lower()
    assert prediction.expected_outcomes is not None


def test_transparent_confidence_calculator():
    # Case 1: High quality evidence, independent support, no contradictions
    weights = [
        EvidenceWeight(source_type=EvidenceSourceType.TOOL_MEASUREMENT, reliability=1.0, directness=1.0),
        EvidenceWeight(source_type=EvidenceSourceType.INDEPENDENT_VERIFIER, reliability=0.9, directness=1.0),
    ]
    breakdown = ConfidenceCalculator.calculate(
        evidence_weights=weights,
        independent_confirmations_count=2,
        unresolved_contradictions_count=0,
        unresolved_unknowns_count=0,
        is_reproducible=True,
    )
    assert breakdown.composite_confidence >= 0.85
    assert breakdown.contradictions_penalty == 0.0

    # Case 2: High contradictions penalty
    breakdown_ctrd = ConfidenceCalculator.calculate(
        evidence_weights=weights,
        independent_confirmations_count=0,
        unresolved_contradictions_count=2,
        unresolved_unknowns_count=2,
        is_reproducible=False,
    )
    assert breakdown_ctrd.composite_confidence < 0.40
    assert breakdown_ctrd.contradictions_penalty > 0.0


def test_world_model_stop_conditions():
    # 1. Budget exhausted
    wm = WorldModel(
        goal="Audit target",
        target="target.com",
        tenant_id="tenant-1",
        engagement_id="eng-1",
    )
    eval_budget = StopConditionEvaluator.evaluate(
        world_model=wm,
        replan_count=5,
        max_replans=5,
        tasks_count=10,
        max_tasks=50,
    )
    assert eval_budget.should_stop is True
    assert eval_budget.condition == StopCondition.BUDGET_EXHAUSTED

    # 2. Human review required due to high confidence with active contradiction
    wm.hypotheses.append(CompetingHypothesis(statement="Severe Auth Bypass", confidence=0.8))
    wm.contradictions.append(Contradiction(statement_a="403", statement_b="200", severity=ContradictionSeverity.HIGH))

    eval_hr = StopConditionEvaluator.evaluate(
        world_model=wm,
        replan_count=1,
        max_replans=5,
        tasks_count=5,
        max_tasks=50,
    )
    assert eval_hr.should_stop is True
    assert eval_hr.condition == StopCondition.HUMAN_REVIEW_REQUIRED
