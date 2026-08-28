"""
Tests for Phase 8: Evolution Lab Sandbox Execution and Baseline Comparator.
"""

import asyncio
import pytest
from sonic.evolution.models import (
    CandidateMetrics,
    EvolutionCandidate,
    EvolutionState,
)
from sonic.evolution.lab import EvolutionLab
from sonic.evolution.comparator import BaselineComparator


def test_evolution_lab_candidate_run_success():
    async def _run():
        lab = EvolutionLab(compute_provider=None)
        candidate = EvolutionCandidate(
            hypothesis_id="hyp-01",
            parent_version="v1.0.0",
            candidate_version="v1.1.0-cand",
            changes=[{"target": "agent_strategies", "diff": "+ add_rule"}],
        )

        pipeline_res, metrics = await lab.run_candidate_pipeline(candidate)
        assert pipeline_res.passed_all_critical is True
        assert pipeline_res.syntax_passed is True
        assert pipeline_res.security_tests_passed is True
        assert metrics.safety_violations == 0
        assert metrics.f1_score >= 0.90
        assert candidate.state == EvolutionState.BENCHMARKING

    asyncio.run(_run())


def test_evolution_lab_security_failure_rejection():
    async def _run():
        lab = EvolutionLab(compute_provider=None)
        candidate = EvolutionCandidate(
            hypothesis_id="hyp-02",
            parent_version="v1.0.0",
            candidate_version="v1.1.0-bad",
        )

        # Candidate causes a security regression in the sandbox
        pipeline_res, metrics = await lab.run_candidate_pipeline(candidate, simulate_security_failure=True)
        assert pipeline_res.passed_all_critical is False
        assert pipeline_res.security_tests_passed is False
        assert metrics.safety_violations == 1
        assert candidate.state == EvolutionState.REJECTED

    asyncio.run(_run())


def test_baseline_comparator_pareto_evaluation():
    baseline = CandidateMetrics(
        precision=0.80,
        recall=0.60,
        f1_score=0.686,
        false_positives=3,
        false_negatives=4,
        latency_ms=200.0,
        token_cost=0.05,
        safety_violations=0,
    )

    candidate = CandidateMetrics(
        precision=0.95,
        recall=0.85,
        f1_score=0.897,
        false_positives=1,
        false_negatives=1,
        latency_ms=220.0,
        token_cost=0.055,
        safety_violations=0,
    )

    report = BaselineComparator.compare(baseline, candidate)
    assert report.is_pareto_improvement is True
    assert report.f1_delta > 0.20
    assert report.false_positives_delta == -2  # 2 fewer false positives!
    assert report.has_safety_violation is False
