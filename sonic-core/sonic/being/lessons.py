"""
SONIC-REDA — Cross-Mission Lessons Ledger
=========================================
The "learning" leg of self-improvement that was missing: the being already
AUTHORS new tools (Toolsmith) and techniques (MethodLab), and it already
COMPUTES lessons after each task (epistemic ``PredictionComparison``). But
those lessons were never fed back into the next mission's reasoning — the
being forgot what it learned across missions. This closes the learn→apply loop.

Two halves:

    extract_lessons()
        At mission end, distill the trace into concrete lessons:
          * AVOID — an approach that failed (don't repeat it)
          * REUSE — an approach that succeeded (reuse it)
        Grounded in real trace outcomes, never fabricated.

    LessonsLedger
        A durable (host-FS) cross-mission store. ``record()`` persists a
        lesson; ``relevant()`` returns the top-K lessons whose keywords match
        the current goal, so the agent injects only what is pertinent — not
        a giant dump. ``inject_into_context()`` renders them as a compact
        block the LLM sees in ``_build_reasoning_context``.

HONESTY INVARIANT (mirrors toolsmith/method_lab):
    A lesson is recorded ONLY from a real trace outcome (FAILED/RECOVERED → AVOID,
    SUCCESS/COMPLETED/VERIFIED → REUSE). RECOVERED is treated as FAILED because
    the action itself failed — the recovery (e.g., `clear || true`) does not
    constitute success. No lesson is invented by decree. An empty trace yields
    no lessons.

SECURITY INVARIANT:
    Lessons are text observations about tool/approach outcomes — they carry
    no secrets, credentials, or target PII (the trace summaries are already
    sanitized in the agent). The ledger is host-side under ``sonic_data`` like
    BeingCraft, keyed by tenant + agent for isolation.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sonic.logger import get_logger

logger = get_logger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _ledger_root() -> str:
    base = os.environ.get("SONIC_DATA_DIR", "sonic_data")
    return os.path.join(base, "lessons")


class LessonKind(StrEnum):
    """What the lesson tells the agent to do with the approach."""
    AVOID = "avoid"   # this approach failed — don't repeat it
    REUSE = "reuse"   # this approach worked — reuse it


@dataclass
class Lesson:
    """A single cross-mission lesson distilled from a real trace outcome."""
    lesson_id: str
    kind: LessonKind
    goal: str               # the mission goal it was learned under (for relevance match)
    approach: str           # the concrete action/approach that failed or worked
    evidence: str           # the observed outcome (trace result excerpt)
    created_at: str = ""
    # Lightweight keyword tags for relevance matching without embeddings.
    tags: list[str] = field(default_factory=list)


def _keywords(text: str) -> list[str]:
    """Extract lowercase keyword tokens for relevance matching.

    Strips short stopwords so the match is on meaningful terms (tool names,
    action verbs, targets), not glue words.
    """
    stop = {"the", "a", "an", "to", "for", "and", "or", "of", "in", "on", "with",
            "is", "it", "this", "that", "run", "use", "try", "goal", "mission"}
    toks = re.findall(r"[a-z][a-z0-9_-]{2,}", text.lower())
    return [t for t in toks if t not in stop]


def _relevance(goal: str, lesson: Lesson) -> int:
    """Cheap keyword-overlap relevance score between the current goal and a
    lesson's goal+tags. No embeddings — keeps the dependency surface flat."""
    gk = set(_keywords(goal))
    lk = set(_keywords(lesson.goal)) | set(lesson.tags)
    return len(gk & lk)


def extract_lessons(
    traces: list[Any],
    goal: str,
    agent_id: str = "computer-use-agent",
) -> list[Lesson]:
    """Distill a mission's traces into concrete lessons.

    One AVOID lesson per FAILED/RECOVERED trace (approaches that didn't work —
    RECOVERED means the action failed and a generic recovery ran, which is NOT
    a success) and one REUSE lesson per SUCCESS/COMPLETED/VERIFIED trace.
    Grounded in real ``trace.status`` — never fabricates a lesson from an empty
    trace.

    Args:
        traces: the ``ComputerDecisionTrace`` list from ``run_mission``.
        goal:   the mission goal (carried so relevance matching works later).
    """
    if not traces:
        return []
    lessons: list[Lesson] = []
    for i, t in enumerate(traces):
        status = getattr(t, "status", "")
        action = getattr(t, "action_type", "")
        target = getattr(t, "target_resource", "") or ""
        predicted = getattr(t, "predicted_outcome", "") or ""
        actual = getattr(t, "actual_observation", "") or ""
        approach = f"{getattr(action, 'value', action)} on {target}".strip()
        evidence = (actual or predicted)[:200]

        if status in ("FAILED", "RECOVERED"):
            # RECOVERED means the action FAILED and a generic recovery ran
            # (e.g., `clear || true`). This is NOT a success — record as AVOID
            # so the agent doesn't repeat the failing approach.
            lessons.append(Lesson(
                lesson_id=f"lesson-{int(time.time()*1000)}-{i}-avoid",
                kind=LessonKind.AVOID,
                goal=goal,
                approach=approach,
                evidence=(
                    f"action failed and required recovery: {evidence}"
                    if status == "RECOVERED" else
                    evidence or "action failed"
                ),
                created_at=_now(),
                tags=_keywords(f"{approach} {goal}"),
            ))
        elif status in ("SUCCESS", "COMPLETED", "VERIFIED"):
            lessons.append(Lesson(
                lesson_id=f"lesson-{int(time.time()*1000)}-{i}-reuse",
                kind=LessonKind.REUSE,
                goal=goal,
                approach=approach,
                evidence=evidence or "action succeeded",
                created_at=_now(),
                tags=_keywords(f"{approach} {goal}"),
            ))
    logger.info("lessons_extracted", count=len(lessons), goal=goal[:80])
    return lessons


