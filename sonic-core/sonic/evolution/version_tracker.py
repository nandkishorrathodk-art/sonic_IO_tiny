"""
SONIC v2 — Evolution Version Tracker
=====================================
Maintains persistent semantic versioning (Major.Minor.Patch) across evolution cycles.
Every successful capability upgrade, bug fix, or milestone bumps the version,
records the change in SQLite, and optionally creates a git tag.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
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
class VersionRecord:
    """A record of a version milestone achieved by self-evolution."""
    version: str
    goal_id: str
    title: str
    bump_type: str  # "patch", "minor", "major", "initial"
    timestamp: str = field(default_factory=_now)
    git_commit: str = ""
    git_tag: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class VersionTracker:
    """
    Manages semantic version progression for the self-evolving codebase.
    Default initial version is 0.1.0.
    """

    INITIAL_VERSION = "0.1.0"

    def __init__(self, db_path: str | None = None, repo_root: Path | str | None = None) -> None:
        self.db_path = db_path or _default_db_path()
        self.repo_root = Path(repo_root).resolve() if repo_root else Path.cwd()
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
                CREATE TABLE IF NOT EXISTS evolution_versions (
                    version TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    bump_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    git_commit TEXT DEFAULT '',
                    git_tag TEXT DEFAULT '',
                    metadata_json TEXT DEFAULT '{}'
                )
            """)
            conn.commit()

            # Ensure baseline version exists
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM evolution_versions")
            if cursor.fetchone()[0] == 0:
                self._record_version_direct(
                    conn,
                    VersionRecord(
                        version=self.INITIAL_VERSION,
                        goal_id="init",
                        title="SONIC Initial Autonomous Baseline",
                        bump_type="initial",
                        timestamp=_now(),
                        git_tag=f"v{self.INITIAL_VERSION}",
                    )
                )

    def _record_version_direct(self, conn: sqlite3.Connection, record: VersionRecord) -> None:
        conn.execute("""
            INSERT OR REPLACE INTO evolution_versions (
                version, goal_id, title, bump_type, timestamp, git_commit, git_tag, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.version,
            record.goal_id,
            record.title,
            record.bump_type,
            record.timestamp,
            record.git_commit,
            record.git_tag,
            json.dumps(record.metadata),
        ))
        conn.commit()

    @staticmethod
    def parse_semver(ver: str) -> tuple[int, int, int]:
        clean = ver.lstrip("v")
        m = re.match(r"^(\d+)\.(\d+)\.(\d+)", clean)
        if not m:
            return (0, 1, 0)
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))

    @staticmethod
    def format_semver(major: int, minor: int, patch: int) -> str:
        return f"{major}.{minor}.{patch}"

    def current_version(self) -> str:
        """Returns the latest active version string (e.g. '0.1.0')."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT version FROM evolution_versions ORDER BY rowid DESC LIMIT 1")
            row = cursor.fetchone()
            return row["version"] if row else self.INITIAL_VERSION

    def get_latest_record(self) -> VersionRecord | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM evolution_versions ORDER BY rowid DESC LIMIT 1")
            row = cursor.fetchone()
            if not row:
                return None
            return VersionRecord(
                version=row["version"],
                goal_id=row["goal_id"],
                title=row["title"],
                bump_type=row["bump_type"],
                timestamp=row["timestamp"],
                git_commit=row["git_commit"],
                git_tag=row["git_tag"],
                metadata=json.loads(row["metadata_json"] or "{}"),
            )

    def history(self) -> list[VersionRecord]:
        """Returns chronological history of all version advancements."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM evolution_versions ORDER BY rowid ASC")
            records = []
            for row in cursor.fetchall():
                records.append(VersionRecord(
                    version=row["version"],
                    goal_id=row["goal_id"],
                    title=row["title"],
                    bump_type=row["bump_type"],
                    timestamp=row["timestamp"],
                    git_commit=row["git_commit"],
                    git_tag=row["git_tag"],
                    metadata=json.loads(row["metadata_json"] or "{}"),
                ))
            return records

    def bump_patch(
        self,
        goal_id: str,
        title: str,
        git_commit: str = "",
        tag: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Increments patch version (e.g. 0.1.0 -> 0.1.1). Used for bug fixes & minor tweaks."""
        major, minor, patch = self.parse_semver(self.current_version())
        new_version = self.format_semver(major, minor, patch + 1)
        return self._apply_bump(new_version, goal_id, title, "patch", git_commit, tag, metadata)

    def bump_minor(
        self,
        goal_id: str,
        title: str,
        git_commit: str = "",
        tag: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Increments minor version (e.g. 0.1.x -> 0.2.0). Used for major capabilities & milestones."""
        major, minor, _ = self.parse_semver(self.current_version())
        new_version = self.format_semver(major, minor + 1, 0)
        return self._apply_bump(new_version, goal_id, title, "minor", git_commit, tag, metadata)

    def bump_major(
        self,
        goal_id: str,
        title: str,
        git_commit: str = "",
        tag: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Increments major version (e.g. 0.x -> 1.0.0). Used for foundational breakthroughs."""
        major, _, _ = self.parse_semver(self.current_version())
        new_version = self.format_semver(major + 1, 0, 0)
        return self._apply_bump(new_version, goal_id, title, "major", git_commit, tag, metadata)

    def _apply_bump(
        self,
        new_version: str,
        goal_id: str,
        title: str,
        bump_type: str,
        git_commit: str = "",
        tag: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        git_tag_name = f"v{new_version}" if tag else ""
        if tag and git_commit:
            self.create_git_tag(git_tag_name, git_commit, f"Release {git_tag_name}: {title}")

        record = VersionRecord(
            version=new_version,
            goal_id=goal_id,
            title=title,
            bump_type=bump_type,
            timestamp=_now(),
            git_commit=git_commit,
            git_tag=git_tag_name,
            metadata=metadata or {},
        )

        with self._get_connection() as conn:
            self._record_version_direct(conn, record)

        logger.info(
            "evolution_version_bumped",
            version=new_version,
            goal_id=goal_id,
            bump_type=bump_type,
            title=title,
        )
        return new_version

    def create_git_tag(self, tag_name: str, commit_hash: str, message: str) -> bool:
        """Creates an annotated git tag at the given commit hash."""
        try:
            cmd = ["git", "tag", "-a", tag_name, commit_hash, "-m", message]
            res = subprocess.run(
                cmd,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            return res.returncode == 0
        except Exception as e:
            logger.warning("evolution_git_tag_failed", tag=tag_name, error=str(e))
            return False

