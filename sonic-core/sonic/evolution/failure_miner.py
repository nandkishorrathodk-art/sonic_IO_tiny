"""
SONIC-REDA — Failure Mining Engine (Phase 8)
==============================================
Analyzes historical execution telemetry, prediction errors, contradiction records,
and verification rejections to discover recurring weakness patterns.
"""

from __future__ import annotations

from typing import Any, Optional
from sonic.evolution.models import FailureCategory, FailurePattern
from sonic.logger import get_logger

logger = get_logger(__name__)


class FailureMiner:
    """
    Automated weakness discovery engine that mines execution logs and benchmarks.
    """

    @classmethod
    def mine_execution_data(
        cls,
        execution_logs: Optional[list[dict[str, Any]]] = None,
        prediction_errors: Optional[list[dict[str, Any]]] = None,
        rejected_findings: Optional[list[dict[str, Any]]] = None,
        missed_benchmarks: Optional[list[dict[str, Any]]] = None,
        repeated_failed_attempts: Optional[list[dict[str, Any]]] = None,
    ) -> list[FailurePattern]:
        """
        Scan all telemetry sources and return clustered FailurePattern items.
        """
        patterns: list[FailurePattern] = []

        # 1. Mine False Positives from Rejected Findings
        if rejected_findings:
            for rf in rejected_findings:
                fp = FailurePattern(
                    category=FailureCategory.FALSE_POSITIVE,
                    description=f"False positive finding reported: {rf.get('title', 'Unknown claim')} on {rf.get('target', 'endpoint')}. Failed independent validation: {rf.get('reason', '')}",
                    evidence_ids=rf.get("evidence_ids", []),
                    occurrences=rf.get("occurrences", 1),
                    affected_agents=[rf.get("discovering_agent", "discovery-agent")],
                    severity="high" if rf.get("severity") in ("critical", "high") else "medium",
                    confidence=0.9,
                    proposed_improvement="Refine verification prompts and require multi-tool cross validation before candidate submission.",
                )
                fp.compute_fingerprint()
                patterns.append(fp)

        # 2. Mine False Negatives from Missed Benchmarks
        if missed_benchmarks:
            for mb in missed_benchmarks:
                fp = FailurePattern(
                    category=FailureCategory.FALSE_NEGATIVE,
                    description=f"Missed benchmark vulnerability: '{mb.get('expected_vuln', '')}' on target '{mb.get('target', '')}'. Discovery agent did not explore alternate authorization paths.",
                    occurrences=mb.get("occurrences", 1),
                    affected_agents=[mb.get("agent_type", "dynamic")],
                    severity="critical" if mb.get("is_critical", False) else "high",
                    confidence=0.95,
                    proposed_improvement=f"Introduce {mb.get('recommended_skill', 'specialized authorization differential testing strategy')} in agent dispatch heuristics.",
                )
                fp.compute_fingerprint()
                patterns.append(fp)

        # 3. Mine Prediction Errors
        if prediction_errors:
            for pe in prediction_errors:
                if pe.get("error_score", 0.0) >= 0.5:
                    fp = FailurePattern(
                        category=FailureCategory.PREDICTION_ERROR,
                        description=f"High prediction error ({pe.get('error_score'):.2f}) on experiment '{pe.get('experiment_name', '')}'. Expected {pe.get('expected')}, observed {pe.get('observed')}.",
                        occurrences=1,
                        affected_agents=[pe.get("agent_id", "director")],
                        severity="medium",
                        confidence=0.8,
                        proposed_improvement="Calibrate prediction heuristics with target technology signatures.",
                    )
                    fp.compute_fingerprint()
                    patterns.append(fp)

        # 4. Mine Repeated Failed Attempts / Inefficient Tool Usage
        if repeated_failed_attempts:
            for rfa in repeated_failed_attempts:
                fp = FailurePattern(
                    category=FailureCategory.REPEATED_FAILED_ATTEMPT,
                    description=f"Repeated failed tool execution: method '{rfa.get('method', '')}' failed {rfa.get('count', 2)} times on {rfa.get('target', '')}.",
                    occurrences=rfa.get("count", 2),
                    affected_agents=[rfa.get("agent_type", "tool-executor")],
                    severity="low",
                    confidence=0.85,
                    proposed_improvement="Update tool selection heuristics to prune known ineffective parameter configurations.",
                )
                fp.compute_fingerprint()
                patterns.append(fp)

        logger.info("failure_mining_completed", total_patterns_mined=len(patterns))
        return patterns
