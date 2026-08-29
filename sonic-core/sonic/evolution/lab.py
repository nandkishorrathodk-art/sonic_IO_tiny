"""
SONIC-REDA — Isolated Evolution Lab (Phase 8)
==============================================
Runs candidate test pipelines strictly within isolated ComputeProvider sandboxes.
Enforces FAIL-CLOSED execution: candidate code is never executed on the host OS.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Optional

from sonic.evolution.models import (
    CandidateMetrics,
    EvolutionCandidate,
    EvolutionPolicy,
    EvolutionState,
)
from sonic.logger import get_logger
from sonic.sandbox.provider import ComputeProvider

logger = get_logger(__name__)


class TestPipelineResult:
    """Detailed stage-by-stage results of an evolution candidate run in the lab."""
    def __init__(self):
        # A stage is true only after a real command completes in the
        # configured evaluation sandbox. Unknown stages fail closed.
        self.syntax_passed: bool = False
        self.type_check_passed: bool = False
        self.unit_tests_passed: bool = False
        self.integration_tests_passed: bool = False
        self.security_tests_passed: bool = False
        self.benchmark_score: float = 0.0
        self.metrics: Optional[CandidateMetrics] = None
        self.errors: list[str] = []

    @property
    def passed_all_critical(self) -> bool:
        return (
            self.syntax_passed and
            self.type_check_passed and
            self.unit_tests_passed and
            self.integration_tests_passed and
            self.security_tests_passed and
            len(self.errors) == 0
        )


class EvolutionLab:
    """
    Dedicated evaluation sandbox for candidate testing and benchmark execution.
    """

    def __init__(
        self,
        compute_provider: Optional[ComputeProvider] = None,
        policy: Optional[EvolutionPolicy] = None,
    ):
        self.provider = compute_provider
        self.policy = policy or EvolutionPolicy()

    async def run_candidate_pipeline(
        self,
        candidate: EvolutionCandidate,
        ground_truth_fixtures: Optional[list[dict[str, Any]]] = None,
        workspace_id: str = "evolution-lab-sandbox",
        simulate_security_failure: bool = False,
        simulate_syntax_failure: bool = False,
    ) -> tuple[TestPipelineResult, CandidateMetrics]:
        """
        Execute candidate through full test pipeline in sandbox.
        """
        logger.info("evolution_lab_pipeline_started", candidate_id=candidate.id, version=candidate.candidate_version)
        candidate.transition_to(EvolutionState.TESTING)
        result = TestPipelineResult()

        if self.provider is None:
            result.errors.append(
                "Evolution evaluation is blocked: no disposable compute provider is configured. "
                "SONIC will not execute or score a candidate on the host."
            )
            candidate.transition_to(EvolutionState.REJECTED)
            metrics = CandidateMetrics(safety_violations=1)
            result.metrics = metrics
            return result, metrics

        # Every stage is command-backed and runs through ComputeProvider. No
        # host shell or synthetic pass/fail values are allowed.
        commands = [
            ("syntax", os.environ.get("SONIC_EVOLUTION_SYNTAX_COMMAND", "python -m compileall -q .")),
            ("type", os.environ.get("SONIC_EVOLUTION_TYPE_COMMAND", "python -m mypy .")),
            ("unit", os.environ.get("SONIC_EVOLUTION_UNIT_COMMAND", "python -m pytest -q")),
            ("integration", os.environ.get("SONIC_EVOLUTION_INTEGRATION_COMMAND", "python -m pytest -q tests/integration")),
            ("security", os.environ.get("SONIC_EVOLUTION_SECURITY_COMMAND", "python -m pytest -q tests/security")),
        ]
        stage_results: dict[str, Any] = {}
        measured_latency_ms = 0.0
        for stage, command in commands:
            started = time.perf_counter()
            try:
                execution = await self.provider.execute(workspace_id, command, timeout=self.policy.max_runtime_seconds)
                duration = getattr(execution, "duration_seconds", 0.0) or (time.perf_counter() - started)
                measured_latency_ms += float(duration) * 1000.0
                passed = execution.exit_code == 0 and not getattr(execution, "timed_out", False)
                stage_results[stage] = passed
                if not passed:
                    detail = (getattr(execution, "stderr", "") or getattr(execution, "stdout", "") or "command failed").strip()
                    result.errors.append(f"{stage} stage failed ({execution.exit_code}): {detail[:500]}")
            except Exception as exc:
                stage_results[stage] = False
                result.errors.append(f"{stage} stage could not execute in evaluation sandbox: {exc}")

        result.syntax_passed = stage_results.get("syntax", False)
        result.type_check_passed = stage_results.get("type", False)
        result.unit_tests_passed = stage_results.get("unit", False)
        result.integration_tests_passed = stage_results.get("integration", False)
        result.security_tests_passed = stage_results.get("security", False)

        if not result.passed_all_critical:
            candidate.transition_to(EvolutionState.REJECTED)
            metrics = CandidateMetrics(
                execution_count=len(commands),
                verification_success_rate=sum(bool(v) for v in stage_results.values()) / len(commands),
                latency_ms=round(measured_latency_ms, 3),
                safety_violations=1 if not result.security_tests_passed else 0,
            )
            result.metrics = metrics
            return result, metrics

        # 1. Syntax Check
        if simulate_syntax_failure:
            result.syntax_passed = False
            result.errors.append("SyntaxError: invalid syntax in candidate mutation.")
            candidate.transition_to(EvolutionState.REJECTED)
            metrics = CandidateMetrics(safety_violations=0)
            result.metrics = metrics
            return result, metrics

        # 3. Security Regression Suite (Immutable Invariant Check)
        if simulate_security_failure:
            result.security_tests_passed = False
            result.errors.append("SecurityRegressionError: Candidate mutation violated tenant isolation boundary.")
            candidate.transition_to(EvolutionState.REJECTED)
            metrics = CandidateMetrics(safety_violations=1)
            result.metrics = metrics
            return result, metrics

        candidate.transition_to(EvolutionState.BENCHMARKING)

        # 4. Ground-Truth Benchmark Dynamic Evaluation
        tp = 0
        fp = 0
        fn = 0

        fixtures = ground_truth_fixtures or []
        if not fixtures:
            result.errors.append("Benchmark blocked: no authorized ground-truth fixtures were supplied")
            candidate.transition_to(EvolutionState.REJECTED)
            metrics = CandidateMetrics(
                execution_count=len(commands),
                verification_success_rate=1.0,
                latency_ms=round(measured_latency_ms, 3),
                safety_violations=0,
            )
            result.metrics = metrics
            return result, metrics

        total_fixtures = len(fixtures)
        for fix in fixtures:
            eval_fn = fix.get("evaluator")
            is_vuln = fix.get("expected_vulnerable", True)

            if callable(eval_fn):
                is_detected = bool(eval_fn(candidate))
            else:
                result.errors.append(f"Fixture {fix.get('id', '<unknown>')} has no executable evaluator")
                is_detected = False

            if is_detected and is_vuln:
                tp += 1
            elif is_detected and not is_vuln:
                fp += 1
            elif not is_detected and is_vuln:
                fn += 1

        precision = round(tp / max(1, (tp + fp)), 3) if (tp + fp) > 0 else 0.0
        recall = round(tp / max(1, (tp + fn)), 3) if (tp + fn) > 0 else 0.0
        f1 = CandidateMetrics.compute_f1(precision, recall)

        metrics = CandidateMetrics(
            precision=precision,
            recall=recall,
            f1_score=f1,
            false_positives=fp,
            false_negatives=fn,
            evidence_completeness=1.0 if total_fixtures and not result.errors else 0.0,
            verification_success_rate=1.0,
            prediction_accuracy=round((tp + (total_fixtures - fp - fn)) / max(1, total_fixtures), 3),
            execution_count=len(commands) + total_fixtures,
            latency_ms=round(measured_latency_ms, 3),
            token_cost=0.0,
            resource_usage=0.0,
            safety_violations=0,
        )

        result.benchmark_score = f1 * 100.0
        result.metrics = metrics

        logger.info(
            "evolution_lab_pipeline_completed",
            candidate_id=candidate.id,
            f1_score=f1,
            passed=result.passed_all_critical,
        )
        return result, metrics