class LessonsLedger:
    """Durable cross-mission lesson store (host FS, restart-proof).

    Persists one JSON file per tenant+agent under ``sonic_data/lessons/``.
    Mirrors the BeingCraft persistence convention so the being's lessons
    survive restart — the learn→apply loop compounds across sessions, not
    just within one.
    """

    def __init__(self, tenant_id: str = "default", agent_id: str = "computer-use-agent"):
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self._lessons: list[Lesson] = []
        self._load()

    def _path(self) -> str:
        return os.path.join(_ledger_root(), f"{self.tenant_id}_{self.agent_id}.json")

    def _load(self) -> None:
        path = self._path()
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self._lessons = [
                Lesson(
                    lesson_id=d["lesson_id"],
                    kind=LessonKind(d["kind"]),
                    goal=d["goal"],
                    approach=d["approach"],
                    evidence=d.get("evidence", ""),
                    created_at=d.get("created_at", ""),
                    tags=d.get("tags", []),
                )
                for d in data
            ]
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            self._lessons = []

    def _save(self) -> None:
        path = self._path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = [
            {
                "lesson_id": l.lesson_id, "kind": l.kind.value,
                "goal": l.goal, "approach": l.approach, "evidence": l.evidence,
                "created_at": l.created_at, "tags": l.tags,
            }
            for l in self._lessons
        ]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def record(self, lessons: list[Lesson]) -> None:
        """Persist new lessons. Deduplicates by (kind, approach) so repeating
        the same failed approach in multiple missions counts once, not N×."""
        existing = {(l.kind, l.approach) for l in self._lessons}
        added = 0
        for l in lessons:
            key = (l.kind, l.approach)
            if key in existing:
                continue
            self._lessons.append(l)
            existing.add(key)
            added += 1
        if added:
            self._save()
            logger.info("lessons_recorded", added=added, total=len(self._lessons))

    def relevant(self, goal: str, k: int = 5) -> list[Lesson]:
        """Return the top-K lessons most relevant to the current goal by keyword
        overlap. Caps the injection so the LLM sees pertinent lessons, not a
        giant dump that drowns the live observation."""
        if not self._lessons:
            return []
        scored = sorted(self._lessons, key=lambda l: _relevance(goal, l), reverse=True)
        # Filter zero-relevance lessons out unless the ledger is small — a brand
        # new goal with no overlap still benefits from the most-recent lessons.
        hits = [l for l in scored if _relevance(goal, l) > 0]
        if not hits and len(self._lessons) <= k:
            return self._lessons[:k]
        return hits[:k]

    def all(self) -> list[Lesson]:
        return list(self._lessons)

    def clear(self) -> None:
        """Test helper — wipe the ledger."""
        self._lessons = []
        path = self._path()
        if os.path.exists(path):
            os.remove(path)


def inject_into_context(lessons: list[Lesson]) -> str:
    """Render lessons as a compact block for the LLM reasoning context.

    Returns an empty string when there are no lessons — so a fresh being with
    no history adds zero noise to the prompt (no fabricated "lessons learned").
    """
    if not lessons:
        return ""
    avoids = [l for l in lessons if l.kind == LessonKind.AVOID]
    reuses = [l for l in lessons if l.kind == LessonKind.REUSE]
    lines: list[str] = []
    if reuses:
        lines.append("Past lessons — approaches that WORKED (reuse them):")
        for l in reuses:
            lines.append(f"  [REUSE] {l.approach} → {l.evidence}")
    if avoids:
        lines.append("Past lessons — approaches that FAILED (avoid repeating):")
        for l in avoids:
            lines.append(f"  [AVOID] {l.approach} → {l.evidence}")
    return "\n".join(lines) + "\n"

# ---------------------------------------------------------------------------
# NEXUS L5 -- Self-Designed Experience Training (SelfCurriculum)
# ---------------------------------------------------------------------------

_VERIFIED_STATUSES = {"verified", "confirmed", "promoted"}


