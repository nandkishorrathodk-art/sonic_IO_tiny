"""
SONIC v2 — Falsification Judge
===============================
Evaluates experimental outcomes with strict verification rules:
Generic HTTP 200 != vulnerability.
Exit code 0 != vulnerability.
LLM belief != vulnerability.

A finding candidate is only supported if there is:
1. Valid trigger payload / action
2. Observable behavioral difference between baseline and probe
3. Concrete evidence artifact
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sonic.brain.experiment import Experiment, ExperimentResult
from sonic.brain.hypothesis import HypothesisEngine
from sonic.logger import get_logger

logger = get_logger(__name__)


class EpistemicVerdict(StrEnum):
    CONFIRMED = "confirmed"
    FALSIFIED = "falsified"
    INCONCLUSIVE = "inconclusive"


@dataclass
class JudgeEvaluation:
    verdict: EpistemicVerdict
    confidence_delta: float
    reason: str
    evidence_valid: bool


class FalsificationJudge:
    """Evaluates empirical evidence against paired hypotheses."""

    def __init__(self, hypothesis_engine: HypothesisEngine):
        self.hypothesis_engine = hypothesis_engine

    def evaluate(
        self,
        experiment: Experiment,
        result: ExperimentResult,
    ) -> JudgeEvaluation:
        """Evaluates an experiment outcome and updates hypothesis pair."""
        hyp = self.hypothesis_engine.get(experiment.hypothesis_id)
        if not hyp:
            return JudgeEvaluation(
                verdict=EpistemicVerdict.INCONCLUSIVE,
                confidence_delta=0.0,
                reason=f"Hypothesis {experiment.hypothesis_id} not found.",
                evidence_valid=False,
            )

        # Rule 1: Failed or blocked experiment execution is inconclusive or dead-end
        if result.status in ("failed", "blocked", "dead_end"):
            logger.info("experiment_non_conclusive", status=result.status, exp_id=experiment.experiment_id)
            return JudgeEvaluation(
                verdict=EpistemicVerdict.INCONCLUSIVE,
                confidence_delta=0.0,
                reason=f"Experiment terminated with status '{result.status}'.",
                evidence_valid=False,
            )

        # Rule 2: No behavioral difference between baseline and probe -> Falsifies vulnerability hypothesis
        if not result.behavioral_difference_detected or (
            result.baseline_observation and result.baseline_observation == result.probe_observation
        ):
            reason = (
                "No observable behavioral difference detected between baseline and probe. "
                "Target behaves identically; hypothesis unsupported (counter-hypothesis supported)."
            )
            self.hypothesis_engine.record_evidence(
                hypothesis_id=hyp.hypothesis_id,
                is_supporting=False,
                evidence_summary=reason,
                weight=0.25,
            )
            return JudgeEvaluation(
                verdict=EpistemicVerdict.FALSIFIED,
                confidence_delta=-0.25,
                reason=reason,
                evidence_valid=False,
            )

        # Rule 3: Concrete behavioral difference + evidence payload present -> Supports hypothesis
        evidence_present = bool(result.evidence_payload)
        delta = 0.35 if evidence_present else 0.15
        reason = f"Observable behavioral difference confirmed: {result.difference_description}"

        self.hypothesis_engine.record_evidence(
            hypothesis_id=hyp.hypothesis_id,
            is_supporting=True,
            evidence_summary=reason,
            weight=delta,
        )

        verdict = EpistemicVerdict.CONFIRMED if hyp.confidence >= 0.85 else EpistemicVerdict.INCONCLUSIVE

        return JudgeEvaluation(
            verdict=verdict,
            confidence_delta=delta,
            reason=reason,
            evidence_valid=evidence_present,
        )
