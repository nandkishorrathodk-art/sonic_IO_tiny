"""
Tests for Phase 1: Central Research Brain (Epistemic Inquiry & World Model)
===========================================================================
Verifies:
1. UnknownTracker priority queue and resolution mechanics.
2. Paired Hypothesis + Counter-Hypothesis generation and anti-confirmation bias balance.
3. FalsificationJudge requiring observable behavioral differences (no false-positive HTTP 200).
4. DecisionEngine dead-end detection and strategy pivot enforcement.
5. DynamicWorldModel state transition tracking across actors and resources.
"""

from __future__ import annotations

import pytest

from sonic.brain.decision import DecisionAction, DecisionEngine
from sonic.brain.experiment import Experiment, ExperimentDesigner, ExperimentResult
from sonic.brain.falsifier import EpistemicVerdict, FalsificationJudge
from sonic.brain.hypothesis import HypothesisEngine, HypothesisStatus
from sonic.brain.unknowns import UnknownDomain, UnknownTracker
from sonic.brain.world_model import DynamicWorldModel


@pytest.mark.no_live_infra
def test_unknown_tracker_prioritization_and_resolution():
    tracker = UnknownTracker()
    u1 = tracker.register_unknown("Is endpoint /admin public or authenticated?", domain=UnknownDomain.AUTHENTICATION, priority=2.0)
    u2 = tracker.register_unknown("Does /api/orders validate cross-tenant IDOR?", domain=UnknownDomain.PERMISSIONS, priority=4.5)

    top = tracker.get_top_priority_unknowns(limit=1)
    assert len(top) == 1
    assert top[0].unknown_id == u2.unknown_id

    resolved = tracker.resolve_unknown(u2.unknown_id, "Verified token signature check is enforced.")
    assert resolved is True
    assert len(tracker.get_unresolved()) == 1
    assert tracker.get_unresolved()[0].unknown_id == u1.unknown_id


@pytest.mark.no_live_infra
def test_hypothesis_engine_mandatory_counter_pair():
    engine = HypothesisEngine()
    h_primary, h_counter = engine.create_hypothesis_pair(
        statement="User-controlled ID parameter allows IDOR to view arbitrary order records",
        vulnerability_class="IDOR",
        target_asset="/api/orders/{id}",
        claim_type="vulnerability",
    )

    assert h_primary.counter_hypothesis_id == h_counter.hypothesis_id
    assert h_counter.counter_hypothesis_id == h_primary.hypothesis_id
    assert h_counter.is_counter is True
    assert h_primary.is_counter is False
    assert h_primary.confidence == 0.5
    assert h_counter.confidence == 0.5


@pytest.mark.no_live_infra
def test_falsifier_falsifies_when_no_behavioral_difference():
    engine = HypothesisEngine()
    h_primary, h_counter = engine.create_hypothesis_pair(
        statement="SQL injection in search parameter",
        vulnerability_class="SQLi",
        target_asset="/search?q=",
    )

    judge = FalsificationJudge(hypothesis_engine=engine)
    exp = ExperimentDesigner.design_for_hypothesis(h_primary)

    # Simulated probe result: Baseline and probe returned identical output (e.g. both HTTP 200 with same body)
    identical_result = ExperimentResult(
        experiment_id=exp.experiment_id,
        hypothesis_id=h_primary.hypothesis_id,
        baseline_observation="HTTP 200: 5 items found",
        probe_observation="HTTP 200: 5 items found",
        behavioral_difference_detected=False,
        evidence_payload={},
    )

    eval_res = judge.evaluate(exp, identical_result)
    assert eval_res.verdict == EpistemicVerdict.FALSIFIED
    # Primary hypothesis confidence must decrease
    assert engine.get(h_primary.hypothesis_id).confidence < 0.5
    # Counter hypothesis confidence must increase
    assert engine.get(h_counter.hypothesis_id).confidence > 0.5


@pytest.mark.no_live_infra
def test_falsifier_confirms_when_behavioral_difference_and_evidence():
    engine = HypothesisEngine()
    h_primary, h_counter = engine.create_hypothesis_pair(
        statement="IDOR in order retrieval",
        vulnerability_class="IDOR",
        target_asset="/api/orders/999",
    )

    judge = FalsificationJudge(hypothesis_engine=engine)
    exp = ExperimentDesigner.design_for_hypothesis(h_primary)

    # First probe with evidence
    res1 = ExperimentResult(
        experiment_id=exp.experiment_id,
        hypothesis_id=h_primary.hypothesis_id,
        baseline_observation="HTTP 403 Forbidden for tenant A",
        probe_observation="HTTP 200 OK: Leaked tenant B order details",
        behavioral_difference_detected=True,
        difference_description="Swapped X-User-ID returned unauthorized data",
        evidence_payload={"leaked_order_id": 999, "tenant": "B"},
    )
    judge.evaluate(exp, res1)
    assert engine.get(h_primary.hypothesis_id).confidence > 0.5

    # Second probe confirming reproduction
    res2 = ExperimentResult(
        experiment_id=exp.experiment_id,
        hypothesis_id=h_primary.hypothesis_id,
        baseline_observation="HTTP 403 Forbidden",
        probe_observation="HTTP 200 OK: Leaked tenant B order details",
        behavioral_difference_detected=True,
        difference_description="Reproduced in clean session",
        evidence_payload={"leaked_order_id": 999, "reproduced": True},
    )
    eval_res2 = judge.evaluate(exp, res2)

    assert eval_res2.verdict == EpistemicVerdict.CONFIRMED
    assert engine.get(h_primary.hypothesis_id).status == HypothesisStatus.CONFIRMED
    assert engine.get(h_primary.hypothesis_id).confidence >= 0.85
    assert engine.get(h_counter.hypothesis_id).confidence < 0.3


@pytest.mark.no_live_infra
def test_decision_engine_detects_dead_end_and_pivots():
    decision = DecisionEngine(failure_threshold_for_pivot=3)

    asset = "/api/v1/auth"
    strategy = "sqli_timing_attack"

    t1 = decision.record_failure(asset, strategy)
    assert t1.action == DecisionAction.PROCEED

    t2 = decision.record_failure(asset, strategy)
    assert t2.action == DecisionAction.PROCEED

    # Third consecutive failure on same asset/strategy -> must pivot!
    t3 = decision.record_failure(asset, strategy)
    assert t3.action == DecisionAction.PIVOT
    assert decision.is_dead_end(asset, strategy)


@pytest.mark.no_live_infra
def test_dynamic_world_model_state_transitions():
    model = DynamicWorldModel(target="https://app.local", goal="Assess e-commerce portal")
    
    actor = model.register_actor("user_alice", role="customer", privilege_level=1)
    res = model.register_resource("order_101", uri="/orders/101", current_state="pending")

    t = model.record_transition(
        source_state="pending",
        target_state="approved",
        action_taken="POST /orders/101/approve",
        actor_id=actor.actor_id,
        resource_id=res.resource_id,
        side_effects=["inventory_deducted"],
    )

    assert t.target_state == "approved"
    assert model.resources["order_101"].current_state == "approved"
    summary = model.get_summary()
    assert summary["actors_count"] == 1
    assert summary["resources_count"] == 1
    assert summary["transitions_count"] == 1
