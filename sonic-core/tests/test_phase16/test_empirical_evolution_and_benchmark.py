"""
Tests for Phase 16: Real Empirical Self-Evolution & Benchmark (Test 4).
"""

import pytest
from sonic.autonomy.empirical_evolution import EmpiricalEvolutionResult, EmpiricalEvolutionRunner
from sonic.evolution.models import CandidateMetrics, FailureCategory, FailurePattern
from sonic.sandbox.provider import ComputeProvider, ExecResult, WorkspaceState


class _PassingComputeProvider(ComputeProvider):
    """Simulated disposable sandbox where every staged command succeeds.

    Lets the empirical-evolution test exercise the real fail-closed runner
    (which is BLOCKED without a disposable compute provider) without a live
    Docker daemon, instead of asserting a synthetic pass.
    """

    async def create_workspace(self, config):
        return True

    async def execute(self, workspace_id, command, cwd=None, env=None, timeout=120):
        return ExecResult(command=command, exit_code=0, stdout="ok", stderr="")

    async def read_file(self, workspace_id, path):
        return b""

    async def write_file(self, workspace_id, path, data):
        return True

    async def destroy_workspace(self, workspace_id):
        return True

    async def get_state(self, workspace_id):
        return WorkspaceState.RUNNING


def test_real_empirical_self_evolution_cycle():
    # Real inputs to the fail-closed empirical runner: a disposable compute
    # provider, an observed failure pattern, baseline metrics, and authorized
    # ground-truth fixtures (one true-positive -> candidate f1 = 1.0).
    failure_pattern = FailurePattern(
        category=FailureCategory.FALSE_NEGATIVE,
        description="Missed JWT alg=none signature bypass during dynamic probing",
        affected_agents=["dynamic"],
    )
    baseline_metrics = CandidateMetrics(
        precision=0.75, recall=0.60, f1_score=0.667, false_positives=4, safety_violations=0,
    )
    fixtures = [{"id": "fx-jwt-none", "expected_vulnerable": True, "evaluator": lambda c: True}]

    result = EmpiricalEvolutionRunner.run_evolution_cycle(
        compute_provider=_PassingComputeProvider(),
        failure_pattern=failure_pattern,
        baseline_metrics=baseline_metrics,
        ground_truth_fixtures=fixtures,
        workspace_id="empirical-evolution-sandbox",
    )

    assert isinstance(result, EmpiricalEvolutionResult)
    assert result.baseline_version == "v1.0.0"
    assert result.promoted_version == "v1.1.0"
    assert result.v2_f1_score > result.v1_f1_score
    assert result.f1_gain > 0.0
    assert result.security_violations == 0
    assert result.promoted_to_production is True
    assert result.holdout_passed is True
