"""
SONIC v2 — L2 Episodic Memory
==============================
Cross-session engagement history that records past targets, attack trails,
what succeeded, and what failed.
Persists write-through to SQLite so memories survive process restarts.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sonic.memory.sqlite_graph import _default_db_path


@dataclass
class Episode:
    """A record of a completed or past engagement/mission."""
    episode_id: str
    target: str
    tenant_id: str = "default"
    goal: str = ""
    summary: str = ""
    findings_count: int = 0
    hypotheses_tested: int = 0
    what_worked: list[str] = field(default_factory=list)
    what_failed: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class EpisodicMemory:
    """Persistent store for cross-session engagement episodes."""

    def __init__(self, db_path: str | None = None, persist: bool = True):
        self.persist = persist
        self._db_path = db_path or (os.environ.get("SONIC_MEMORY_DB_PATH") or _default_db_path()) if persist else None
        self._db: sqlite3.Connection | None = None
        self._cache: dict[str, Episode] = {}
        if persist:
            self._init_db()

    def _init_db(self) -> None:
        if self._db is not None or not self.persist:
            return
        self._db = sqlite3.connect(self._db_path, check_same_thread=False)
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_episodes (
                episode_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                target TEXT NOT NULL,
                goal TEXT NOT NULL,
                summary TEXT NOT NULL,
                findings_count INTEGER NOT NULL,
                hypotheses_tested INTEGER NOT NULL,
                what_worked_json TEXT NOT NULL,
                what_failed_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._db.commit()
        # Pre-populate cache
        cur = self._db.execute(
            "SELECT episode_id, tenant_id, target, goal, summary, findings_count, hypotheses_tested, what_worked_json, what_failed_json, created_at FROM memory_episodes"
        )
        for row in cur.fetchall():
            self._cache[row[0]] = Episode(
                episode_id=row[0],
                tenant_id=row[1],
                target=row[2],
                goal=row[3],
                summary=row[4],
                findings_count=row[5],
                hypotheses_tested=row[6],
                what_worked=json.loads(row[7]),
                what_failed=json.loads(row[8]),
                created_at=row[9],
            )

    def record_episode(
        self,
        target: str,
        goal: str,
        summary: str,
        findings_count: int = 0,
        hypotheses_tested: int = 0,
        what_worked: list[str] | None = None,
        what_failed: list[str] | None = None,
        tenant_id: str = "default",
        episode_id: str | None = None,
    ) -> Episode:
        eid = episode_id or f"ep-{uuid.uuid4().hex[:8]}"
        ep = Episode(
            episode_id=eid,
            target=target,
            tenant_id=tenant_id,
            goal=goal,
            summary=summary,
            findings_count=findings_count,
            hypotheses_tested=hypotheses_tested,
            what_worked=what_worked or [],
            what_failed=what_failed or [],
        )
        self._cache[eid] = ep

        if self.persist and self._db:
            self._db.execute(
                """
                INSERT OR REPLACE INTO memory_episodes
                (episode_id, tenant_id, target, goal, summary, findings_count, hypotheses_tested, what_worked_json, what_failed_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ep.episode_id,
                    ep.tenant_id,
                    ep.target,
                    ep.goal,
                    ep.summary,
                    ep.findings_count,
                    ep.hypotheses_tested,
                    json.dumps(ep.what_worked),
                    json.dumps(ep.what_failed),
                    ep.created_at,
                ),
            )
            self._db.commit()

        return ep

    def get_by_target(self, target: str, tenant_id: str = "default") -> list[Episode]:
        return [ep for ep in self._cache.values() if ep.tenant_id == tenant_id and ep.target == target]

    def get_all(self, tenant_id: str = "default") -> list[Episode]:
        return [ep for ep in self._cache.values() if ep.tenant_id == tenant_id]

    def close(self) -> None:
        if self._db is not None:
            try:
                self._db.close()
            except Exception:
                pass
            self._db = None
