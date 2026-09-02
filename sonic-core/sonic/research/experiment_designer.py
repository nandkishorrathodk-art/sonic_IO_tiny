"""
SONIC-REDA — Experiment Designer & Adversarial Challenger (Phase 6)
=====================================================================
Generates discriminating experiments that distinguish between competing hypotheses,
and formulates adversarial falsification challenges to eliminate confirmation bias.
"""

from __future__ import annotations

from sonic.logger import get_logger
from sonic.research.epistemic import CompetingHypothesis, Prediction, Unknown
from sonic.research.information_gain import ActionCandidate

logger = get_logger(__name__)


class ExperimentDesigner:
    """
    Designs high-value experiments to resolve unknowns and discriminate between competing hypotheses.
    """

    @staticmethod
    def design_discriminating_experiment(
        hypothesis_a: CompetingHypothesis,
        hypothesis_b: CompetingHypothesis,
        target: str,
        unknown_id: str = "",
    ) -> tuple[ActionCandidate, Prediction]:
        """
        Generate an experiment specifically designed to separate two competing hypotheses.
        """
        exp_name = f"Discriminating Test: '{hypothesis_a.statement[:30]}' vs '{hypothesis_b.statement[:30]}'"

        candidate = ActionCandidate(
            name=exp_name,
            description=f"Differentiate between Hypothesis A ({hypothesis_a.statement}) and Hypothesis B ({hypothesis_b.statement})",
            agent_type="dynamic",
            task_payload={
                "target": target,
                "task": "discriminating_experiment",
                "hypothesis_a": hypothesis_a.id,
                "hypothesis_b": hypothesis_b.id,
            },
            rationale=f"Determine whether {hypothesis_a.statement} or {hypothesis_b.statement} explains observed behavior",
            expected_information_gain=0.9,
            expected_confidence_gain=0.5,
            estimated_cost=0.2,
            estimated_time_seconds=90,
            risk=0.1,
            resolves_unknown_id=unknown_id,
            tests_hypothesis_id=hypothesis_a.id,
            is_discriminating_test=True,
        )

        prediction = Prediction(
            experiment_name=exp_name,
            expected_outcomes={
                "if_hypothesis_a": hypothesis_a.falsification_criteria or "Outcome confirms Hypothesis A",
                "if_hypothesis_b": hypothesis_b.falsification_criteria or "Outcome confirms Hypothesis B",
            },
            falsification_observation="Outcome is inconsistent with both hypotheses",
            confidence=0.75,
        )

        return candidate, prediction

    @staticmethod
    def design_unknown_resolution_experiment(
        unknown: Unknown,
        target: str,
    ) -> tuple[ActionCandidate, Prediction]:
        """Generate an experiment to resolve an open unknown question."""
        exp_name = f"Investigate Uncertainty: {unknown.question[:40]}"

        candidate = ActionCandidate(
            name=exp_name,
            description=f"Resolve uncertainty: {unknown.question}",
            agent_type="dynamic" if "endpoint" in unknown.question.lower() or "auth" in unknown.question.lower() else "recon",
            task_payload={"target": target, "question": unknown.question, "task": "resolve_unknown"},
            rationale=f"Reduce uncertainty on {unknown.question} to enable confident decision making",
            expected_information_gain=unknown.importance,
            expected_confidence_gain=0.3,
            estimated_cost=0.15,
            estimated_time_seconds=60,
            risk=0.05,
            resolves_unknown_id=unknown.id,
            is_discriminating_test=False,
        )

        prediction = Prediction(
            experiment_name=exp_name,
            expected_outcomes={"goal": f"Obtain conclusive answer for '{unknown.question}'"},
            confidence=0.7,
        )

        return candidate, prediction


class AdversarialChallenger:
    """
    Adversarial Self-Challenge Engine.
    Before confirming a high-confidence finding, challenges it by generating
    falsification tests and testing alternative non-vulnerable explanations.
    """

    @staticmethod
    def generate_falsification_challenge(
        hypothesis: CompetingHypothesis,
        target: str,
    ) -> tuple[ActionCandidate, Prediction]:
        """
        Formulate an explicit test designed to disprove the primary hypothesis.
        """
        challenge_name = f"Falsification Challenge: '{hypothesis.statement[:35]}'"

        candidate = ActionCandidate(
            name=challenge_name,
            description=f"Falsify or challenge hypothesis: {hypothesis.statement}. Search for counter-evidence that this is expected application behavior.",
            agent_type="verifier",
            task_payload={
                "target": target,
                "hypothesis_id": hypothesis.id,
                "task": "adversarial_verification",
                "challenge_mode": True,
            },
            rationale="Eliminate false positives and confirmation bias by attempting to disprove the vulnerability",
            expected_information_gain=0.85,
            expected_confidence_gain=0.4,
            estimated_cost=0.2,
            estimated_time_seconds=90,
            risk=0.05,
            tests_hypothesis_id=hypothesis.id,
            is_discriminating_test=True,
        )

        prediction = Prediction(
            experiment_name=challenge_name,
            expected_outcomes={
                "confirm_vuln": "Behavior persists under clean control conditions without side effects",
                "falsify_vuln": "Behavior is reproducible on guest accounts as intended feature or test artifact",
            },
            falsification_observation=hypothesis.falsification_criteria or "Normal application error response observed",
            confidence=0.8,
        )

        return candidate, prediction
