"""
Tests for Continuous Codebase Self-Evolution Engine (`CodebaseEvolver`)
=====================================================================
Verifies:
1. Safety Invariant: AI is strictly blocked from proposing edits to safety kernels.
2. Syntax Pre-flight: Python AST catches syntax errors before touching files.
3. Atomic Rollback: When tests fail, all modifications are cleanly rolled back.
4. Lessons Integration: Test failures automatically record [AVOID] lessons.
5. Evolution Summary Report: Generates rich, structured markdown reports.
6. Auto-Promotion Gate: Commits and pushes without human approval when tests pass.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sonic.being.lessons import LessonKind, LessonsLedger
from sonic.evolution.codebase_evolver import (
    CodebaseEvolver,
    EvolutionSummaryReport,
    SafetyInvariantViolation,
    TestExecutionResult,
)
from sonic.evolution.pipeline import EvolutionStage


@pytest.fixture
def temp_repo(tmp_path):
    """Creates a temporary isolated repository structure for evolution testing."""
    repo = tmp_path / "mock_repo"
    repo.mkdir()

    # Create directory structure
    (repo / "sonic" / "safety").mkdir(parents=True)
    (repo / "sonic" / "tools" / "adapters").mkdir(parents=True)
    (repo / "sonic" / "research").mkdir(parents=True)
    (repo / "tests").mkdir(parents=True)

    # Populate a protected safety file
    (repo / "sonic" / "safety" / "kernel.py").write_text(
        "# PROTECTED SAFETY KERNEL\nclass SafetyKernel:\n    pass\n", encoding="utf-8"
    )

    # Populate an evolvable tool adapter file
    (repo / "sonic" / "tools" / "adapters" / "custom_parser.py").write_text(
        "def parse_status(code: int) -> str:\n    return 'OK' if code == 200 else 'ERR'\n",
        encoding="utf-8",
    )

    # Populate a test file
    (repo / "tests" / "test_parser.py").write_text(
        "from sonic.tools.adapters.custom_parser import parse_status\n\n"
        "def test_status():\n    assert parse_status(200) == 'OK'\n",
        encoding="utf-8",
    )

    return repo


class TestSafetyInvariants:
    def test_rejects_modification_to_protected_safety_components(self, temp_repo):
        evolver = CodebaseEvolver(repo_root=temp_repo)

        protected_targets = [
            "sonic/safety/kernel.py",
            "sonic/safety/sealed.py",
            "sonic/safety/action_policy.py",
            "sonic/kernel/action_broker.py",
            "sonic/sandbox/egress.py",
            "sonic-kernel-rs/src/safety/mod.rs",
        ]

        for target in protected_targets:
            assert evolver.is_protected(target) is True
            report = evolver.evolve(
                target_component=target,
                description="Bypass safety filters for speed",
                code_diff="def bypass(): pass",
            )
            assert report.stage == EvolutionStage.REJECTED
            assert "Safety Invariant Violation" in report.error_reason

        # Ensure protected file was NOT touched
        kernel_content = (temp_repo / "sonic" / "safety" / "kernel.py").read_text(encoding="utf-8")
        assert "PROTECTED SAFETY KERNEL" in kernel_content


class TestSyntaxAndStaging:
    def test_catches_ast_syntax_errors_before_touching_disk(self, temp_repo):
        evolver = CodebaseEvolver(repo_root=temp_repo)
        target = "sonic/tools/adapters/custom_parser.py"

        orig_content = (temp_repo / target).read_text(encoding="utf-8")

        # Propose broken Python code with syntax error
        broken_code = "def parse_status(code: int) -> str\n    return 'broken'"

        report = evolver.evolve(
            target_component=target,
            description="Broken syntax upgrade",
            code_diff=broken_code,
        )

        assert report.stage == EvolutionStage.REJECTED
        assert "SyntaxError" in report.error_reason
        assert report.ast_validated is False

        # File content must remain completely unchanged
        current_content = (temp_repo / target).read_text(encoding="utf-8")
        assert current_content == orig_content


class TestRollbackAndLessons:
    def test_rolls_back_and_records_avoid_lesson_when_tests_fail(self, temp_repo, tmp_path):
        ledger = LessonsLedger(tenant_id="test-tenant", agent_id="test-agent")
        evolver = CodebaseEvolver(repo_root=temp_repo, lessons_ledger=ledger)
        target = "sonic/tools/adapters/custom_parser.py"
        orig_content = (temp_repo / target).read_text(encoding="utf-8")

        # Code is valid Python AST, but changes behavior and breaks the test
        breaking_code = "def parse_status(code: int) -> str:\n    return 'ALWAYS_FAIL'\n"

        # Mock test runner to simulate failed tests
        mock_res = TestExecutionResult(
            passed=False,
            total_tests=5,
            passed_tests=3,
            failed_tests=2,
            duration_seconds=1.2,
            error_message="AssertionError: 'ALWAYS_FAIL' != 'OK'",
            raw_output="FAILED test_parser.py::test_status",
        )

        with patch.object(evolver, "run_tests", return_value=mock_res):
            report = evolver.evolve(
                target_component=target,
                description="Mutate status parsing return value",
                code_diff=breaking_code,
                auto_promote=True,
            )

        assert report.stage == EvolutionStage.ROLLED_BACK
        assert report.test_result.passed is False
        assert "Verification tests failed" in report.error_reason

        # Verified: Atomic rollback restored the original file
        assert (temp_repo / target).read_text(encoding="utf-8") == orig_content

        # Verified: AVOID lesson was recorded in the ledger
        lessons = ledger.all()
        assert len(lessons) >= 1
        assert any(l.kind == LessonKind.AVOID for l in lessons)


class TestSuccessfulEvolutionAndSummary:
    def test_successful_upgrade_with_auto_promotion_and_markdown_summary(self, temp_repo):
        evolver = CodebaseEvolver(repo_root=temp_repo)
        target = "sonic/tools/adapters/custom_parser.py"

        # Enhanced, backwards-compatible implementation
        enhanced_code = (
            "def parse_status(code: int) -> str:\n"
            "    if code in (200, 201, 204):\n"
            "        return 'OK'\n"
            "    return 'ERR'\n"
        )

        mock_test_res = TestExecutionResult(
            passed=True,
            total_tests=4,
            passed_tests=4,
            failed_tests=0,
            duration_seconds=0.45,
            raw_output="4 passed in 0.45s",
        )

        with patch.object(evolver, "run_tests", return_value=mock_test_res), \
             patch.object(evolver, "run_security_regression", return_value=True), \
             patch.object(evolver, "commit_and_push", return_value=(True, "a1b2c3d", True, "Pushed to origin/main")):

            report = evolver.evolve(
                target_component=target,
                description="Support HTTP 201 and 204 in parse_status",
                code_diff=enhanced_code,
                auto_promote=True,
                push=True,
            )

        assert report.stage == EvolutionStage.PROMOTED
        assert report.ast_validated is True
        assert report.test_result.passed is True
        assert report.security_regression_passed is True
        assert report.git_committed is True
        assert report.git_commit_hash == "a1b2c3d"
        assert report.git_pushed is True

        # Markdown summary verification
        md = report.to_markdown()
        assert "# 🧬 Codebase Self-Evolution Summary:" in md
        assert "PROMOTED (AUTO-MERGED)" in md
        assert "Support HTTP 201 and 204 in parse_status" in md
        assert "Passed: `4` / `4`" in md
        assert "a1b2c3d" in md
        assert "Origin Updated" in md

    def test_manual_approval_mode_when_auto_promote_is_false(self, temp_repo):
        evolver = CodebaseEvolver(repo_root=temp_repo)
        target = "sonic/tools/adapters/custom_parser.py"

        enhanced_code = "def parse_status(code: int) -> str:\n    return 'OK'\n"

        mock_test_res = TestExecutionResult(passed=True, total_tests=2, passed_tests=2)

        with patch.object(evolver, "run_tests", return_value=mock_test_res), \
             patch.object(evolver, "run_security_regression", return_value=True):

            report = evolver.evolve(
                target_component=target,
                description="Minor refactor",
                code_diff=enhanced_code,
                auto_promote=False,
            )

        assert report.stage == EvolutionStage.AWAITING_APPROVAL
        assert report.git_committed is False
        assert "AWAITING OPERATOR APPROVAL" in report.to_markdown()
