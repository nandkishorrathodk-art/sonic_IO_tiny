"""
SONIC-REDA — Top-Level Autonomous Research Manager (Phase 12)
===============================================================
Orchestrates long-horizon research missions, portfolio management,
parallel track dispatching, anomaly detection, strategy adaptation,
and intelligent stopping judgment.
"""

from __future__ import annotations

from typing import Any

from sonic.logger import get_logger
from sonic.researcher.anomaly_engine import AnomalyDetector, DeadEndDetector, NoveltyEngine
from sonic.researcher.memory import ResearchMemoryStore
from sonic.researcher.models import (
    AnomalyRecord,
    HypothesisPortfolio,
    ResearcherHypothesis,
    ResearcherHypothesisStatus,
    ResearchLead,
    ResearchMode,
    ResearchQuestion,
    ResearchQuestionStatus,
    ResearchReport,
    StopReason,
)
from sonic.researcher.strategy_switcher import InvestigationMethod, StrategySwitcher
from sonic.researcher.track_manager import InvestigationTrackManager

logger = get_logger(__name__)


class ResearchManager:
    """
    Autonomous Mission Research Manager.
    Coordinates questions, hypotheses, tracks, leads, and stopping conditions.
    """

    def __init__(
        self,
        mission_id: str,
        tenant_id: str,
        goal: str,
        mode: ResearchMode = ResearchMode.AUTONOMOUS,
    ):
        self.mission_id = mission_id
        self.tenant_id = tenant_id
        self.goal = goal
        self.mode = mode

        # Core Engines
        self.questions: dict[str, ResearchQuestion] = {}
        self.portfolio = HypothesisPortfolio()
        self.track_manager = InvestigationTrackManager()
        self.dead_end_detector = DeadEndDetector()
        self.strategy_switcher = StrategySwitcher()
        self.memory_store = ResearchMemoryStore()

        # Telemetry & State
        self.leads: dict[str, ResearchLead] = {}
        self.anomalies: list[AnomalyRecord] = []
        self.initial_facts: list[str] = []
        self.evidence_collected: list[str] = []
        self.dead_ends: list[str] = []
        self.is_paused: bool = False
        self.stop_reason: StopReason | None = None
        self.stopping_justification: str = ""

    def add_initial_facts(self, facts: list[str]) -> None:
        self.initial_facts.extend(facts)

    # -------------------------------------------------------------
    # Question Management
    # -------------------------------------------------------------
    def add_question(
        self,
        question: str,
        importance: float = 0.8,
        uncertainty: float = 0.9,
    ) -> ResearchQuestion:
        rq = ResearchQuestion(
            tenant_id=self.tenant_id,
            engagement_id=self.mission_id,
            question=question,
            importance=importance,
            uncertainty=uncertainty,
            status=ResearchQuestionStatus.OPEN,
        )
        self.questions[rq.id] = rq
        logger.info("research_question_added", qid=rq.id, question=question)
        return rq

    def resolve_question(self, question_id: str, answer: str, evidence_ids: list[str] | None = None) -> bool:
        rq = self.questions.get(question_id)
        if rq:
            rq.status = ResearchQuestionStatus.RESOLVED
            rq.resolved_answer = answer
            if evidence_ids:
                rq.evidence_ids.extend(evidence_ids)
            logger.info("research_question_resolved", qid=question_id, answer=answer)
            return True
        return False

    # -------------------------------------------------------------
    # Hypothesis Portfolio
    # -------------------------------------------------------------
    def propose_hypothesis(
        self,
        statement: str,
        confidence: float = 0.5,
        assumptions: list[str] | None = None,
        predicted_observations: list[str] | None = None,
    ) -> ResearcherHypothesis:
        hyp = ResearcherHypothesis(
            tenant_id=self.tenant_id,
            engagement_id=self.mission_id,
            statement=statement,
            confidence=confidence,
            assumptions=assumptions or [],
            predicted_observations=predicted_observations or [],
            status=ResearcherHypothesisStatus.ACTIVE,
        )
        self.portfolio.add_hypothesis(hyp)
        logger.info("hypothesis_proposed", hid=hyp.id, statement=statement)
        return hyp

    def confirm_hypothesis(self, hyp_id: str, evidence_id: str) -> bool:
        hyp = self.portfolio.hypotheses.get(hyp_id)
        if hyp:
            hyp.status = ResearcherHypothesisStatus.CONFIRMED
            hyp.confidence = min(1.0, hyp.confidence + 0.35)
            hyp.supporting_evidence.append(evidence_id)
            logger.info("hypothesis_confirmed", hid=hyp_id)
            return True
        return False

    def reject_hypothesis(self, hyp_id: str, contradictory_evidence_id: str) -> bool:
        hyp = self.portfolio.hypotheses.get(hyp_id)
        if hyp:
            hyp.status = ResearcherHypothesisStatus.REJECTED
            hyp.confidence = max(0.0, hyp.confidence - 0.5)
            hyp.contradictory_evidence.append(contradictory_evidence_id)
            logger.info("hypothesis_rejected", hid=hyp_id)
            return True
        return False

    # -------------------------------------------------------------
    # Step Evaluation & Adaptive Feedback
    # -------------------------------------------------------------
    def evaluate_step_outcome(
        self,
        track_id: str,
        action: str,
        expected: str,
        observed: str,
        current_strategy: InvestigationMethod = InvestigationMethod.HTTP_DIFFERENTIAL_PROBE,
    ) -> dict[str, Any]:
        """
        Processes observation, detects anomalies, checks dead-ends, and triggers strategy pivots.
        """
        # 1. Anomaly Evaluation
        anomaly = AnomalyDetector.evaluate(
            expected=expected,
            observed=observed,
            tenant_id=self.tenant_id,
            engagement_id=self.mission_id,
        )
        if anomaly:
            self.anomalies.append(anomaly)

        # 2. Novelty & Information Gain
        if anomaly and not anomaly.is_novel:
            info_gain = 0.0
            success = False
        else:
            info_gain = NoveltyEngine.compute_novelty(observed, self.initial_facts)
            success = (anomaly is not None and anomaly.is_novel) or (anomaly is None and "error" not in observed.lower())

        # 3. Dead-End Check
        self.dead_end_detector.record_attempt(track_id, action, success=success, info_gain=info_gain)
        is_dead_end, dead_end_reason = self.dead_end_detector.is_dead_end(track_id)

        next_strategy = None
        if is_dead_end:
            self.dead_ends.append(f"Track {track_id}: {dead_end_reason}")
            next_strategy = self.strategy_switcher.get_next_strategy(
                track_id=track_id,
                current_strategy=current_strategy,
                reason=dead_end_reason,
            )

        return {
            "anomaly": anomaly,
            "information_gain": info_gain,
            "is_dead_end": is_dead_end,
            "next_strategy": next_strategy,
        }

    # -------------------------------------------------------------
    # Stop Intelligence
    # -------------------------------------------------------------
    def check_stop_condition(
        self,
        budget_used: float,
        max_budget: float,
        time_elapsed_s: float,
        max_time_s: float,
    ) -> tuple[bool, StopReason, str]:
        """
        Evaluates whether the investigation should terminate.
        """
        # 1. Budget exhausted
        if budget_used >= max_budget:
            self.stop_reason = StopReason.BUDGET_EXHAUSTED
            self.stopping_justification = f"Allocated compute budget reached ({budget_used:.1f}/{max_budget:.1f})"
            return True, self.stop_reason, self.stopping_justification

        # 2. Time exhausted
        if time_elapsed_s >= max_time_s:
            self.stop_reason = StopReason.TIME_EXHAUSTED
            self.stopping_justification = f"Maximum mission execution time reached ({time_elapsed_s:.1f}s)"
            return True, self.stop_reason, self.stopping_justification

        # 3. Goal satisfied (all core questions resolved)
        all_resolved = len(self.questions) > 0 and all(
            q.status in (ResearchQuestionStatus.RESOLVED, ResearchQuestionStatus.PARTIALLY_RESOLVED)
            for q in self.questions.values()
        )
        if all_resolved:
            self.stop_reason = StopReason.GOAL_SATISFIED
            self.stopping_justification = "All primary research questions successfully investigated and resolved."
            return True, self.stop_reason, self.stopping_justification

        # 4. Diminishing returns (all tracks hit dead ends and no new leads)
        active_tracks = self.track_manager.get_active_tracks()
        if len(active_tracks) == 0 and len(self.questions) > 0:
            self.stop_reason = StopReason.DIMINISHING_RETURNS
            self.stopping_justification = "All active tracks completed or exhausted with no further high-value leads."
            return True, self.stop_reason, self.stopping_justification

        return False, StopReason.GOAL_SATISFIED, ""

    # -------------------------------------------------------------
    # Report Generation
    # -------------------------------------------------------------
    def generate_report(self) -> ResearchReport:
        conclusions = []
        for hyp in self.portfolio.get_confirmed_hypotheses():
            conclusions.append(f"CONFIRMED: {hyp.statement} (Confidence: {hyp.confidence:.2f})")
        for q in self.questions.values():
            if q.status == ResearchQuestionStatus.RESOLVED and q.resolved_answer:
                conclusions.append(f"RESOLVED [{q.question}]: {q.resolved_answer}")

        report = ResearchReport(
            mission_id=self.mission_id,
            tenant_id=self.tenant_id,
            goal=self.goal,
            initial_facts=list(self.initial_facts),
            questions_investigated=list(self.questions.values()),
            tracks_executed=list(self.track_manager.tracks.values()),
            hypotheses_portfolio=list(self.portfolio.hypotheses.values()),
            anomalies_detected=list(self.anomalies),
            dead_ends_encountered=list(self.dead_ends),
            strategy_changes=list(self.strategy_switcher.switch_history),
            evidence_collected=list(self.evidence_collected),
            stop_reason=self.stop_reason or StopReason.GOAL_SATISFIED,
            stopping_justification=self.stopping_justification or "Research mission concluded.",
            final_conclusions=conclusions,
        )
        return report
