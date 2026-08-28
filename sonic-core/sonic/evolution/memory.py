"""
SONIC-REDA — Evolution Memory Store (Phase 8)
==============================================
Persistent repository indexing past evolution experiments, benchmark comparisons,
promotion decisions, and derived lessons to prevent duplicate failures.
"""

from __future__ import annotations

from typing import Optional
from sonic.evolution.models import EvolutionMemoryItem
from sonic.logger import get_logger

logger = get_logger(__name__)


class EvolutionMemoryStore:
    """
    In-memory and persistent store for self-evolution history and lessons.
    """

    def __init__(self):
        self._items: list[EvolutionMemoryItem] = []
        self._fingerprints: set[str] = set()

    def record_experiment(self, item: EvolutionMemoryItem) -> None:
        """Store an experiment record and index its fingerprint."""
        self._items.append(item)
        if item.fingerprint:
            self._fingerprints.add(item.fingerprint)
        logger.info(
            "evolution_memory_recorded",
            memory_id=item.id,
            candidate=item.candidate_version,
            decision=item.decision,
        )

    def is_duplicate(self, fingerprint: str) -> bool:
        """Check if an identical evolution attempt already exists in memory."""
        return bool(fingerprint and fingerprint in self._fingerprints)

    def get_lessons_for_problem(self, problem_keyword: str) -> list[str]:
        """Retrieve relevant lessons from past experiments addressing similar problems."""
        lessons = []
        kw = problem_keyword.lower()
        for it in self._items:
            if kw in it.problem.lower() and it.lesson:
                lessons.append(f"[{it.candidate_version}] {it.lesson}")
        return lessons

    def get_all_history(self) -> list[EvolutionMemoryItem]:
        """Return full evolution timeline."""
        return list(self._items)
