"""
SONIC-REDA — Promotion, Canary & Automatic Rollback Engine (Phase 8)
=====================================================================
Evaluates strict multi-gate promotion criteria, monitors canary deployment health,
and triggers instant rollback upon safety or performance anomalies.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from sonic.evolution.comparator import ComparisonReport
from sonic.evolution.models import (
    EvolutionCandidate,
    EvolutionPolicy,
    EvolutionState,
)
from sonic.logger import get_logger

logger = get_logger(__name__)


def _run_async(coro: Any) -> Any:
    """
    Run a coroutine from synchronous code, handling both the no-event-loop
    case (asyncio.run) and the already-running-loop case (nest_asyncio fallback
    or graceful failure). Returns None if execution is not possible.
    """
    try:
        return asyncio.run(coro)
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            logger.warning("async_call_from_running_loop_skipped", error=str(e))
            coro.close()
            return None
        raise


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
    def deploy_canary(
        candidate: EvolutionCandidate,
        traffic_percent: float = 10.0,
        compute_provider: Optional[Any] = None,
        workspace_id: Optional[str] = None,
        routing_config: Optional[dict[str, Any]] = None,
    ) -> bool:
        """
        Assign canary traffic percentage. When a compute_provider + workspace_id
        are supplied, also write a canary routing config to the deployment
        (e.g., nginx upstream weights) so traffic is actually routed.
        """
        candidate.canary_traffic_percent = traffic_percent
        candidate.transition_to(EvolutionState.CANARY)

        routing_applied = False
        if compute_provider is not None and workspace_id:
            import json

            config_path = "/etc/sonic/canary_routing.json"
            config_content = {
                "candidate_id": candidate.id,
                "candidate_version": candidate.candidate_version,
                "traffic_percent": traffic_percent,
                "routes": routing_config or {"canary": traffic_percent, "baseline": 100 - traffic_percent},
            }
            routing_applied = _run_async(
                compute_provider.write_file(
                    workspace_id, config_path, json.dumps(config_content, indent=2)
                )
            )

        logger.info(
            "canary_deployed",
            candidate_id=candidate.id,
            traffic=f"{traffic_percent}%",
            routing_applied=routing_applied,
        )
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
    Executes instant rollback to parent baseline version via git revert when a
    compute provider is available; otherwise falls back to status-only rollback.
    """

    @staticmethod
    def execute_rollback(
        candidate: EvolutionCandidate,
        reason: str,
        baseline_version: str = "v1.0.0",
        compute_provider: Optional[Any] = None,
        workspace_id: Optional[str] = None,
        bad_commit_sha: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Rollback candidate and restore baseline version.

        When compute_provider + workspace_id are supplied, performs a real
        `git revert` (or `git reset --hard` to baseline) in the sandbox.
        """
        git_result: dict[str, Any] = {}
        git_rollback_performed = False

        if compute_provider is not None and workspace_id:
            try:
                if bad_commit_sha:
                    cmd = f"git revert --no-edit {bad_commit_sha} || git reset --hard {baseline_version}"
                else:
                    cmd = f"git reset --hard {baseline_version}"
                res = _run_async(
                    compute_provider.execute(
                        workspace_id, command=cmd, cwd="/home/sonic/workspace"
                    )
                )
                git_rollback_performed = bool(res and res.exit_code == 0)
                git_result = {
                    "stdout": (res.stdout[:500] if res.stdout else "") if res else "",
                    "exit_code": res.exit_code if res else -1,
                    "performed": git_rollback_performed,
                }
            except Exception as e:
                logger.error("git_rollback_failed", error=str(e))
                git_result = {"performed": False, "error": str(e)}

        candidate.transition_to(EvolutionState.ROLLED_BACK)
        candidate.canary_traffic_percent = 0.0
        logger.warning(
            "candidate_rolled_back",
            candidate_id=candidate.id,
            restored_version=baseline_version,
            reason=reason,
            git_rollback_performed=git_rollback_performed,
        )
        return {
            "candidate_id": candidate.id,
            "candidate_version": candidate.candidate_version,
            "rolled_back_to": baseline_version,
            "status": "rolled_back",
            "reason": reason,
            "git_rollback_performed": git_rollback_performed,
            "git_result": git_result,
        }
