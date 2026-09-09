"""
SONIC v2 — Decision Engine & Dead-End Pivot System
===================================================
Prevents infinite repetition and aimless looping.
Treats 'DEAD END' as a first-class epistemic state and mandates pivots.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sonic.logger import get_logger

logger = get_logger(__name__)


class DecisionAction(StrEnum):
    PROCEED = "proceed"
    PIVOT = "pivot"
    PAUSE_REVIEW = "pause_review"
    TERMINATE = "terminate"


@dataclass
class DecisionTrace:
    action: DecisionAction
    target_asset: str
    rationale: str
    strategy: str
    alternative_strategies: list[str] = field(default_factory=list)
    consecutive_failures: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class DecisionEngine:
    """Monitors mission trajectory, identifies dead-ends, and orchestrates pivots."""

    def __init__(self, failure_threshold_for_pivot: int = 3):
        self.failure_threshold = failure_threshold_for_pivot
        # Tracks failures per (asset, strategy)
        self._failure_tallies: dict[str, int] = {}
        self._dead_ends: set[str] = set()
        self._traces: list[DecisionTrace] = []

    def _key(self, asset: str, strategy: str) -> str:
        return f"{asset}::{strategy}"

    def record_success(self, asset: str, strategy: str) -> None:
        key = self._key(asset, strategy)
        self._failure_tallies[key] = 0

    def record_failure(self, asset: str, strategy: str, reason: str = "") -> DecisionTrace:
        """Records an experiment failure and assesses whether to pivot."""
        key = self._key(asset, strategy)
        current_count = self._failure_tallies.get(key, 0) + 1
        self._failure_tallies[key] = current_count

        if current_count >= self.failure_threshold:
            self._dead_ends.add(key)
            logger.warning(
                "decision_engine_dead_end_reached",
                asset=asset,
                strategy=strategy,
                failures=current_count,
            )
            trace = DecisionTrace(
                action=DecisionAction.PIVOT,
                target_asset=asset,
                rationale=f"Strategy '{strategy}' failed {current_count} consecutive times on asset '{asset}'. Declaring DEAD END and pivoting.",
                strategy=strategy,
                consecutive_failures=current_count,
                alternative_strategies=["recon_deep", "alternate_endpoint", "privilege_pivot"],
            )
        else:
            trace = DecisionTrace(
                action=DecisionAction.PROCEED,
                target_asset=asset,
                rationale=f"Failure count ({current_count}/{self.failure_threshold}) within tolerance; continuing investigation.",
                strategy=strategy,
                consecutive_failures=current_count,
            )

        self._traces.append(trace)
        return trace

    def is_dead_end(self, asset: str, strategy: str) -> bool:
        return self._key(asset, strategy) in self._dead_ends

    def get_traces(self) -> list[DecisionTrace]:
        return list(self._traces)
