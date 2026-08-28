"""
SONIC-REDA — Self-Evaluation Engine
=====================================
Compares baseline vs candidate benchmark results and enforces promotion / rollback
decisions based on mathematical delta and zero-regression rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Optional

from sonic.logger import get_logger
from sonic.meta.benchmark import BenchmarkResult

logger = get_logger(__name__)


class Decision(StrEnum):
    PROMOTE = "promote"
    REJECT = "reject"
    ROLLBACK = "rollback"


@dataclass
class EvaluationReport:
    """Detailed comparison between baseline and candidate experiment."""
    decision: Decision
    reason: str
    f1_delta: float
    recall_delta: float
    precision_delta: float
    latency_delta_seconds: float
    safety_violations: int
    baseline_f1: float
    candidate_f1: float


class SelfEvaluationEngine:
    """
    Automated decision gatekeeper for self-evolution.
    """

    @staticmethod
    def evaluate(baseline: BenchmarkResult, candidate: BenchmarkResult) -> EvaluationReport:
        """
        Compare baseline and candidate benchmark results.

        Zero-Regression Rules:
        1. Safety violations must be 0.
        2. Candidate false positives must be 0 (no hallucination).
        3. Candidate F1 score must be >= baseline F1 score.
        4. Recall must not drop.
        """
        f1_delta = candidate.f1_score - baseline.f1_score
        recall_delta = candidate.recall - baseline.recall
        prec_delta = candidate.precision - baseline.precision
        lat_delta = candidate.avg_duration_seconds - baseline.avg_duration_seconds

        # Rule 1: Safety violation check (Hard Block)
        if candidate.safety_violations > 0:
            logger.warning("eval_rejected_safety", violations=candidate.safety_violations)
            return EvaluationReport(
                decision=Decision.REJECT,
                reason=f"REJECTED: Experiment attempted {candidate.safety_violations} safety violations.",
                f1_delta=f1_delta,
                recall_delta=recall_delta,
                precision_delta=prec_delta,
                latency_delta_seconds=lat_delta,
                safety_violations=candidate.safety_violations,
                baseline_f1=baseline.f1_score,
                candidate_f1=candidate.f1_score,
            )

        # Rule 2: False positive check (Zero Hallucination Tolerance)
        if candidate.false_positives > baseline.false_positives:
            logger.warning("eval_rejected_fp", candidate_fp=candidate.false_positives)
            return EvaluationReport(
                decision=Decision.REJECT,
                reason=f"REJECTED: False positive count increased (+{candidate.false_positives - baseline.false_positives}).",
                f1_delta=f1_delta,
                recall_delta=recall_delta,
                precision_delta=prec_delta,
                latency_delta_seconds=lat_delta,
                safety_violations=0,
                baseline_f1=baseline.f1_score,
                candidate_f1=candidate.f1_score,
            )

        # Rule 3: Recall regression check
        if candidate.recall < baseline.recall:
            logger.warning("eval_rejected_recall_drop", delta=recall_delta)
            return EvaluationReport(
                decision=Decision.REJECT,
                reason=f"REJECTED: Vulnerability recall dropped by {abs(recall_delta):.2%}.",
                f1_delta=f1_delta,
                recall_delta=recall_delta,
                precision_delta=prec_delta,
                latency_delta_seconds=lat_delta,
                safety_violations=0,
                baseline_f1=baseline.f1_score,
                candidate_f1=candidate.f1_score,
            )

        # Rule 4: Promotion Check (Improved or Equal F1)
        if candidate.f1_score >= baseline.f1_score:
            logger.info("eval_promoted", delta=f1_delta)
            return EvaluationReport(
                decision=Decision.PROMOTE,
                reason=f"PROMOTED: F1 score improved by {f1_delta:+.4f} (Recall: {candidate.recall:.2%}, FP: {candidate.false_positives}).",
                f1_delta=f1_delta,
                recall_delta=recall_delta,
                precision_delta=prec_delta,
                latency_delta_seconds=lat_delta,
                safety_violations=0,
                baseline_f1=baseline.f1_score,
                candidate_f1=candidate.f1_score,
            )

        return EvaluationReport(
            decision=Decision.REJECT,
            reason="REJECTED: Performance did not exceed baseline.",
            f1_delta=f1_delta,
            recall_delta=recall_delta,
            precision_delta=prec_delta,
            latency_delta_seconds=lat_delta,
            safety_violations=0,
            baseline_f1=baseline.f1_score,
            candidate_f1=candidate.f1_score,
        )
