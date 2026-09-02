"""
SONIC-REDA — Anomaly, Novelty & Dead-End Detection Engine (Phase 12)
=====================================================================
Identifies discrepancies between expected predictions and actual outcomes,
detects novel serendipitous leads, and flags dead-end investigations.
"""

from __future__ import annotations

import difflib
from typing import Any

from sonic.logger import get_logger
from sonic.researcher.models import (
    AnomalyRecord,
    AnomalyType,
    ResearchLead,
    ResearchLeadStatus,
)

logger = get_logger(__name__)


class AnomalyDetector:
    """
    Evaluates observed outcomes against predicted expectations.
    """

    @classmethod
    def evaluate(
        cls,
        expected: str,
        observed: str,
        tenant_id: str,
        engagement_id: str,
    ) -> AnomalyRecord | None:
        """
        Compare expected prediction with actual observation.
        Returns AnomalyRecord and creates a ResearchLead if significant.
        """
        exp_clean = expected.strip().lower()
        obs_clean = observed.strip().lower()

        # If identical or near-identical, no anomaly
        similarity = difflib.SequenceMatcher(None, exp_clean, obs_clean).ratio()
        if similarity > 0.85:
            return None

        # Classify anomaly type
        if "error" in obs_clean or "connection refused" in obs_clean or "timeout" in obs_clean:
            anomaly_type = AnomalyType.TECHNICAL_FAILURE
            is_novel = False
        elif "429" in obs_clean or "too many requests" in obs_clean or "rate limit" in obs_clean or "404" in obs_clean or "not found" in obs_clean:
            anomaly_type = AnomalyType.KNOWN_VARIATION
            is_novel = False
        elif "forbidden" in obs_clean and "200" in exp_clean:
            anomaly_type = AnomalyType.CONTRADICTION
            is_novel = True
        elif "admin" in obs_clean or "token" in obs_clean or "leak" in obs_clean or "unauthorized" in obs_clean or ("200" in obs_clean and "401" in exp_clean):
            anomaly_type = AnomalyType.NOVEL_ANOMALY
            is_novel = True
        else:
            anomaly_type = AnomalyType.INVALID_PREDICTION
            is_novel = True

        # Generate lead if novel or contradictory
        lead_id = None
        if is_novel:
            lead = ResearchLead(
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                observation=observed[:200],
                why_interesting=f"Prediction deviation ({anomaly_type.value}): Expected '{expected[:60]}...' but got '{observed[:60]}...'",
                expected_value=0.85 if anomaly_type == AnomalyType.NOVEL_ANOMALY else 0.70,
                priority=0.85,
                status=ResearchLeadStatus.NEW,
            )
            lead_id = lead.id
            logger.info("anomaly_lead_generated", lead_id=lead.id, anomaly_type=anomaly_type.value)

        record = AnomalyRecord(
            expected=expected,
            observed=observed,
            anomaly_type=anomaly_type,
            is_novel=is_novel,
            created_lead_id=lead_id,
            confidence_deviation=round(1.0 - similarity, 4),
        )
        return record


class NoveltyEngine:
    """
    Evaluates whether an observation introduces genuinely new information.
    """

    @classmethod
    def compute_novelty(cls, observation: str, known_facts: list[str]) -> float:
        if not known_facts:
            return 1.0

        obs_tokens = set(observation.lower().split())
        if not obs_tokens:
            return 0.0

        max_overlap = 0.0
        for fact in known_facts:
            fact_tokens = set(fact.lower().split())
            if not fact_tokens:
                continue
            intersection = obs_tokens.intersection(fact_tokens)
            overlap = len(intersection) / len(obs_tokens)
            if overlap > max_overlap:
                max_overlap = overlap

        novelty = max(0.0, min(1.0, 1.0 - max_overlap))
        return round(novelty, 4)


class DeadEndDetector:
    """
    Monitors investigative tracks for repetitive failures and diminishing returns.
    """

    def __init__(self, failure_threshold: int = 3, min_info_gain: float = 0.05):
        self.failure_threshold = failure_threshold
        self.min_info_gain = min_info_gain
        self._track_history: dict[str, list[dict[str, Any]]] = {}

    def record_attempt(self, track_id: str, action: str, success: bool, info_gain: float) -> None:
        if track_id not in self._track_history:
            self._track_history[track_id] = []
        self._track_history[track_id].append({
            "action": action,
            "success": success,
            "info_gain": info_gain,
        })

    def is_dead_end(self, track_id: str) -> tuple[bool, str]:
        """
        Determines whether a track has reached a dead end.
        Returns: (is_dead_end, reason)
        """
        history = self._track_history.get(track_id, [])
        if len(history) < self.failure_threshold:
            return False, ""

        recent = history[-self.failure_threshold:]

        # 1. Check for consecutive failures
        all_failed = all(not r["success"] for r in recent)
        if all_failed:
            return True, f"Track {track_id} experienced {self.failure_threshold} consecutive failed experiments"

        # 2. Check for repeated identical actions with zero info gain
        actions = [r["action"] for r in recent]
        if len(set(actions)) == 1 and all(r["info_gain"] < self.min_info_gain for r in recent):
            return True, f"Track {track_id} repeated action '{actions[0]}' without information gain"

        # 3. Check for diminishing returns across recent steps
        avg_info = sum(r["info_gain"] for r in recent) / len(recent)
        if avg_info < self.min_info_gain:
            return True, f"Track {track_id} average information gain ({avg_info:.3f}) fell below threshold ({self.min_info_gain})"

        return False, ""
