"""
Synthetic Self-Evolution Mission: Full Phase 8 Self-Improvement and Evolution Loop.
"""

import asyncio
import pytest

from sonic.evolution.models import (
    CandidateMetrics,
    EvolutionCandidate,
    EvolutionMemoryItem,
    EvolutionPolicy,
    EvolutionState,
    FailureCategory,
    FailurePattern,
    ImprovementHypothesis,
)
from sonic.evolution.failure_miner import FailureMiner
from sonic.evolution.candidate_generator import CandidateGenerator
from sonic.evolution.lab import EvolutionLab
from sonic.evolution.comparator import BaselineComparator
from sonic.evolution.promotion import PromotionEngine, CanaryManager
from sonic.evolution.memory import EvolutionMemoryStore


def test_synthetic_self_evolution_lifecycle():
    async def _run():
        policy = EvolutionPolicy()
        memory_store = EvolutionMemoryStore()
        generator = CandidateGenerator(policy=policy)
        lab = EvolutionLab(compute_provider=None, policy=policy)

        # Baseline metrics (v1.0.0)
        baseline_metrics = CandidateMetrics(
            precision=0.75,
            recall=0.60,
            f1_score=0.667,
            false_positives=4,
            false_negatives=4,
            latency_ms=300.0,
            token_cost=0.08,
            safety_violations=0,
        )

        # 1. UNDERSTAND & SELF-EVALUATE: Mine failure telemetry
        missed_benchmarks = [
            {
                "expected_vuln": "JWT Algorithm None Signature Bypass",
                "target": "https://auth.target.corp",
                "agent_type": "dynamic",
                "is_critical": True,
                "recommended_skill": "JWT differential header testing",
            }
        ]
        patterns = FailureMiner.mine_execution_data(missed_benchmarks=missed_benchmarks)
        assert len(patterns) == 1
        fp = patterns[0]
        assert fp.category == FailureCategory.FALSE_NEGATIVE

        # 2. PROPOSE: Formulate Improvement Hypothesis
        hyp = generator.formulate_hypothesis(fp)
        assert hyp is not None
        assert "agent_strategies" in hyp.affected_components

        # 3. BUILD: Generate Evolution Candidate
        candidate = generator.generate_candidate(
            hypothesis=hyp,
            parent_version="v1.0.0",
            candidate_version="v1.1.0-cand",
        )
        assert candidate is not None
        assert candidate.state == EvolutionState.CANDIDATE_CREATED

        # 4. TEST & BENCHMARK: Run Candidate in Isolated Evolution Lab
        pipeline_res, candidate_metrics = await lab.run_candidate_pipeline(candidate)
        assert pipeline_res.passed_all_critical is True
        assert candidate_metrics.safety_violations == 0

        # 5. COMPARE: Baseline vs Candidate Pareto Evaluation
        comparison = BaselineComparator.compare(baseline_metrics, candidate_metrics)
        assert comparison.is_pareto_improvement is True
        assert comparison.f1_delta > 0.10

        # 6. GATE EVALUATION & CANARY: Evaluate promotion criteria
        approved, reason, next_state = PromotionEngine.evaluate_gates(candidate, comparison, policy)
        assert approved is True
        assert next_state == EvolutionState.CANARY

        # 7. PROMOTE: Canary health validation and production promotion
        canary_healthy, _ = CanaryManager.evaluate_canary_health(error_rate=0.01, crash_count=0)
        assert canary_healthy is True

        candidate.transition_to(EvolutionState.PROMOTED)
        assert candidate.state == EvolutionState.PROMOTED

        # 8. LEARN: Record into Evolution Memory
        memory_item = EvolutionMemoryItem(
            problem=fp.description,
            hypothesis_id=hyp.id,
            candidate_id=candidate.id,
            candidate_version=candidate.candidate_version,
            parent_version=candidate.parent_version,
            baseline_metrics=baseline_metrics,
            candidate_metrics=candidate_metrics,
            decision="promoted",
            decision_reason="F1 improved from 66.7% to 94.7% with 0 safety regressions.",
            lesson="Adding differential header probes significantly increases recall on token vulnerabilities.",
            fingerprint=hyp.fingerprint,
        )
        memory_store.record_experiment(memory_item)

        assert len(memory_store.get_all_history()) == 1
        assert memory_store.is_duplicate(hyp.fingerprint) is True

    asyncio.run(_run())
