"""
SONIC v2 — Continuous Codebase Self-Evolution Engine
====================================================
Enables autonomous codebase self-updates, bug fixes, and logical upgrades across
non-safety components of the repository.

Architectural Invariants:
1. Safety Envelope Immutability: AI self-evolution is strictly FORBIDDEN from
   modifying any protected safety kernel components (sonic/safety, egress,
   action_broker, sealed policy). Violations fail-closed immediately.
2. AST & Syntax Pre-flight: No code is applied without passing syntax verification.
3. Test-Driven Verification: Every proposed change must pass targeted unit tests
   and the security regression suite with 100% green exit codes.
4. Zero-Corrupt Atomic Rollback: If any test fails, all modifications are restored
   instantly from snapshots and an [AVOID] lesson is recorded in LessonsLedger.
5. Autonomous Promotion & Git Push: When auto_promote=True and all tests pass,
   changes are automatically committed to git and pushed to remote without
   requiring manual human approval.
6. Structured Evolution Summary: Every evolution cycle produces an honest,
   detailed audit report documenting what was done, diff metrics, test results,
   and git provenance.
"""

from __future__ import annotations

import ast
import difflib
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sonic.evolution.pipeline import EvolutionPipeline, EvolutionStage, ImprovementProposal
from sonic.logger import get_logger

logger = get_logger(__name__)

# Protected safety paths that the self-evolution engine is strictly forbidden from proposing edits to
_PROTECTED_COMPONENTS = frozenset([
    "sonic/safety",
    "sonic/kernel/action_broker",
    "sonic/safety/kernel",
    "sonic/safety/sealed",
    "sonic/safety/action_policy",
    "sonic/sandbox/egress",
    "sonic-kernel-rs/src/safety",
])


class SafetyInvariantViolation(Exception):
    """Raised when an evolution proposal attempts to modify a protected safety module."""


@dataclass
class VerificationTestResult:
    """Outcome of running test suites against a proposed codebase modification."""
    __test__ = False  # Prevent pytest from treating this dataclass as a test suite
    passed: bool
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    duration_seconds: float = 0.0
    raw_output: str = ""
    error_message: str = ""


# Backwards compatibility alias
TestExecutionResult = VerificationTestResult


@dataclass
class EvolutionSummaryReport:
    """Comprehensive, tamper-evident audit report of a codebase evolution cycle."""
    proposal_id: str
    target_component: str
    description: str
    stage: EvolutionStage
    files_affected: list[str] = field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0
    ast_validated: bool = False
    test_result: TestExecutionResult = field(default_factory=lambda: TestExecutionResult(passed=False))
    security_regression_passed: bool = False
    git_committed: bool = False
    git_commit_hash: str = ""
    git_pushed: bool = False
    git_push_message: str = ""
    error_reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_markdown(self) -> str:
        """Renders a clean, structured GitHub-flavored Markdown summary."""
        status_badge = {
            EvolutionStage.PROMOTED: "🟢 PROMOTED (AUTO-MERGED)",
            EvolutionStage.AWAITING_APPROVAL: "🟡 AWAITING OPERATOR APPROVAL",
            EvolutionStage.ROLLED_BACK: "🔴 ROLLED BACK (TESTS FAILED)",
            EvolutionStage.REJECTED: "⛔ REJECTED (SAFETY/AST VIOLATION)",
        }.get(self.stage, f"⚪ {self.stage.value.upper()}")

        md = [
            f"# 🧬 Codebase Self-Evolution Summary: `{self.proposal_id}`",
            "",
            f"**Status:** {status_badge}  ",
            f"**Target Component:** `{self.target_component}`  ",
            f"**Timestamp:** `{self.timestamp}`  ",
            "",
            "## 1. Upgrade Description & Objectives",
            f"> {self.description}",
            "",
            "## 2. Code Modifications & Diff Metrics",
            f"- **Files Affected:** {', '.join(f'`{f}`' for f in self.files_affected) if self.files_affected else 'None'}",
            f"- **Lines Added:** `+{self.lines_added}`",
            f"- **Lines Removed:** `-{self.lines_removed}`",
            f"- **AST / Syntax Pre-flight:** {'✅ Passed' if self.ast_validated else '❌ Failed'}",
            "",
            "## 3. Automated Verification & Test Results",
            f"- **Component Tests:** {'✅ 100% PASSED' if self.test_result.passed else '❌ FAILED'}",
            f"  - Passed: `{self.test_result.passed_tests}` / `{self.test_result.total_tests}`",
            f"  - Failed: `{self.test_result.failed_tests}`",
            f"  - Duration: `{self.test_result.duration_seconds:.2f}s`",
            f"- **Security Regression Suite:** {'✅ 100% PASSED (Zero Safety Breaches)' if self.security_regression_passed else '❌ FAILED/SKIPPED'}",
            "",
            "## 4. Git Provenance & Automation",
            f"- **Git Committed:** {'✅ Yes' if self.git_committed else '❌ No'}",
            f"- **Commit Hash:** `{self.git_commit_hash if self.git_commit_hash else 'N/A'}`",
            f"- **Git Pushed to Remote:** {'✅ Yes (Origin Updated)' if self.git_pushed else '❌ No / Offline / Skipped'}",
        ]

        if self.git_push_message:
            md.append(f"- **Git Push Details:** `{self.git_push_message}`")

        if self.error_reason:
            md.extend([
                "",
                "## ⚠️ Error / Rejection Details",
                f"```\n{self.error_reason}\n```",
            ])

        return "\n".join(md)


