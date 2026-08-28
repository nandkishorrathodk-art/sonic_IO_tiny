"""
SONIC-REDA — Promotion, Canary & Automatic Rollback Engine (Phase 8)
=====================================================================
Evaluates strict multi-gate promotion criteria, monitors canary deployment health,
and triggers instant rollback upon safety or performance anomalies.
"""

from __future__ import annotations

from typing import Any, Optional

from sonic.evolution.comparator import ComparisonReport
from sonic.evolution.models import (
    EvolutionCandidate,
    EvolutionPolicy,
    EvolutionState,
)
from sonic.logger import get_logger

logger = get_logger(__name__)


class PromotionEngine:
    """
    Evaluates multi-gate promotion policies for evolution candidates.
    """

    @classmethod
    def evaluate_gates(
        cls,
        candidate: EvolutionCandidate,
        comparison: ComparisonReport,
        policy: Optional[EvolutionPolicy] = None,
    ) -> tuple[bool, str, EvolutionState]:
        """
        Evaluate all gates before allowing canary or production promotion.
        """
        pol = policy or EvolutionPolicy()
        rejection_reasons = []

        # Gate 1: Zero Safety Violations (Immutable Core)
        if comparison.has_safety_violation or comparison.candidate.safety_violations > 0:
            rejection_reasons.append("Safety Gate Failed: Candidate caused security violation in sandbox tests.")

        # Gate 2: F1 Score Improvement
        if comparison.candidate.f1_score < comparison.baseline.f1_score:
            rejection_reasons.append(
                f"Accuracy Gate Failed: Candidate F1 ({comparison.candidate.f1_score:.3f}) is below baseline ({comparison.baseline.f1_score:.3f})."
            )

        # Gate 3: False Positive Non-Regression
        if comparison.candidate.false_positives > comparison.baseline.false_positives:
            rejection_reasons.append(
                f"Precision Gate Failed: Candidate introduced {comparison.candidate.false_positives - comparison.baseline.false_positives} new false positives."
            )

        # Gate 4: Budget & Cost Constraints
        if comparison.candidate.token_cost > 10.0:  # Arbitrary hard ceiling
            rejection_reasons.append("Budget Gate Failed: Candidate exceeded maximum allowed token cost per task.")

        if rejection_reasons:
            reason_str = " | ".join(rejection_reasons)
            candidate.transition_to(EvolutionState.REJECTED)
            logger.warning("candidate_promotion_rejected", candidate_id=candidate.id, reasons=reason_str)
            return False, reason_str, EvolutionState.REJECTED

        # Passed all automated gates
        candidate.transition_to(EvolutionState.CANARY)
        logger.info("candidate_promotion_approved_for_canary", candidate_id=candidate.id)
        return True, "Passed all automated promotion gates. Ready for Canary deployment.", EvolutionState.CANARY


class CanaryManager:
    """
    Manages gradual canary rollout of approved candidates to live workloads.
    """

    @staticmethod
    def deploy_canary(candidate: EvolutionCandidate, traffic_percent: float = 10.0) -> bool:
        """Assign canary traffic percentage."""
        candidate.canary_traffic_percent = traffic_percent
        candidate.transition_to(EvolutionState.CANARY)
        logger.info("canary_deployed", candidate_id=candidate.id, traffic=f"{traffic_percent}%")
        return True

    @staticmethod
    def evaluate_canary_health(
        error_rate: float,
        crash_count: int,
        safety_anomaly_detected: bool = False,
        max_error_threshold: float = 0.05,
    ) -> tuple[bool, str]:
        """
        Evaluate live telemetry from canary deployment.
        """
        if safety_anomaly_detected:
            return False, "Canary health FAILED: Safety anomaly detected in live traffic."
        if crash_count > 0:
            return False, f"Canary health FAILED: {crash_count} crashes detected during canary run."
        if error_rate > max_error_threshold:
            return False, f"Canary health FAILED: Error rate ({error_rate*100:.1f}%) exceeded threshold ({max_error_threshold*100:.1f}%)."

        return True, "Canary health PASSED: Error and safety rates within normal parameters."


class RollbackManager:
    """
    Executes instant rollback to parent baseline version.
    """

    @staticmethod
    def execute_rollback(
        candidate: EvolutionCandidate,
        reason: str,
        baseline_version: str = "v1.0.0",
    ) -> dict[str, Any]:
        """
        Rollback candidate and restore baseline version.
        """
        candidate.transition_to(EvolutionState.ROLLED_BACK)
        candidate.canary_traffic_percent = 0.0
        logger.warning(
            "candidate_rolled_back",
            candidate_id=candidate.id,
            restored_version=baseline_version,
            reason=reason,
        )
        return {
            "candidate_id": candidate.id,
            "candidate_version": candidate.candidate_version,
            "rolled_back_to": baseline_version,
            "status": "rolled_back",
            "reason": reason,
        }
