"""
SONIC v2 — Evolution Journal & Live `evolution.md` Logger
==========================================================
Durable audit trail and real-time evolution notes logger.

USER INVARIANT:
"and jo bhi file edit karta hai or koi bhi task uske notes ek evolution.md main save hota rehta hai"

Every file edit, task, bug fix, or capability upgrade automatically writes detailed
markdown audit notes to `evolution.md` at the repository root, as well as preserving
structured telemetry in SQLite for changelog generation and fitness tracking.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sonic.logger import get_logger

logger = get_logger(__name__)


def _default_db_path() -> str:
    from sonic.memory.sqlite_graph import _default_db_path as _g
    return os.environ.get("SONIC_EVOLUTION_DB_PATH") or os.environ.get("SONIC_MEMORY_DB_PATH") or _g()


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class JournalEntry:
    """A structured log entry for an evolution task or codebase modification."""
    entry_id: str
    goal_id: str
    title: str
    category: str
    status: str  # "promoted", "rolled_back", "rejected", "manual"
    version_before: str
    version_after: str
    files_affected: list[str] = field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0
    test_summary: str = ""
    notes: str = ""
    commit_hash: str = ""
    timestamp: str = field(default_factory=_now)


class EvolutionJournal:
    """
    Manages the persistent evolution audit journal in SQLite and appends
    human-readable notes to `evolution.md` at the repository root.
    """

    def __init__(
        self,
        db_path: str | None = None,
        repo_root: Path | str | None = None,
        markdown_filename: str = "evolution.md",
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

        self.evolution_md_path = self.repo_root / markdown_filename
        self._init_db()
        self._ensure_evolution_md_header()

    def _get_connection(self) -> sqlite3.Connection:
        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evolution_journal (
                    entry_id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version_before TEXT NOT NULL,
                    version_after TEXT NOT NULL,
                    files_json TEXT NOT NULL,
                    lines_added INTEGER DEFAULT 0,
                    lines_removed INTEGER DEFAULT 0,
                    test_summary TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    commit_hash TEXT DEFAULT '',
                    timestamp TEXT NOT NULL
                )
            """)
            conn.commit()

    def _ensure_evolution_md_header(self) -> None:
        """Creates the initial evolution.md file if it doesn't already exist."""
        if not self.evolution_md_path.exists():
            header = [
                "# 🧬 SONIC Continuous Codebase Evolution & Task Notes",
                "",
                "> This document is automatically maintained by the SONIC Self-Evolution Engine.",
                "> Every file modification, bug fix, logical upgrade, and autonomous goal logs its audit trail here.",
                "",
                "---",
                "",
            ]
            try:
                self.evolution_md_path.write_text("\n".join(header), encoding="utf-8")
            except Exception as e:
                logger.warning("evolution_md_header_init_failed", error=str(e))

    def record_entry(self, entry: JournalEntry) -> None:
        """Saves a journal entry to SQLite and appends live notes to evolution.md."""
        # 1. Save to SQLite
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO evolution_journal (
                    entry_id, goal_id, title, category, status, version_before, version_after,
                    files_json, lines_added, lines_removed, test_summary, notes, commit_hash, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.entry_id,
                entry.goal_id,
                entry.title,
                entry.category,
                entry.status,
                entry.version_before,
                entry.version_after,
                json.dumps(entry.files_affected),
                entry.lines_added,
                entry.lines_removed,
                entry.test_summary,
                entry.notes,
                entry.commit_hash,
                entry.timestamp,
            ))
            conn.commit()

        # 2. Append live note to evolution.md
        self.append_to_markdown(entry)

    def append_to_markdown(self, entry: JournalEntry) -> None:
        """Appends a structured markdown note entry to evolution.md."""
        self._ensure_evolution_md_header()

        status_emoji = {
            "promoted": "🟢 PROMOTED (AUTO-COMMITTED)",
            "rolled_back": "🔴 ROLLED BACK (TESTS FAILED)",
            "rejected": "⛔ REJECTED (SAFETY/AST VIOLATION)",
            "manual": "🟡 MANUAL APPROVAL REQUIRED",
        }.get(entry.status.lower(), f"⚪ {entry.status.upper()}")

        files_formatted = ", ".join(f"`{f}`" for f in entry.files_affected) if entry.files_affected else "None"

        note_block = [
            f"## [{entry.timestamp}] {entry.title}",
            "",
            f"- **Goal ID:** `{entry.goal_id}`",
            f"- **Status:** {status_emoji}",
            f"- **Version:** `{entry.version_before}` ➔ `{entry.version_after}`",
            f"- **Category:** `{entry.category}`",
            f"- **Files Edited:** {files_formatted}",
            f"- **Diff Metrics:** `+{entry.lines_added}` lines, `-{entry.lines_removed}` lines",
        ]

        if entry.commit_hash:
            note_block.append(f"- **Git Commit:** `{entry.commit_hash}`")

        if entry.test_summary:
            note_block.append(f"- **Verification:** {entry.test_summary}")

        if entry.notes:
            note_block.extend([
                "",
                "### Notes & Rationale",
                f"> {entry.notes}",
            ])

        note_block.extend(["", "---", ""])

        try:
            with open(self.evolution_md_path, "a", encoding="utf-8") as f:
                f.write("\n".join(note_block))
            logger.info("evolution_md_appended", goal_id=entry.goal_id, path=str(self.evolution_md_path))
        except Exception as e:
            logger.error("evolution_md_append_failed", error=str(e), file=str(self.evolution_md_path))

    def get_entries(self, limit: int = 50) -> list[JournalEntry]:
        """Retrieves recent journal entries ordered by timestamp descending."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM evolution_journal ORDER BY rowid DESC LIMIT ?
            """, (limit,))
            entries = []
            for row in cursor.fetchall():
                entries.append(JournalEntry(
                    entry_id=row["entry_id"],
                    goal_id=row["goal_id"],
                    title=row["title"],
                    category=row["category"],
                    status=row["status"],
                    version_before=row["version_before"],
                    version_after=row["version_after"],
                    files_affected=json.loads(row["files_json"] or "[]"),
                    lines_added=row["lines_added"],
                    lines_removed=row["lines_removed"],
                    test_summary=row["test_summary"],
                    notes=row["notes"],
                    commit_hash=row["commit_hash"],
                    timestamp=row["timestamp"],
                ))
            return entries

    def fitness_metrics(self) -> dict[str, Any]:
        """Calculates self-evolution fitness scores (success rate, promotions, rollbacks)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM evolution_journal")
            total = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM evolution_journal WHERE status = 'promoted'")
            promoted = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM evolution_journal WHERE status = 'rolled_back'")
            rolled_back = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM evolution_journal WHERE status = 'rejected'")
            rejected = cursor.fetchone()[0]

            success_rate = (promoted / total) if total > 0 else 0.0

            return {
                "total_cycles": total,
                "promoted": promoted,
                "rolled_back": rolled_back,
                "rejected": rejected,
                "success_rate": round(success_rate, 4),
            }

    def generate_changelog(self, from_version: str | None = None, to_version: str | None = None) -> str:
        """Generates a clean Markdown changelog between versions."""
        entries = self.get_entries(limit=200)
        # Filter promoted only
        promoted = [e for e in entries if e.status.lower() == "promoted"]

        lines = [
            f"# 📜 SONIC Evolution Changelog {f'({from_version} ➔ {to_version})' if from_version else ''}",
            "",
        ]

        for e in promoted:
            lines.append(f"### Version `{e.version_after}` — {e.title}")
            lines.append(f"- **Timestamp:** {e.timestamp}")
            lines.append(f"- **Category:** `{e.category}`")
            lines.append(f"- **Files:** {', '.join(f'`{f}`' for f in e.files_affected)}")
            lines.append(f"- **Impact:** `+{e.lines_added} / -{e.lines_removed}` lines")
            if e.commit_hash:
                lines.append(f"- **Commit:** `{e.commit_hash}`")
            if e.notes:
                lines.append(f"- **Summary:** {e.notes}")
            lines.append("")

        return "\n".join(lines)

