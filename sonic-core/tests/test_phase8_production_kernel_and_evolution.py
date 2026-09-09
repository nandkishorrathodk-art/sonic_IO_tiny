"""
Tests for Phase 8: Production Kernel, Brain Tool-Decoupling & Evolution Pipeline
=================================================================================
Verifies:
1. ResearchBrain pure reasoning (zero direct tool execution handles).
2. MissionKernel FSM state transitions and multi-dimensional budget exhaustion.
3. VerificationLab rigorous 5-step proof requirement (Impact + Repro + Diff).
4. EvolutionPipeline safety immutability, canary stages, and operator approval gate.
"""

from __future__ import annotations

import pytest

from sonic.brain.planner import ExperimentPlan, ResearchBrain
from sonic.brain.world_model import DynamicWorldModel
from sonic.evidence.custody import CustodyChain
from sonic.evidence.models import (
    ArtifactType,
    EvidenceItem,
    FindingSeverity,
    ProvenancedFinding,
)
from sonic.evidence.verification_lab import VerificationLab, VerificationStage
from sonic.evolution.pipeline import EvolutionPipeline, EvolutionStage
from sonic.kernel.mission import MissionBudget, MissionKernel, MissionState


@pytest.mark.no_live_infra
def test_brain_pure_reasoning_without_tools():
    brain = ResearchBrain(tenant_id="t-prod")
    model = DynamicWorldModel(target="https://api.portal.local", goal="Assess authentication")
    
    # Register an unknown
    model.unknowns.register_unknown("Is JWT signed with HS256 using weak secret?")

    # Brain plans next step without touching any shell or tool
    plan: ExperimentPlan = brain.plan_next_step(model)

    assert plan.experiment is not None
    assert plan.selected_hypothesis is not None
    assert plan.specialist_type in ("auth", "api", "web")
    assert not plan.goal_satisfied
    # Assert brain has NO tool attributes
    assert not hasattr(brain, "execute")
    assert not hasattr(brain, "run_shell")
    assert not hasattr(brain, "browser")


@pytest.mark.no_live_infra
def test_mission_kernel_fsm_and_budget_enforcement():
    budget = MissionBudget(max_actions=2, time_limit_seconds=10.0)
    kernel = MissionKernel(target="https://target.local", goal="Penetration test", budget=budget)

    assert kernel.state == MissionState.CREATED

    # Out of scope target fails closed to BLOCKED
    kernel_blocked = MissionKernel(target="https://unauthorized.org", goal="Test", budget=budget)
    assert not kernel_blocked.validate_scope(in_scope=False, reason="Target not authorized by ROE")
    assert kernel_blocked.state == MissionState.BLOCKED

    # Valid scope transitions to SCOPED
    assert kernel.validate_scope(in_scope=True, reason="Whitelisted in customer ROE")
    assert kernel.state == MissionState.SCOPED

    # Transitions to PLANNING -> RESEARCHING
    assert kernel.transition_to(MissionState.PLANNING)
    assert kernel.transition_to(MissionState.RESEARCHING)

    # Consume budget
    kernel.budget_tracker.consume_action(count=1)
    assert kernel.check_budget() is True

    # Consuming beyond budget stops the mission cleanly
    kernel.budget_tracker.consume_action(count=2)
    assert kernel.check_budget() is False
    assert kernel.state == MissionState.COMPLETED


@pytest.mark.no_live_infra
def test_verification_lab_rigorous_pipeline():
    evidence_text = "HTTP 200 OK: Leaked secret API keys"
    content_hash = CustodyChain.compute_hash(evidence_text)

    item = EvidenceItem(
        tenant_id="t-1",
        engagement_id="eng-1",
        artifact_type=ArtifactType.HTTP_RESPONSE,
        raw_content=evidence_text,
        content_hash=content_hash,
    )

    finding = ProvenancedFinding(
        tenant_id="t-1",
        engagement_id="eng-1",
        title="Sensitive API Key Exfiltration",
        description="Leaked master key via unauthenticated debug route",
        target="https://api.target.local",
        endpoint="/debug/keys",
        vulnerability_class="InformationDisclosure",
        severity=FindingSeverity.CRITICAL,
        poc="curl https://api.target.local/debug/keys",
        evidence_items=[item],
    )

    # 1. Reject if impact proof missing
    rep_no_impact = VerificationLab.verify_finding(
        finding=finding,
        baseline_observation="HTTP 404 Not Found",
        probe_observation=evidence_text,
        reproduction_observation=evidence_text,
        impact_proof=None,
    )
    assert rep_no_impact.verified is False
    assert rep_no_impact.current_stage == VerificationStage.REJECTED
    assert any("impact assessment failed" in r.lower() for r in rep_no_impact.rejection_reasons)

    # 2. Accept with concrete impact proof and clean reproduction
    rep_certified = VerificationLab.verify_finding(
        finding=finding,
        baseline_observation="HTTP 404 Not Found",
        probe_observation=evidence_text,
        reproduction_observation=evidence_text,
        impact_proof={"consequence": "Confidentiality breach: Master administrative API keys disclosed."},
    )
    assert rep_certified.verified is True
    assert rep_certified.current_stage == VerificationStage.VERIFIED
    assert len(rep_certified.custody_hash) == 64


@pytest.mark.no_live_infra
def test_evolution_pipeline_safety_immutability_and_canary_flow():
    pipeline = EvolutionPipeline()

    # Invariant: AI attempting to alter safety kernel is strictly rejected
    prop_bad, reason = pipeline.submit_proposal(
        target_component="sonic/safety/kernel.py",
        description="Relax egress filter for faster scans",
        code_diff="- egress.check()\n+ pass",
    )
    assert prop_bad.stage == EvolutionStage.REJECTED
    assert "Cannot self-modify safety kernel" in reason

    # Valid proposal for a specialist adapter
    prop_good, _ = pipeline.submit_proposal(
        target_component="sonic/tools/adapters/nmap.py",
        description="Optimize nmap timing template to -T4",
        code_diff="- -T3\n+ -T4",
    )
    assert prop_good.stage == EvolutionStage.ISOLATED_BRANCH

    # Progression through validation gates
    assert pipeline.advance_stage(prop_good.proposal_id, EvolutionStage.TESTS_PASSING, "All unit tests green")
    assert pipeline.advance_stage(prop_good.proposal_id, EvolutionStage.SECURITY_REGRESSION_PASSING, "36/36 safety tests green")
    assert pipeline.advance_stage(prop_good.proposal_id, EvolutionStage.BENCHMARK_VALIDATED, "15% faster scan with 0 FP increase")
    assert pipeline.advance_stage(prop_good.proposal_id, EvolutionStage.CANARY_ACTIVE, "Active in 5% canary testing")

    # Operator approval gate
    assert not pipeline.promote_with_approval(prop_good.proposal_id, operator_approved=False)
    assert prop_good.stage == EvolutionStage.ROLLED_BACK
