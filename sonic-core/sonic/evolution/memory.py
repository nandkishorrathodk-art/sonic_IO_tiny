"""
SONIC-REDA — Evolution Memory Store (Phase 8)
==============================================
Persistent repository indexing past evolution experiments, benchmark comparisons,
promotion decisions, and derived lessons to prevent duplicate failures.

Items are written through to an ``evolution_items`` table in the SONIC SQLite DB
so evolution lessons survive a backend restart.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional

from sonic.evolution.models import EvolutionMemoryItem
from sonic.logger import get_logger

logger = get_logger(__name__)


def _default_db_path() -> str:
    from sonic.memory.sqlite_graph import _default_db_path as _g
    return os.environ.get("SONIC_MEMORY_DB_PATH") or _g()


class EvolutionMemoryStore:
    """
    Persistent store for self-evolution history and lessons.

    The in-memory ``_items`` list and ``_fingerprints`` set are read caches
    populated on init from SQLite and kept in sync on every write-through.
    """

    def __init__(self, db_path: Optional[str] = None, persist: bool = True):
        self._items: list[EvolutionMemoryItem] = []
        self._fingerprints: set[str] = set()
        self.persist = persist
        self._db_path = db_path or (_default_db_path() if persist else None)
        self._db: Optional[sqlite3.Connection] = None
        if persist:
            self._open_db()

    def _open_db(self) -> None:
        if self._db is not None or not self.persist:
            return
        self._db = sqlite3.connect(self._db_path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS evolution_items ("
            "id TEXT PRIMARY KEY, fingerprint TEXT, item_json TEXT NOT NULL)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_evo_fp ON evolution_items(fingerprint)"
        )
        self._db.commit()
        for item_id, fp, item_json in self._db.execute(
            "SELECT id, fingerprint, item_json FROM evolution_items"
        ).fetchall():
            try:
                item = EvolutionMemoryItem.model_validate_json(item_json)
            except Exception:
                continue
            self._items.append(item)
            if fp:
                self._fingerprints.add(fp)

    def record_experiment(self, item: EvolutionMemoryItem) -> None:
        """Store an experiment record and index its fingerprint (write-through)."""
        compute_fp = getattr(item, "compute_fingerprint", None)
        if callable(compute_fp) and not item.fingerprint:
            compute_fp()
        self._items.append(item)
        if item.fingerprint:
            self._fingerprints.add(item.fingerprint)
        if self._db is not None:
            self._db.execute(
                "INSERT OR REPLACE INTO evolution_items (id, fingerprint, item_json) VALUES (?, ?, ?)",
                (item.id, item.fingerprint, item.model_dump_json()),
            )
            self._db.commit()
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
