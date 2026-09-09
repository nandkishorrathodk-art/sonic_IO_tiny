"""
SONIC v2 — L4 Procedural Memory & Lessons Ledger
=================================================
Cross-session failure avoidance and procedural mastery.
Records lessons learned from:
- SUCCESS (proven attack path / payload template)
- FAILURE (waf block, payload syntax rejection)
- FALSE_POSITIVE (discredited hypothesis)
- DEAD_END (exhausted strategy requiring pivot)
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sonic.memory.sqlite_graph import _default_db_path


class LessonType(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    FALSE_POSITIVE = "false_positive"
    DEAD_END = "dead_end"


@dataclass
class Lesson:
    lesson_id: str
    lesson_type: LessonType
    target_pattern: str  # e.g., "fastapi_jwt", "nginx_reverse_proxy", "auth_login"
    technique: str
    summary: str
    guidance: str  # Actionable recommendation or avoid-directive
    tenant_id: str = "default"
    times_encountered: int = 1
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class LessonsLedger:
    """Persistent procedural lesson ledger with SQLite write-through."""

    def __init__(self, db_path: str | None = None, persist: bool = True):
        self.persist = persist
        self._db_path = db_path or (os.environ.get("SONIC_MEMORY_DB_PATH") or _default_db_path()) if persist else None
        self._db: sqlite3.Connection | None = None
        self._cache: dict[str, Lesson] = {}
        if persist:
            self._init_db()

    def _init_db(self) -> None:
        if self._db is not None or not self.persist:
            return
        self._db = sqlite3.connect(self._db_path, check_same_thread=False)
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_lessons (
                lesson_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                lesson_type TEXT NOT NULL,
                target_pattern TEXT NOT NULL,
                technique TEXT NOT NULL,
                summary TEXT NOT NULL,
                guidance TEXT NOT NULL,
                times_encountered INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._db.commit()
        cur = self._db.execute(
            "SELECT lesson_id, tenant_id, lesson_type, target_pattern, technique, summary, guidance, times_encountered, created_at FROM memory_lessons"
        )
        for row in cur.fetchall():
            self._cache[row[0]] = Lesson(
                lesson_id=row[0],
                tenant_id=row[1],
                lesson_type=LessonType(row[2]),
                target_pattern=row[3],
                technique=row[4],
                summary=row[5],
                guidance=row[6],
                times_encountered=row[7],
                created_at=row[8],
            )

    def record_lesson(
        self,
        lesson_type: LessonType,
        target_pattern: str,
        technique: str,
        summary: str,
        guidance: str,
        tenant_id: str = "default",
    ) -> Lesson:
        # Check if identical pattern and technique already recorded
        for existing in self._cache.values():
            if (
                existing.tenant_id == tenant_id
                and existing.lesson_type == lesson_type
                and existing.target_pattern == target_pattern
                and existing.technique == technique
            ):
                existing.times_encountered += 1
                if self.persist and self._db:
                    self._db.execute(
                        "UPDATE memory_lessons SET times_encountered = ? WHERE lesson_id = ?",
                        (existing.times_encountered, existing.lesson_id),
                    )
                    self._db.commit()
                return existing

        lid = f"lsn-{uuid.uuid4().hex[:8]}"
        lesson = Lesson(
            lesson_id=lid,
            lesson_type=lesson_type,
            target_pattern=target_pattern,
            technique=technique,
            summary=summary,
            guidance=guidance,
            tenant_id=tenant_id,
        )
        self._cache[lid] = lesson

        if self.persist and self._db:
            self._db.execute(
                """
                INSERT INTO memory_lessons
                (lesson_id, tenant_id, lesson_type, target_pattern, technique, summary, guidance, times_encountered, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lesson.lesson_id,
                    lesson.tenant_id,
                    str(lesson.lesson_type.value),
                    lesson.target_pattern,
                    lesson.technique,
                    lesson.summary,
                    lesson.guidance,
                    lesson.times_encountered,
                    lesson.created_at,
                ),
            )
            self._db.commit()

        return lesson

    def get_lessons_for_target(self, target_pattern: str, tenant_id: str = "default") -> list[Lesson]:
        return [
            lsn for lsn in self._cache.values()
            if lsn.tenant_id == tenant_id and (target_pattern.lower() in lsn.target_pattern.lower() or lsn.target_pattern.lower() in target_pattern.lower())
        ]

    def get_avoid_directives(self, target_pattern: str, tenant_id: str = "default") -> list[str]:
        """Returns directives from past failures and dead ends to prevent loops."""
        lessons = self.get_lessons_for_target(target_pattern, tenant_id=tenant_id)
        return [
            f"[{lsn.lesson_type.upper()}] {lsn.guidance}"
            for lsn in lessons
            if lsn.lesson_type in (LessonType.FAILURE, LessonType.DEAD_END, LessonType.FALSE_POSITIVE)
        ]

    def close(self) -> None:
        if self._db is not None:
            try:
                self._db.close()
            except Exception:
                pass
            self._db = None
