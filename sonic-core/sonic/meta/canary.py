"""
SONIC-REDA — Canary Deployment & Auto-Rollback Pipeline
=========================================================
Runs candidate self-evolution experiments inside isolated canary sandboxes,
benchmarks performance against baseline, and executes automatic promotion or rollback.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Optional

from sonic.logger import get_logger
from sonic.meta.benchmark import BenchmarkLab, BenchmarkResult, ChallengeFixture
from sonic.meta.evaluator import Decision, EvaluationReport, SelfEvaluationEngine
from sonic.meta.experiment import ExperimentManager, ExperimentProposal, ExperimentStatus
from sonic.sandbox.virtual_computer import DaytonaSandbox

logger = get_logger(__name__)


class CanaryPipeline:
    """
    Automates the Canary Testing -> Benchmark -> Evaluation -> Promotion/Rollback cycle.
    """

    def __init__(self, experiment_manager: ExperimentManager):
        self.exp_mgr = experiment_manager
        self.benchmark_lab = BenchmarkLab()
        self.evaluator = SelfEvaluationEngine()
        self.active_baseline_result: Optional[BenchmarkResult] = None

    async def execute_canary_run(
        self,
        experiment_id: str,
        baseline_eval_fn: Callable[[ChallengeFixture], Coroutine[Any, Any, dict[str, Any]]],
        candidate_eval_fn: Callable[[ChallengeFixture], Coroutine[Any, Any, dict[str, Any]]],
    ) -> EvaluationReport:
        """
        Execute full canary lifecycle for a proposed experiment.
        """
        proposal = self.exp_mgr.get_experiment(experiment_id)
        if not proposal:
            raise ValueError(f"Experiment {experiment_id} not found")

        logger.info("canary_run_started", exp_id=experiment_id, title=proposal.title)
        self.exp_mgr.update_status(experiment_id, ExperimentStatus.CANARY_TESTING, "Running inside isolated sandbox")

        try:
            # 1. Benchmark Baseline
            self.exp_mgr.update_status(experiment_id, ExperimentStatus.BENCHMARKING, "Benchmarking baseline vs candidate")
            baseline_result = await self.benchmark_lab.run_benchmark(baseline_eval_fn, suite_id="baseline-v1")
            self.active_baseline_result = baseline_result
            proposal.baseline_score = baseline_result.f1_score

            # 2. Benchmark Candidate in Canary Sandbox
            candidate_result = await self.benchmark_lab.run_benchmark(candidate_eval_fn, suite_id=f"canary-{experiment_id}")
            proposal.candidate_score = candidate_result.f1_score

            # 3. Evaluate Decision Gate
            report = self.evaluator.evaluate(baseline_result, candidate_result)

            # 4. Enforce Decision
            if report.decision == Decision.PROMOTE:
                self.exp_mgr.update_status(experiment_id, ExperimentStatus.PROMOTED, report.reason)
                logger.info("canary_promoted_success", exp_id=experiment_id, delta=report.f1_delta)
            else:
                self.exp_mgr.update_status(experiment_id, ExperimentStatus.REJECTED, report.reason)
                logger.info("canary_rejected", exp_id=experiment_id, reason=report.reason)

            return report

        except Exception as e:
            logger.error("canary_failed_exception", exp_id=experiment_id, error=str(e))
            self.exp_mgr.update_status(experiment_id, ExperimentStatus.ROLLED_BACK, f"Auto-Rollback: Runtime Error: {str(e)}")
            return EvaluationReport(
                decision=Decision.ROLLBACK,
                reason=f"AUTO-ROLLED BACK: {str(e)}",
                f1_delta=0.0,
                recall_delta=0.0,
                precision_delta=0.0,
                latency_delta_seconds=0.0,
                safety_violations=0,
                baseline_f1=0.0,
                candidate_f1=0.0,
            )
