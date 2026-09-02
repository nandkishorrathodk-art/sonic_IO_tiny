"""
SONIC-REDA — Investigation Track Manager & Prioritizer (Phase 12)
===================================================================
Manages independent parallel investigation tracks, priority scoring,
resource slot allocations, and lifecycle state transitions.
"""

from __future__ import annotations

from collections.abc import Callable

from sonic.logger import get_logger
from sonic.researcher.models import InvestigationTrack, TrackStatus

logger = get_logger(__name__)

# Replaceable scoring function type
TrackScorer = Callable[[InvestigationTrack], float]


def default_track_scorer(track: InvestigationTrack) -> float:
    """
    Deterministic multi-factor track scoring:
    score = (expected_value * 1.5 + (1.0 - track.risk) * 0.5) / (track.cost + track.risk + 0.2)
    """
    numerator = (track.expected_value * 1.5) + ((1.0 - track.risk) * 0.5)
    denominator = track.cost + track.risk + 0.2
    return max(0.01, round(numerator / denominator, 4))


class TrackPrioritizer:
    """
    Evaluates and ranks candidate investigation tracks.
    """

    def __init__(self, scorer: TrackScorer | None = None):
        self.scorer = scorer or default_track_scorer

    def score_track(self, track: InvestigationTrack) -> float:
        return self.scorer(track)

    def rank_tracks(self, tracks: list[InvestigationTrack]) -> list[InvestigationTrack]:
        for t in tracks:
            t.priority = self.score_track(t)
        return sorted(tracks, key=lambda t: t.priority, reverse=True)


class InvestigationTrackManager:
    """
    Manages portfolio of active, paused, and completed investigation tracks.
    """

    def __init__(self, prioritizer: TrackPrioritizer | None = None):
        self.tracks: dict[str, InvestigationTrack] = {}
        self.prioritizer = prioritizer or TrackPrioritizer()

    def create_track(
        self,
        mission_id: str,
        tenant_id: str,
        objective: str,
        questions: list[str] | None = None,
        hypotheses: list[str] | None = None,
        expected_value: float = 0.7,
        cost: float = 0.2,
        risk: float = 0.1,
    ) -> InvestigationTrack:
        track = InvestigationTrack(
            mission_id=mission_id,
            tenant_id=tenant_id,
            objective=objective,
            questions=questions or [],
            hypotheses=hypotheses or [],
            expected_value=expected_value,
            cost=cost,
            risk=risk,
            status=TrackStatus.ACTIVE,
        )
        track.priority = self.prioritizer.score_track(track)
        self.tracks[track.id] = track
        logger.info("investigation_track_created", track_id=track.id, objective=objective, priority=track.priority)
        return track

    def get_track(self, track_id: str) -> InvestigationTrack | None:
        return self.tracks.get(track_id)

    def get_active_tracks(self) -> list[InvestigationTrack]:
        return [t for t in self.tracks.values() if t.status == TrackStatus.ACTIVE]

    def reprioritize_tracks(self) -> list[InvestigationTrack]:
        """Recalculate priorities and return sorted list of active tracks."""
        active = self.get_active_tracks()
        ranked = self.prioritizer.rank_tracks(active)
        return ranked

    def pause_track(self, track_id: str, reason: str = "") -> bool:
        track = self.tracks.get(track_id)
        if track and track.status == TrackStatus.ACTIVE:
            track.status = TrackStatus.PAUSED
            logger.info("investigation_track_paused", track_id=track_id, reason=reason)
            return True
        return False

    def resume_track(self, track_id: str) -> bool:
        track = self.tracks.get(track_id)
        if track and track.status == TrackStatus.PAUSED:
            track.status = TrackStatus.ACTIVE
            logger.info("investigation_track_resumed", track_id=track_id)
            return True
        return False

    def close_track(self, track_id: str, status: TrackStatus = TrackStatus.COMPLETED) -> bool:
        track = self.tracks.get(track_id)
        if track:
            track.status = status
            logger.info("investigation_track_closed", track_id=track_id, status=status.value)
            return True
        return False

    def allocate_resources(self, total_slots: int = 4) -> dict[str, int]:
        """
        Dynamically allocate concurrency execution slots to active tracks.
        Ensures highest-value tracks receive proportionally more slots without total starvation.
        """
        active = self.reprioritize_tracks()
        if not active:
            return {}

        total_priority = sum(t.priority for t in active)
        allocations: dict[str, int] = {}
        remaining_slots = total_slots

        for idx, track in enumerate(active):
            if idx == len(active) - 1:
                # Give remaining slots to last track (minimum 1)
                assigned = max(1, remaining_slots)
            else:
                share = track.priority / total_priority if total_priority > 0 else 1.0 / len(active)
                assigned = max(1, round(share * total_slots))
                assigned = min(assigned, remaining_slots - (len(active) - idx - 1))

            track.allocated_slots = assigned
            allocations[track.id] = assigned
            remaining_slots = max(0, remaining_slots - assigned)

        return allocations
