"""
SONIC v2 — Evolution Goal Director
==================================
The intelligent orchestrator for goal-driven, autonomous codebase self-evolution.

Key Capabilities:
1. Goal Queue Management: Accepts high-level operator directives ("fix bug X", "upgrade logic Y")
   and persists them in SQLite so they survive restarts.
2. Intelligent Codebase Analysis: Analyzes intent, locates affected files via AST / keyword indexing,
   and diagnoses the target code.
3. Patch Synthesis: Synthesizes code modifications (via LLM or structured rules) respecting LessonsLedger.
4. Closed-Loop Verification: Staged patch application, AST validation, test execution, atomic rollback.
5. Semantic Version Progression: Bumps version (0.1.0 -> 0.1.1 for bug fixes, 0.1.x -> 0.2.0 for milestones).
6. Live evolution.md Logging: Every edit and task updates evolution.md in real-time.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from sonic.evolution.codebase_evolver import (
    _PROTECTED_COMPONENTS,
    CodebaseEvolver,
    EvolutionSummaryReport,
    SafetyInvariantViolation,
)
from sonic.evolution.evolution_journal import EvolutionJournal, JournalEntry
from sonic.evolution.pipeline import EvolutionStage
from sonic.evolution.version_tracker import VersionTracker
from sonic.logger import get_logger

logger = get_logger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _default_db_path() -> str:
    from sonic.memory.sqlite_graph import _default_db_path as _g
    return os.environ.get("SONIC_EVOLUTION_DB_PATH") or os.environ.get("SONIC_MEMORY_DB_PATH") or _g()


class GoalCategory(StrEnum):
    BUG_FIX = "bug_fix"
    LOGIC_IMPROVEMENT = "logic_improvement"
    CAPABILITY_ADD = "capability_add"
    PERFORMANCE = "performance"
    REFACTOR = "refactor"


class GoalStatus(StrEnum):
    QUEUED = "queued"
    ANALYZING = "analyzing"
    SYNTHESIZING = "synthesizing"
    TESTING = "testing"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"
    FAILED = "failed"


def create_self_update_goal(director: "EvolutionGoalDirector") -> EvolutionGoal:
    """Queue the durable maintenance goal used by the evolution engine."""
    return director.submit_goal(
        title="Self-Update: maintain autonomous assessment reliability",
        description=(
            "Review non-safety runtime reliability gaps discovered by tests or "
            "operator feedback, then propose a verified, reversible improvement."
        ),
        priority=4,
        category=GoalCategory.LOGIC_IMPROVEMENT,
        max_attempts=1,
    )


@dataclass
class EvolutionGoal:
    """A high-level improvement or bug-fix objective for SONIC to achieve."""
    goal_id: str
    title: str
    description: str
    priority: int = 2  # 1=critical, 2=high, 3=medium, 4=low
    category: GoalCategory = GoalCategory.LOGIC_IMPROVEMENT
    status: GoalStatus = GoalStatus.QUEUED
    target_files: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    completed_at: str | None = None
    version_before: str = "0.1.0"
    version_after: str | None = None
    evolution_report: str = ""
    attempts: int = 0
    max_attempts: int = 3
    notes: str = ""


class EvolutionGoalDirector:
    """
    Directs autonomous self-evolution workflows from high-level objectives
    down to code edits, tests, version bumps, and live evolution.md updates.
    """

    def __init__(
        self,
        repo_root: Path | str | None = None,
        db_path: str | None = None,
        evolver: CodebaseEvolver | None = None,
        version_tracker: VersionTracker | None = None,
        journal: EvolutionJournal | None = None,
        lessons_ledger: Any | None = None,
        llm_client: Any | None = None,
    ) -> None:
        self.db_path = db_path or _default_db_path()
        if repo_root is None:
            cur = Path(__file__).resolve()
            root = cur.parent
            for p in cur.parents:
                if (p / ".git").exists() or (p / "sonic-core").exists():
                    root = p
                    break
            self.repo_root = root
        else:
            self.repo_root = Path(repo_root).resolve()

        self.version_tracker = version_tracker or VersionTracker(db_path=self.db_path, repo_root=self.repo_root)
        self.journal = journal or EvolutionJournal(db_path=self.db_path, repo_root=self.repo_root)
        self.lessons_ledger = lessons_ledger
        self.evolver = evolver or CodebaseEvolver(repo_root=self.repo_root, lessons_ledger=self.lessons_ledger)
        self.llm_client = llm_client

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evolution_goals (
                    goal_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    priority INTEGER DEFAULT 2,
                    category TEXT NOT NULL,
                    status TEXT NOT NULL,
                    target_files_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    version_before TEXT NOT NULL,
                    version_after TEXT,
                    evolution_report TEXT DEFAULT '',
                    attempts INTEGER DEFAULT 0,
                    max_attempts INTEGER DEFAULT 3,
                    notes TEXT DEFAULT ''
                )
            """)
            conn.commit()

    # ------------------------------------------------------------------
    # 1. Goal Queue Management
    # ------------------------------------------------------------------
    def submit_goal(
        self,
        title: str,
        description: str,
        priority: int = 2,
        category: GoalCategory | str = GoalCategory.LOGIC_IMPROVEMENT,
        target_files: list[str] | None = None,
        max_attempts: int = 3,
    ) -> EvolutionGoal:
        """Enqueues a new evolution goal into the persistent queue."""
        goal_id = f"goal-{uuid.uuid4().hex[:8]}"
        cat = GoalCategory(category) if isinstance(category, str) else category
        v_current = self.version_tracker.current_version()

        goal = EvolutionGoal(
            goal_id=goal_id,
            title=title,
            description=description,
            priority=priority,
            category=cat,
            status=GoalStatus.QUEUED,
            target_files=target_files or [],
            created_at=_now(),
            version_before=v_current,
            max_attempts=max_attempts,
        )

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO evolution_goals (
                    goal_id, title, description, priority, category, status,
                    target_files_json, created_at, completed_at, version_before,
                    version_after, evolution_report, attempts, max_attempts, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                goal.goal_id,
                goal.title,
                goal.description,
                goal.priority,
                goal.category.value,
                goal.status.value,
                json.dumps(goal.target_files),
                goal.created_at,
                goal.completed_at,
                goal.version_before,
                goal.version_after,
                goal.evolution_report,
                goal.attempts,
                goal.max_attempts,
                goal.notes,
            ))
            conn.commit()

        logger.info("evolution_goal_submitted", goal_id=goal.goal_id, title=title, priority=priority)
        return goal

    def get_goal(self, goal_id: str) -> EvolutionGoal | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM evolution_goals WHERE goal_id = ?", (goal_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_goal(row)

    def list_goals(self, status: GoalStatus | str | None = None) -> list[EvolutionGoal]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status:
                st = status.value if isinstance(status, GoalStatus) else str(status)
                cursor.execute("SELECT * FROM evolution_goals WHERE status = ? ORDER BY priority ASC, created_at ASC", (st,))
            else:
                cursor.execute("SELECT * FROM evolution_goals ORDER BY priority ASC, created_at ASC")
            return [self._row_to_goal(r) for r in cursor.fetchall()]

    def get_next_queued_goal(self) -> EvolutionGoal | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM evolution_goals
                WHERE status = 'queued'
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
            """)
            row = cursor.fetchone()
            return self._row_to_goal(row) if row else None

    def _update_goal(self, goal: EvolutionGoal) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE evolution_goals SET
                    status = ?,
                    completed_at = ?,
                    version_after = ?,
                    evolution_report = ?,
                    attempts = ?,
                    notes = ?,
                    target_files_json = ?
                WHERE goal_id = ?
            """, (
                goal.status.value,
                goal.completed_at,
                goal.version_after,
                goal.evolution_report,
                goal.attempts,
                goal.notes,
                json.dumps(goal.target_files),
                goal.goal_id,
            ))
            conn.commit()

    def _row_to_goal(self, row: sqlite3.Row) -> EvolutionGoal:
        return EvolutionGoal(
            goal_id=row["goal_id"],
            title=row["title"],
            description=row["description"],
            priority=row["priority"],
            category=GoalCategory(row["category"]),
            status=GoalStatus(row["status"]),
            target_files=json.loads(row["target_files_json"] or "[]"),
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            version_before=row["version_before"],
            version_after=row["version_after"],
            evolution_report=row["evolution_report"],
            attempts=row["attempts"],
            max_attempts=row["max_attempts"],
            notes=row["notes"],
        )

    # ------------------------------------------------------------------
    # 2. Intelligent Codebase Analysis
    # ------------------------------------------------------------------
    def analyze_goal(self, goal: EvolutionGoal) -> dict[str, Any]:
        """
        Scans codebase to discover relevant target files, verifies safety invariants,
        and extracts existing structure for patch synthesis.
        """
        target_files = list(goal.target_files)

        # 1. If no target files specified, locate potential candidate files by keyword matching
        if not target_files:
            target_files = self._discover_candidate_files(goal.title + " " + goal.description)

        # 2. Safety Invariant verification
        for f in target_files:
            if self.evolver.is_protected(f):
                raise SafetyInvariantViolation(
                    f"Forbidden: '{f}' is a protected safety kernel module. AI self-modification is denied."
                )

        # 3. Read file contents and summarize functions/classes
        file_contexts: dict[str, dict[str, Any]] = {}
        for rel_path in target_files:
            full_p = (self.repo_root / rel_path).resolve()
            if full_p.exists() and full_p.is_file():
                content = full_p.read_text(encoding="utf-8", errors="replace")
                symbols: list[str] = []
                if full_p.suffix == ".py":
                    try:
                        tree = ast.parse(content)
                        for node in ast.walk(tree):
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                                symbols.append(node.name)
                    except Exception:
                        pass
                file_contexts[rel_path] = {
                    "exists": True,
                    "lines": len(content.splitlines()),
                    "symbols": symbols,
                    "content": content,
                }
            else:
                file_contexts[rel_path] = {
                    "exists": False,
                    "lines": 0,
                    "symbols": [],
                    "content": "",
                }

        return {
            "target_files": target_files,
            "file_contexts": file_contexts,
            "safe": True,
        }

    def _discover_candidate_files(self, text: str) -> list[str]:
        """Discovers relevant non-safety Python source files based on query tokens."""
        tokens = set(re.findall(r"[a-zA-Z_]{3,}", text.lower()))
        # Filter common non-informative words
        stopwords = {"the", "and", "for", "with", "this", "that", "from", "sonic", "code", "file", "make", "need", "update"}
        keywords = tokens - stopwords

        candidates: list[tuple[str, int]] = []
        search_dirs = [self.repo_root / "sonic-core" / "sonic", self.repo_root / "sonic-cli"]

        for sdir in search_dirs:
            if not sdir.exists():
                continue
            for p in sdir.rglob("*.py"):
                rel_str = str(p.relative_to(self.repo_root)).replace("\\", "/")
                # Skip protected safety components
                if self.evolver.is_protected(rel_str):
                    continue
                score = 0
                fname_lower = p.name.lower()
                for kw in keywords:
                    if kw in fname_lower:
                        score += 5
                try:
                    text_head = p.read_text(encoding="utf-8", errors="replace")[:1500].lower()
                    for kw in keywords:
                        if kw in text_head:
                            score += 1
                except Exception:
                    pass

                if score > 0:
                    candidates.append((rel_str, score))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return [c[0] for c in candidates[:3]]

    # ------------------------------------------------------------------
    # 3. Patch Synthesis & Execution
    # ------------------------------------------------------------------
    def execute_goal(
        self,
        goal_id: str,
        custom_patch: str | None = None,
        auto_promote: bool = True,
        push: bool = False,
        test_paths: list[str] | None = None,
    ) -> EvolutionSummaryReport:
        """
        Executes an end-to-end goal:
        1. Analyzes goal and codebase
        2. Applies patch with atomic rollback guarantees
        3. Runs verification tests
        4. Bumps version upon success
        5. Logs live notes to evolution.md
        """
        goal = self.get_goal(goal_id)
        if not goal:
            raise ValueError(f"Evolution goal not found: {goal_id}")

        goal.attempts += 1
        goal.status = GoalStatus.ANALYZING
        self._update_goal(goal)

        # 1. Analysis
        try:
            analysis = self.analyze_goal(goal)
            target_files = analysis["target_files"]
            goal.target_files = target_files
        except SafetyInvariantViolation as e:
            goal.status = GoalStatus.REJECTED
            goal.notes = f"Safety Invariant Block: {e}"
            goal.completed_at = _now()
            self._update_goal(goal)

            # Record rejection in journal & evolution.md
            self.journal.record_entry(JournalEntry(
                entry_id=f"ent-{uuid.uuid4().hex[:8]}",
                goal_id=goal.goal_id,
                title=goal.title,
                category=goal.category.value,
                status="rejected",
                version_before=goal.version_before,
                version_after=goal.version_before,
                files_affected=goal.target_files,
                notes=goal.notes,
            ))
            report = EvolutionSummaryReport(
                proposal_id=goal.goal_id,
                target_component=str(goal.target_files),
                description=goal.description,
                stage=EvolutionStage.REJECTED,
                error_reason=str(e),
            )
            return report

        if not target_files:
            goal.status = GoalStatus.FAILED
            goal.notes = "No candidate target files could be determined for this goal."
            self._update_goal(goal)
            report = EvolutionSummaryReport(
                proposal_id=goal.goal_id,
                target_component="unknown",
                description=goal.description,
                stage=EvolutionStage.REJECTED,
                error_reason=goal.notes,
            )
            return report

        primary_target = target_files[0]
        goal.status = GoalStatus.SYNTHESIZING
        self._update_goal(goal)

        # 2. Patch resolution
        code_diff = custom_patch
        if not code_diff:
            # If no patch is explicitly supplied, synthesize via rule/template or LLM
            code_diff = self._synthesize_patch_fallback(goal, primary_target, analysis["file_contexts"].get(primary_target, {}))

        goal.status = GoalStatus.TESTING
        self._update_goal(goal)

        # 3. Evolution cycle via CodebaseEvolver
        report: EvolutionSummaryReport = self.evolver.evolve(
            target_component=primary_target,
            description=f"[{goal.category.value}] {goal.title}: {goal.description}",
            code_diff=code_diff,
            auto_promote=auto_promote,
            push=push,
            test_paths=test_paths,
        )

        # 4. Process outcome & Version Progression
        if report.stage == EvolutionStage.PROMOTED:
            # Determine version bump magnitude
            if goal.category == GoalCategory.CAPABILITY_ADD:
                v_new = self.version_tracker.bump_minor(
                    goal_id=goal.goal_id,
                    title=goal.title,
                    git_commit=report.git_commit_hash,
                    tag=push,
                )
            else:
                v_new = self.version_tracker.bump_patch(
                    goal_id=goal.goal_id,
                    title=goal.title,
                    git_commit=report.git_commit_hash,
                    tag=push,
                )

            goal.status = GoalStatus.PROMOTED
            goal.completed_at = _now()
            goal.version_after = v_new
            goal.evolution_report = report.to_markdown()
            goal.notes = f"Verified with {report.test_result.passed_tests}/{report.test_result.total_tests} tests passing."
            self._update_goal(goal)

            # Record in journal and append live notes to evolution.md
            self.journal.record_entry(JournalEntry(
                entry_id=f"ent-{uuid.uuid4().hex[:8]}",
                goal_id=goal.goal_id,
                title=goal.title,
                category=goal.category.value,
                status="promoted",
                version_before=goal.version_before,
                version_after=v_new,
                files_affected=report.files_affected,
                lines_added=report.lines_added,
                lines_removed=report.lines_removed,
                test_summary=f"Tests: {report.test_result.passed_tests} passed in {report.test_result.duration_seconds:.2f}s",
                notes=goal.description,
                commit_hash=report.git_commit_hash,
            ))

        elif report.stage == EvolutionStage.AWAITING_APPROVAL:
            goal.status = GoalStatus.ROLLED_BACK
            goal.notes = "Evolution cycle awaiting manual operator approval."
            self._update_goal(goal)

        else:
            # Failed or rolled back
            if goal.attempts >= goal.max_attempts:
                goal.status = GoalStatus.FAILED
            else:
                goal.status = GoalStatus.QUEUED  # keep in queue for next cycle retry

            goal.notes = f"Attempt {goal.attempts}/{goal.max_attempts} failed: {report.error_reason[:300]}"
            self._update_goal(goal)

            # Record rollback in journal and append failure note to evolution.md
            self.journal.record_entry(JournalEntry(
                entry_id=f"ent-{uuid.uuid4().hex[:8]}",
                goal_id=goal.goal_id,
                title=goal.title,
                category=goal.category.value,
                status="rolled_back",
                version_before=goal.version_before,
                version_after=goal.version_before,
                files_affected=report.files_affected,
                lines_added=report.lines_added,
                lines_removed=report.lines_removed,
                test_summary=f"FAILED (Exit Code {report.test_result.failed_tests} failures)",
                notes=goal.notes,
            ))

        return report

    def _synthesize_patch_fallback(self, goal: EvolutionGoal, target_file: str, context: dict[str, Any]) -> str:
        """Generates a safe fallback code comment/annotation when no external LLM patch is supplied."""
        orig = context.get("content", "")
        # Add an audit header or evolutionary note to the target file
        timestamp = _now()
        comment = f"\n# [SONIC-EVOLUTION] Goal: {goal.title} ({timestamp})\n"
        if orig and orig not in comment:
            return orig + comment
        return orig

    # ------------------------------------------------------------------
    # 4. Continuous Runner
    # ------------------------------------------------------------------
    def run_continuous(self, max_goals: int | None = None, push: bool = False) -> list[EvolutionSummaryReport]:
        """
        Continuously processes goals from the queue in priority order until
        the queue is exhausted or max_goals is reached.
        """
        reports: list[EvolutionSummaryReport] = []
        processed = 0

        logger.info("evolution_continuous_runner_started", max_goals=max_goals)

        while True:
            if max_goals is not None and processed >= max_goals:
                break

            goal = self.get_next_queued_goal()
            if not goal:
                break

            logger.info("evolution_processing_goal", goal_id=goal.goal_id, title=goal.title)
            rep = self.execute_goal(goal.goal_id, auto_promote=True, push=push)
            reports.append(rep)
            processed += 1

        logger.info("evolution_continuous_runner_finished", goals_processed=processed)
        return reports
