"""
Tests for Phase 39: Advanced Autonomous Self-Evolution Director
================================================================
Verifies:
1. Persistent Semantic Version Tracking (0.1.0 -> 0.1.1 -> 0.2.0).
2. Live evolution.md logging for all tasks, edits, and goals.
3. Goal Queue Management & Priority Dispatch.
4. Fail-closed Safety Invariant rejection on protected components.
5. End-to-end goal execution with automated testing, version bump, and journal entry.
6. Continuous goal queue runner.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from sonic.evolution.codebase_evolver import CodebaseEvolver, SafetyInvariantViolation
from sonic.evolution.engine import EvolutionEngine
from sonic.evolution.evolution_journal import EvolutionJournal, JournalEntry
from sonic.evolution.goal_director import (
    EvolutionGoalDirector,
    GoalCategory,
    GoalStatus,
)
from sonic.evolution.pipeline import EvolutionStage
from sonic.evolution.version_tracker import VersionTracker


@pytest.fixture
def temp_evolution_env(tmp_path: Path):
    """Provides an isolated temp workspace with custom DB and repo root."""
    db_path = str(tmp_path / "test_evolution.db")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "sonic-core" / "sonic").mkdir(parents=True)

    version_tracker = VersionTracker(db_path=db_path, repo_root=repo_root)
    journal = EvolutionJournal(db_path=db_path, repo_root=repo_root)
    evolver = CodebaseEvolver(repo_root=repo_root)
    director = EvolutionGoalDirector(
        repo_root=repo_root,
        db_path=db_path,
        evolver=evolver,
        version_tracker=version_tracker,
        journal=journal,
    )
    return {
        "tmp_path": tmp_path,
        "db_path": db_path,
        "repo_root": repo_root,
        "version_tracker": version_tracker,
        "journal": journal,
        "evolver": evolver,
        "director": director,
    }


def test_version_tracker_initial_and_semantic_bumps(temp_evolution_env):
    """Verifies baseline 0.1.0 and semantic bumps across patch, minor, major."""
    vt: VersionTracker = temp_evolution_env["version_tracker"]
    db_path = temp_evolution_env["db_path"]
    repo_root = temp_evolution_env["repo_root"]

    assert vt.current_version() == "0.1.0"

    # 1. Bump patch (bug fix)
    v1 = vt.bump_patch(goal_id="g-1", title="Fix regex boundary")
    assert v1 == "0.1.1"
    assert vt.current_version() == "0.1.1"

    # 2. Bump minor (new capability / milestone)
    v2 = vt.bump_minor(goal_id="g-2", title="Add Ghidra decompilation support")
    assert v2 == "0.2.0"
    assert vt.current_version() == "0.2.0"

    # 3. Bump major (breakthrough milestone)
    v3 = vt.bump_major(goal_id="g-3", title="Autonomous AI Pentest Breakthrough")
    assert v3 == "1.0.0"
    assert vt.current_version() == "1.0.0"

    # 4. Persistence check across re-instantiation
    vt_new = VersionTracker(db_path=db_path, repo_root=repo_root)
    assert vt_new.current_version() == "1.0.0"
    hist = vt_new.history()
    assert len(hist) == 4  # init, patch, minor, major
    assert [h.version for h in hist] == ["0.1.0", "0.1.1", "0.2.0", "1.0.0"]


def test_evolution_journal_and_evolution_md_live_logging(temp_evolution_env):
    """Verifies that entries are saved in SQLite and appended to evolution.md."""
    journal: EvolutionJournal = temp_evolution_env["journal"]
    repo_root: Path = temp_evolution_env["repo_root"]

    # evolution.md should be created with header
    md_file = repo_root / "evolution.md"
    assert md_file.exists()
    assert "# 🧬 SONIC Continuous Codebase Evolution" in md_file.read_text(encoding="utf-8")

    # Record an entry
    entry = JournalEntry(
        entry_id="ent-101",
        goal_id="goal-101",
        title="Upgrade DOM Parser Speed",
        category="performance",
        status="promoted",
        version_before="0.1.0",
        version_after="0.1.1",
        files_affected=["sonic-core/sonic/research/dom.py"],
        lines_added=45,
        lines_removed=10,
        test_summary="Passed: 5/5 tests",
        notes="Replaced linear scan with binary lookup",
        commit_hash="abc1234",
    )
    journal.record_entry(entry)

    # Check evolution.md contains live notes
    content = md_file.read_text(encoding="utf-8")
    assert "Upgrade DOM Parser Speed" in content
    assert "`0.1.0` ➔ `0.1.1`" in content
    assert "Replaced linear scan with binary lookup" in content
    assert "sonic-core/sonic/research/dom.py" in content
    assert "`+45` lines, `-10` lines" in content

    # Check SQLite retrieval & fitness metrics
    entries = journal.get_entries()
    assert len(entries) == 1
    assert entries[0].title == "Upgrade DOM Parser Speed"

    metrics = journal.fitness_metrics()
    assert metrics["total_cycles"] == 1
    assert metrics["promoted"] == 1
    assert metrics["success_rate"] == 1.0


def test_goal_director_submission_and_priority_queue(temp_evolution_env):
    """Verifies priority-ordered goal queue dispatch (P1 before P3)."""
    director: EvolutionGoalDirector = temp_evolution_env["director"]

    g_low = director.submit_goal(title="Low priority cosmetic fix", description="Formatting", priority=4)
    g_crit = director.submit_goal(title="Critical session crash", description="Fix NoneType exception", priority=1)
    g_med = director.submit_goal(title="Medium feature add", description="Telemetry", priority=2)

    all_queued = director.list_goals(status=GoalStatus.QUEUED)
    assert len(all_queued) == 3

    # Priority 1 should be dispatched first
    next_goal = director.get_next_queued_goal()
    assert next_goal is not None
    assert next_goal.goal_id == g_crit.goal_id
    assert next_goal.priority == 1


def test_goal_director_safety_invariant_rejection(temp_evolution_env):
    """Verifies fail-closed rejection when a goal targets protected safety kernel components."""
    director: EvolutionGoalDirector = temp_evolution_env["director"]
    journal: EvolutionJournal = temp_evolution_env["journal"]

    goal = director.submit_goal(
        title="Tamper with Safety Kernel",
        description="Try to bypass egress checks",
        priority=1,
        target_files=["sonic-core/sonic/safety/kernel.py"],
    )

    report = director.execute_goal(goal.goal_id)
    assert report.stage == EvolutionStage.REJECTED

    updated = director.get_goal(goal.goal_id)
    assert updated.status == GoalStatus.REJECTED
    assert "Safety Invariant Block" in updated.notes

    # Verify that rejection was logged in evolution.md
    md_content = journal.evolution_md_path.read_text(encoding="utf-8")
    assert "REJECTED" in md_content
    assert "Tamper with Safety Kernel" in md_content


def test_goal_director_successful_execution_and_version_bump(temp_evolution_env):
    """Verifies full execution loop: patch staging, version bump, and evolution.md logging."""
    director: EvolutionGoalDirector = temp_evolution_env["director"]
    version_tracker: VersionTracker = temp_evolution_env["version_tracker"]
    journal: EvolutionJournal = temp_evolution_env["journal"]
    repo_root: Path = temp_evolution_env["repo_root"]

    # Create an evolvable target file
    target_rel = "sonic-core/sonic/tools/sample_worker.py"
    target_abs = repo_root / target_rel
    target_abs.parent.mkdir(parents=True, exist_ok=True)
    target_abs.write_text("def worker_task():\n    return 42\n", encoding="utf-8")

    # Submit a bug fix goal
    goal = director.submit_goal(
        title="Enhance worker return payload",
        description="Worker task should return dict with status",
        category=GoalCategory.BUG_FIX,
        target_files=[target_rel],
    )

    new_code = "def worker_task():\n    return {'status': 'ok', 'val': 42}\n"

    # Execute goal with mock test pass
    import unittest.mock as mock
    with mock.patch.object(director.evolver, "run_tests") as mock_tests, \
         mock.patch.object(director.evolver, "run_security_regression") as mock_sec:
        from sonic.evolution.codebase_evolver import TestExecutionResult
        mock_tests.return_value = TestExecutionResult(passed=True, total_tests=1, passed_tests=1, duration_seconds=0.1)
        mock_sec.return_value = True

        rep = director.execute_goal(goal.goal_id, custom_patch=new_code, auto_promote=True)

        assert rep.stage == EvolutionStage.PROMOTED
        # Category was bug_fix -> version bumped from 0.1.0 to 0.1.1
        assert version_tracker.current_version() == "0.1.1"

        # Code on disk was updated
        assert "{'status': 'ok', 'val': 42}" in target_abs.read_text(encoding="utf-8")

        # Goal is updated to PROMOTED
        g_done = director.get_goal(goal.goal_id)
        assert g_done.status == GoalStatus.PROMOTED
        assert g_done.version_after == "0.1.1"

        # evolution.md contains the task notes
        md_text = journal.evolution_md_path.read_text(encoding="utf-8")
        assert "Enhance worker return payload" in md_text
        assert "`0.1.0` ➔ `0.1.1`" in md_text


def test_goal_director_capability_add_bumps_minor_version(temp_evolution_env):
    """Verifies that CAPABILITY_ADD bumps the minor version (e.g. 0.1.0 -> 0.2.0)."""
    director: EvolutionGoalDirector = temp_evolution_env["director"]
    version_tracker: VersionTracker = temp_evolution_env["version_tracker"]
    repo_root: Path = temp_evolution_env["repo_root"]

    target_rel = "sonic-core/sonic/research/analyzer.py"
    target_abs = repo_root / target_rel
    target_abs.parent.mkdir(parents=True, exist_ok=True)
    target_abs.write_text("class Analyzer:\n    pass\n", encoding="utf-8")

    goal = director.submit_goal(
        title="Add Fast Pattern Matching Engine",
        description="Introduces Aho-Corasick automaton for rapid secret scanning",
        category=GoalCategory.CAPABILITY_ADD,
        target_files=[target_rel],
    )

    new_code = "class Analyzer:\n    def scan_fast(self): return True\n"

    import unittest.mock as mock
    with mock.patch.object(director.evolver, "run_tests") as mock_tests, \
         mock.patch.object(director.evolver, "run_security_regression") as mock_sec:
        from sonic.evolution.codebase_evolver import TestExecutionResult
        mock_tests.return_value = TestExecutionResult(passed=True, total_tests=3, passed_tests=3, duration_seconds=0.2)
        mock_sec.return_value = True

        rep = director.execute_goal(goal.goal_id, custom_patch=new_code, auto_promote=True)
        assert rep.stage == EvolutionStage.PROMOTED
        # Minor bump: 0.1.0 -> 0.2.0
        assert version_tracker.current_version() == "0.2.0"


def test_evolution_engine_unified_facade(temp_evolution_env):
    """Verifies that EvolutionEngine cleanly exposes goal queue, status, and version progression."""
    director = temp_evolution_env["director"]
    version_tracker = temp_evolution_env["version_tracker"]
    journal = temp_evolution_env["journal"]
    evolver = temp_evolution_env["evolver"]

    engine = EvolutionEngine(
        codebase_evolver=evolver,
        version_tracker=version_tracker,
        journal=journal,
        goal_director=director,
    )

    status = engine.get_evolution_status()
    assert status["current_version"] == "0.1.0"
    assert status["queued_goals"] == 0
    assert "evolution.md" in status["evolution_md_path"]

    # Submit via engine facade
    goal = engine.submit_evolution_goal(
        title="Engine facade test goal",
        description="Test queue integration through unified engine",
    )
    assert goal.title == "Engine facade test goal"
    assert engine.get_evolution_status()["queued_goals"] == 1


def test_continuous_runner_processes_queue(temp_evolution_env):
    """Verifies that run_continuous drains queued goals in priority order."""
    director: EvolutionGoalDirector = temp_evolution_env["director"]
    version_tracker: VersionTracker = temp_evolution_env["version_tracker"]
    repo_root: Path = temp_evolution_env["repo_root"]

    # Target 1
    t1 = repo_root / "sonic-core" / "sonic" / "tools" / "t1.py"
    t1.parent.mkdir(parents=True, exist_ok=True)
    t1.write_text("x = 1\n", encoding="utf-8")

    # Target 2
    t2 = repo_root / "sonic-core" / "sonic" / "tools" / "t2.py"
    t2.write_text("y = 1\n", encoding="utf-8")

    director.submit_goal(title="Goal 1", description="Update t1", priority=2, target_files=["sonic-core/sonic/tools/t1.py"])
    director.submit_goal(title="Goal 2", description="Update t2", priority=1, target_files=["sonic-core/sonic/tools/t2.py"])

    assert len(director.list_goals(status=GoalStatus.QUEUED)) == 2

    import unittest.mock as mock
    with mock.patch.object(director.evolver, "run_tests") as mock_tests, \
         mock.patch.object(director.evolver, "run_security_regression") as mock_sec:
        from sonic.evolution.codebase_evolver import TestExecutionResult
        mock_tests.return_value = TestExecutionResult(passed=True, total_tests=1, passed_tests=1, duration_seconds=0.05)
        mock_sec.return_value = True

        reps = director.run_continuous(max_goals=2)
        assert len(reps) == 2
        # All goals in queue processed
        assert len(director.list_goals(status=GoalStatus.QUEUED)) == 0
        assert version_tracker.current_version() == "0.1.2"


def test_changelog_generation(temp_evolution_env):
    """Verifies markdown changelog formatting from evolution journal."""
    journal: EvolutionJournal = temp_evolution_env["journal"]

    journal.record_entry(JournalEntry(
        entry_id="c1",
        goal_id="g1",
        title="Added Subdomain CT Log Recon",
        category="capability_add",
        status="promoted",
        version_before="0.1.0",
        version_after="0.2.0",
        files_affected=["sonic-core/sonic/agents/recon.py"],
        lines_added=50,
        lines_removed=0,
        notes="Non-hallucinated CT log extraction",
        commit_hash="c0ffee",
    ))

    changelog = journal.generate_changelog("0.1.0", "0.2.0")
    assert "# 📜 SONIC Evolution Changelog (0.1.0 ➔ 0.2.0)" in changelog
    assert "Version `0.2.0` — Added Subdomain CT Log Recon" in changelog
    assert "`c0ffee`" in changelog