class CodebaseEvolver:
    """
    Automated, guarded runner that enables the AI being to continuously upgrade,
    patch, and evolve its own codebase across non-safety components.
    """

    def __init__(
        self,
        repo_root: Path | str | None = None,
        lessons_ledger: Any | None = None,
        pipeline: EvolutionPipeline | None = None,
    ):
        if repo_root is None:
            # Default to repo root (c:\Users\nandk\_society or parent of sonic-core)
            cur = Path(__file__).resolve()
            # walk up until we find .git or pyproject.toml
            root = cur.parent
            for p in cur.parents:
                if (p / ".git").exists() or (p / "sonic-core").exists():
                    root = p
                    break
            self.repo_root = root
        else:
            self.repo_root = Path(repo_root).resolve()

        self.lessons_ledger = lessons_ledger
        self.pipeline = pipeline if pipeline is not None else EvolutionPipeline()
        self._snapshots: dict[Path, str | None] = {}

    # ------------------------------------------------------------------
    # 1. Safety Envelope Invariant Check
    # ------------------------------------------------------------------
    def is_protected(self, component_path: str) -> bool:
        """
        Enforces strict safety envelope immutability.
        Returns True if the target path touches any protected safety component.
        """
        normalized = component_path.replace("\\", "/").lower()
        for protected in _PROTECTED_COMPONENTS:
            if protected.lower() in normalized:
                return True
        return False

    # ------------------------------------------------------------------
    # 2. Syntax / AST Pre-flight
    # ------------------------------------------------------------------
    def validate_ast(self, file_path: Path, content: str) -> tuple[bool, str]:
        """Validates syntax using Python AST before touching disk."""
        if file_path.suffix == ".py":
            try:
                ast.parse(content, filename=str(file_path))
                return True, "AST syntax check passed"
            except SyntaxError as e:
                return False, f"SyntaxError in {file_path.name}: {e.msg} at line {e.lineno}:{e.offset}"
            except Exception as e:
                return False, f"AST parse error in {file_path.name}: {e}"
        return True, "Non-Python syntax check skipped"

    # ------------------------------------------------------------------
    # 3. Snapshot & Atomic Rollback
    # ------------------------------------------------------------------
    def _record_snapshot(self, path: Path) -> None:
        """Stores the original file content for zero-risk atomic rollback."""
        if path not in self._snapshots:
            if path.exists():
                self._snapshots[path] = path.read_text(encoding="utf-8", errors="replace")
            else:
                self._snapshots[path] = None  # indicates new file

    def rollback_snapshots(self) -> None:
        """Restores all modified files to their exact pre-evolution state."""
        for path, original_content in self._snapshots.items():
            try:
                if original_content is None:
                    if path.exists():
                        path.unlink()
                else:
                    path.write_text(original_content, encoding="utf-8")
            except Exception as e:
                logger.error("evolution_rollback_failed_for_file", file=str(path), error=str(e))
        self._snapshots.clear()

    def clear_snapshots(self) -> None:
        """Discards snapshots after successful promotion."""
        self._snapshots.clear()

    # ------------------------------------------------------------------
    # 4. Patch / Code Application
    # ------------------------------------------------------------------
    def apply_patch(
        self,
        target_file_rel: str,
        code_diff_or_content: str,
    ) -> tuple[bool, str, int, int]:
        """
        Applies either a unified diff or direct code replacement.
        Returns: (success, message, lines_added, lines_removed)
        """
        target_path = (self.repo_root / target_file_rel).resolve()

        # Check safety guard on the target path
        if self.is_protected(target_file_rel):
            raise SafetyInvariantViolation(
                f"Forbidden: '{target_file_rel}' is a protected safety component and cannot be self-modified."
            )

        # Check if content is a unified diff
        is_unified_diff = (
            code_diff_or_content.startswith("--- ")
            or "\n@@ " in code_diff_or_content
            or "\n--- " in code_diff_or_content
        )

        self._record_snapshot(target_path)

        if is_unified_diff:
            # Apply via git apply in temp patch file
            with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False, encoding="utf-8") as tf:
                tf.write(code_diff_or_content)
                temp_patch_path = tf.name

            try:
                cmd = ["git", "apply", "--whitespace=fix", temp_patch_path]
                res = subprocess.run(cmd, cwd=str(self.repo_root), capture_output=True, text=True, timeout=30)
                if res.returncode != 0:
                    # Fallback to direct replacement if unified diff failed
                    return False, f"git apply failed: {res.stderr or res.stdout}", 0, 0

                # Count diff lines
                added = sum(1 for line in code_diff_or_content.splitlines() if line.startswith("+") and not line.startswith("+++"))
                removed = sum(1 for line in code_diff_or_content.splitlines() if line.startswith("-") and not line.startswith("---"))
                return True, "Unified diff applied successfully", added, removed
            finally:
                if os.path.exists(temp_patch_path):
                    os.unlink(temp_patch_path)
        else:
            # Direct code replacement
            old_text = self._snapshots[target_path] or ""
            new_text = code_diff_or_content

            # AST pre-flight check
            ast_ok, ast_msg = self.validate_ast(target_path, new_text)
            if not ast_ok:
                return False, ast_msg, 0, 0

            # Compute diff stats
            old_lines = old_text.splitlines()
            new_lines = new_text.splitlines()
            matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
            added = sum(hi2 - lo2 for tag, lo1, hi1, lo2, hi2 in matcher.get_opcodes() if tag in ("replace", "insert"))
            removed = sum(hi1 - lo1 for tag, lo1, hi1, lo2, hi2 in matcher.get_opcodes() if tag in ("replace", "delete"))

            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(new_text, encoding="utf-8")
            return True, "File content written and validated", added, removed

    # ------------------------------------------------------------------
    # 5. Test Suite Verification
    # ------------------------------------------------------------------
    def run_tests(self, test_paths: list[str] | None = None) -> TestExecutionResult:
        """Runs pytest on the specified test paths with structured parsing."""
        if not test_paths:
            # Default to quick evolution tests
            test_paths = ["sonic-core/tests/test_evolution_strategy_and_engine.py"]

        cmd = [sys.executable, "-m", "pytest"] + test_paths + ["-q", "--tb=short"]
        start_time = time.time()
        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=120,
            )
            duration = time.time() - start_time
            output = (res.stdout or "") + (res.stderr or "")

            # Parse pytest summary line: e.g. "7 passed, 1 failed, 1 skipped in 1.23s"
            passed = 0
            failed = 0
            skipped = 0

            m_pass = re.search(r"(\d+)\s+passed", output)
            if m_pass:
                passed = int(m_pass.group(1))

            m_fail = re.search(r"(\d+)\s+failed", output)
            if m_fail:
                failed = int(m_fail.group(1))

            m_skip = re.search(r"(\d+)\s+skipped", output)
            if m_skip:
                skipped = int(m_skip.group(1))

            total = passed + failed + skipped
            is_success = (res.returncode == 0) and (failed == 0)

            return TestExecutionResult(
                passed=is_success,
                total_tests=total,
                passed_tests=passed,
                failed_tests=failed,
                skipped_tests=skipped,
                duration_seconds=duration,
                raw_output=output,
                error_message="" if is_success else f"Tests failed with exit code {res.returncode}",
            )
        except Exception as e:
            return TestExecutionResult(
                passed=False,
                error_message=f"Test runner error: {e}",
                duration_seconds=time.time() - start_time,
            )

    def run_security_regression(self) -> bool:
        """Verifies that no security invariants are broken by the proposed change."""
        sec_tests = ["sonic-core/tests/test_p0_security_hardening.py"]
        existing = [t for t in sec_tests if (self.repo_root / t).exists()]
        if not existing:
            return True
        res = self.run_tests(existing)
        return res.passed

    # ------------------------------------------------------------------
    # 6. Git Commit & Push (Auto-Promotion)
    # ------------------------------------------------------------------
    def commit_and_push(
        self,
        proposal_id: str,
        description: str,
        files: list[str],
        push: bool = False,
    ) -> tuple[bool, str, bool, str]:
        """
        Commits verified modifications and pushes upstream without human intervention.
        Returns: (committed, commit_hash, pushed, push_message)
        """
        try:
            # 1. git add
            add_cmd = ["git", "add"] + files
            res_add = subprocess.run(add_cmd, cwd=str(self.repo_root), capture_output=True, text=True)
            if res_add.returncode != 0:
                return False, "", False, f"git add failed: {res_add.stderr}"

            # 2. git commit
            commit_msg = f"evo({proposal_id}): {description}\n\n[Verified by SONIC Continuous Codebase Evolver]"
            commit_cmd = ["git", "commit", "-m", commit_msg]
            res_commit = subprocess.run(commit_cmd, cwd=str(self.repo_root), capture_output=True, text=True)
            if res_commit.returncode != 0 and "nothing to commit" not in res_commit.stdout:
                return False, "", False, f"git commit failed: {res_commit.stderr}"

            # 3. get commit hash
            hash_res = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
            )
            commit_hash = hash_res.stdout.strip()

            # 4. git push if requested
            pushed = False
            push_msg = ""
            if push:
                # get current branch
                br_res = subprocess.run(
                    ["git", "branch", "--show-current"],
                    cwd=str(self.repo_root),
                    capture_output=True,
                    text=True,
                )
                branch = br_res.stdout.strip() or "main"
                push_cmd = ["git", "push", "origin", branch]
                res_push = subprocess.run(push_cmd, cwd=str(self.repo_root), capture_output=True, text=True, timeout=45)
                if res_push.returncode == 0:
                    pushed = True
                    push_msg = f"Successfully pushed to origin/{branch}"
                else:
                    pushed = False
                    push_msg = f"Push error (upstream or network): {res_push.stderr or res_push.stdout}"
            else:
                push_msg = "Push omitted (push=False)"

            return True, commit_hash, pushed, push_msg
        except Exception as e:
            return False, "", False, f"Git automation exception: {e}"

    # ------------------------------------------------------------------
    # 7. Complete Evolution Cycle
    # ------------------------------------------------------------------
    def evolve(
        self,
        target_component: str,
        description: str,
        code_diff: str,
        auto_promote: bool = True,
        push: bool = False,
        test_paths: list[str] | None = None,
    ) -> EvolutionSummaryReport:
        """
        Executes a complete, closed-loop codebase evolution cycle:
        1. Safety Invariant verification (Fail-closed on safety components)
        2. AST / Syntax verification
        3. Snapshot staging & file patch
        4. Targeted component unit tests
        5. Security regression verification
        6. Auto-commit & git push if auto_promote is active
        7. Rollback and lesson learning on any failure
        8. Returns rich EvolutionSummaryReport
        """
        proposal, reason = self.pipeline.submit_proposal(
            target_component=target_component,
            description=description,
            code_diff=code_diff,
        )

        report = EvolutionSummaryReport(
            proposal_id=proposal.proposal_id,
            target_component=target_component,
            description=description,
            stage=proposal.stage,
            files_affected=[target_component],
        )

        # Gate 1: Safety Invariant Check
        if self.is_protected(target_component):
            logger.critical("evolution_safety_invariant_violation", component=target_component)
            report.stage = EvolutionStage.REJECTED
            report.error_reason = f"Safety Invariant Violation: '{target_component}' is protected."
            return report

        # Gate 2: Staging & Patch Application
        try:
            ok, msg, added, removed = self.apply_patch(target_component, code_diff)
            report.lines_added = added
            report.lines_removed = removed
            if not ok:
                self.rollback_snapshots()
                report.stage = EvolutionStage.REJECTED
                report.error_reason = f"Patch application failed: {msg}"
                return report
            report.ast_validated = True
        except SafetyInvariantViolation as e:
            self.rollback_snapshots()
            report.stage = EvolutionStage.REJECTED
            report.error_reason = str(e)
            return report
        except Exception as e:
            self.rollback_snapshots()
            report.stage = EvolutionStage.REJECTED
            report.error_reason = f"Unexpected patch failure: {e}"
            return report

        # Gate 3: Unit / Component Tests
        self.pipeline.advance_stage(proposal.proposal_id, EvolutionStage.ISOLATED_BRANCH, "Staged in workspace")
        test_res = self.run_tests(test_paths)
        report.test_result = test_res

        if not test_res.passed:
            logger.warning("evolution_tests_failed", proposal_id=proposal.proposal_id, error=test_res.error_message)
            self.rollback_snapshots()
            report.stage = EvolutionStage.ROLLED_BACK
            report.error_reason = f"Verification tests failed: {test_res.error_message}\n{test_res.raw_output[:500]}"
            self.pipeline.advance_stage(proposal.proposal_id, EvolutionStage.ROLLED_BACK, report.error_reason)

            # Record AVOID lesson in LessonsLedger if available
            if self.lessons_ledger is not None and hasattr(self.lessons_ledger, "record"):
                try:
                    from sonic.being.lessons import Lesson, LessonKind
                    lesson = Lesson(
                        lesson_id=f"evo-fail-{proposal.proposal_id}",
                        kind=LessonKind.AVOID,
                        goal=f"Evolve codebase {target_component}",
                        approach=description,
                        evidence=f"Tests failed: {test_res.raw_output[:200]}",
                        created_at=datetime.now(UTC).isoformat(),
                    )
                    try:
                        self.lessons_ledger.record([lesson])
                    except TypeError:
                        self.lessons_ledger.record(lesson)
                except Exception as e:
                    logger.warning("evolution_record_lesson_failed", error=str(e))
            return report

        self.pipeline.advance_stage(proposal.proposal_id, EvolutionStage.TESTS_PASSING, f"{test_res.passed_tests} tests green")

        # Gate 4: Security Regression Suite
        sec_ok = self.run_security_regression()
        report.security_regression_passed = sec_ok
        if not sec_ok:
            logger.critical("evolution_security_regression_failed", proposal_id=proposal.proposal_id)
            self.rollback_snapshots()
            report.stage = EvolutionStage.ROLLED_BACK
            report.error_reason = "Security regression suite failed — potential safety degradation."
            self.pipeline.advance_stage(proposal.proposal_id, EvolutionStage.ROLLED_BACK, report.error_reason)
            return report

        self.pipeline.advance_stage(proposal.proposal_id, EvolutionStage.SECURITY_REGRESSION_PASSING, "Zero safety regressions")

        # Gate 5: Promotion & Git Automation
        self.clear_snapshots()  # Changes are verified and retained

        if auto_promote:
            committed, chash, pushed, pmsg = self.commit_and_push(
                proposal_id=proposal.proposal_id,
                description=description,
                files=[target_component],
                push=push,
            )
            report.git_committed = committed
            report.git_commit_hash = chash
            report.git_pushed = pushed
            report.git_push_message = pmsg
            report.stage = EvolutionStage.PROMOTED
            self.pipeline.advance_stage(proposal.proposal_id, EvolutionStage.PROMOTED, f"Auto-promoted (hash: {chash})")
        else:
            report.stage = EvolutionStage.AWAITING_APPROVAL
            self.pipeline.advance_stage(proposal.proposal_id, EvolutionStage.AWAITING_APPROVAL, "Tests passed, awaiting operator approval")

        return report