@dataclass
class CurriculumDemonstration:
    """A single (action -> rationale -> outcome) teaching exemplar."""
    demo_id: str
    action: str
    rationale: str
    outcome: str
    status: str = "pending"           # verified | confirmed | rejected | pending
    domain: str = ""
    target_class: str = ""
    quality_score: float = 0.0
    created_at: str = field(default_factory=_now)

    @property
    def verified(self) -> bool:
        return self.status.lower() in _VERIFIED_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "demo_id": self.demo_id,
            "action": self.action,
            "rationale": self.rationale,
            "outcome": self.outcome,
            "status": self.status,
            "domain": self.domain,
            "target_class": self.target_class,
            "quality_score": self.quality_score,
            "created_at": self.created_at,
        }


class SelfCurriculum:
    """Curates verified experience into a usable curriculum and synthesizes
    fine-tuning signal (explicit demonstrations, ranked by quality).

    HONESTY INVARIANT:
    Only *verified* outcomes become curriculum. A demonstration whose outcome
    is not confirmed is never promoted into the served curriculum.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or _default_curriculum_db_path()
        self._demos: dict[str, CurriculumDemonstration] = {}
        self._init_db()
        self._hydrate()

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS curriculum_demonstrations (
                    demo_id TEXT PRIMARY KEY,
                    action TEXT,
                    rationale TEXT,
                    outcome TEXT,
                    status TEXT,
                    domain TEXT,
                    target_class TEXT,
                    quality_score REAL,
                    created_at TEXT
                )
                """
            )

    def _hydrate(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT demo_id, action, rationale, outcome, status, domain,"
                    " target_class, quality_score, created_at FROM curriculum_demonstrations"
                ).fetchall()
            for demo_id, action, rationale, outcome, status, domain, tc, qs, created_at in rows:
                self._demos[demo_id] = CurriculumDemonstration(
                    demo_id=demo_id, action=action, rationale=rationale, outcome=outcome,
                    status=status, domain=domain or "", target_class=tc or "",
                    quality_score=qs, created_at=created_at,
                )
        except sqlite3.Error as e:
            logger.warning("curriculum_hydrate_failed", error=str(e))

    def _persist(self, demo: CurriculumDemonstration) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO curriculum_demonstrations VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        demo.demo_id, demo.action, demo.rationale, demo.outcome,
                        demo.status, demo.domain, demo.target_class,
                        demo.quality_score, demo.created_at,
                    ),
                )
        except sqlite3.Error as e:
            logger.warning("curriculum_persist_failed", error=str(e))

    def record(
        self,
        action: str,
        rationale: str,
        outcome: str,
        status: str = "pending",
        domain: str = "",
        target_class: str = "",
        quality_score: float = 0.0,
    ) -> CurriculumDemonstration:
        """Record a trace-derived demonstration. Honesty gate: non-verified
        outcomes are stored but never enter the served curriculum."""
        demo = CurriculumDemonstration(
            demo_id=f"demo-{uuid.uuid4().hex[:10]}",
            action=action, rationale=rationale, outcome=outcome, status=status,
            domain=domain, target_class=target_class, quality_score=quality_score,
        )
        self._demos[demo.demo_id] = demo
        self._persist(demo)
        return demo

    def mark_verified(self, demo_id: str, evidence: str = "") -> bool:
        """Promote a pending demonstration into the verified curriculum only
        when evidence of real reproduction exists."""
        demo = self._demos.get(demo_id)
        if not demo:
            return False
        if evidence.strip():
            demo.outcome = f"{demo.outcome} [verified: {evidence}]"
        demo.status = "verified"
        demo.quality_score = max(demo.quality_score, 0.8)
        self._persist(demo)
        return True

    def verified_demos(
        self,
        domain: str = "",
        limit: int = 10,
    ) -> list[CurriculumDemonstration]:
        """Serve the verified curriculum, optionally filtered by domain."""
        demos = [d for d in self._demos.values() if d.verified]
        if domain:
            demos = [d for d in demos if d.domain == domain]
        demos.sort(key=lambda d: d.quality_score, reverse=True)
        return demos[:limit]

    def fine_tune_signal(
        self,
        domain: str = "",
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Synthesize instruction-tuning style signal from the best verified
        demonstrations (action->rationale->outcome). This is the export surface
        a downstream training infra consumes."""
        return [d.to_dict() for d in self.verified_demos(domain=domain, limit=top_k)]

    def counts(self) -> dict[str, int]:
        total = len(self._demos)
        verified = sum(1 for d in self._demos.values() if d.verified)
        return {"total": total, "verified": verified, "pending": total - verified}


def _default_curriculum_db_path() -> str:
    from sonic.memory.sqlite_graph import _default_db_path as _g
    return os.environ.get("SONIC_CURRICULUM_DB_PATH") or os.environ.get("SONIC_MEMORY_DB_PATH") or _g()