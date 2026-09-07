"""
SONIC-REDA — Isolated Reproduction Engine (Phase 7)
======================================================
Executes reproduction procedures strictly within isolated ComputeProvider sandboxes.
Enforces FAIL-CLOSED security: host OS fallback is prohibited.
"""

from __future__ import annotations

import re
from typing import Any

from sonic.evidence.models import (
    ArtifactType,
    EvidenceItem,
    ProvenancedFinding,
    ReproductionPlan,
)
from sonic.logger import get_logger
from sonic.sandbox.provider import ComputeProvider

logger = get_logger(__name__)


class ReproductionEngine:
    """
    Executes controlled, sandbox-bound vulnerability reproductions.
    """

    def __init__(self, compute_provider: ComputeProvider | None = None):
        self.provider = compute_provider

    @staticmethod
    def _check_failure_conditions(failure_conditions: Any, combined_output: str) -> bool:
        """Return True if any failure condition is met in combined_output."""
        if not failure_conditions:
            return False
        if isinstance(failure_conditions, dict):
            for v in failure_conditions.values():
                if isinstance(v, (list, tuple, set)):
                    if any(str(item) in combined_output for item in v if str(item)):
                        return True
                elif isinstance(v, str) and v and v in combined_output:
                    return True
        elif isinstance(failure_conditions, (list, tuple, set)):
            if any(str(item) in combined_output for item in failure_conditions if str(item)):
                return True
        elif isinstance(failure_conditions, str) and failure_conditions and failure_conditions in combined_output:
            return True
        return False

    @classmethod
    def _verify_criteria(
        cls,
        finding: ProvenancedFinding | Any,
        plan: ReproductionPlan,
        combined_output: str,
    ) -> bool:
        """
        Check if output satisfies concrete verification criteria when no
        expected_result string is specified.
        Prevents false-positive verifications from innocent commands that return exit 0.
        """
        has_criteria = False

        # 1. Check plan.success_conditions
        if plan.success_conditions:
            conds = plan.success_conditions
            if isinstance(conds, dict):
                # Assertions
                if "assertions" in conds:
                    has_criteria = True
                    assertions = conds["assertions"]
                    if isinstance(assertions, (list, tuple, set)):
                        if not assertions or not all(str(a) in combined_output for a in assertions if str(a)):
                            return False
                    elif isinstance(assertions, str):
                        if not assertions.strip() or assertions not in combined_output:
                            return False

                # Contains / match
                if "contains" in conds:
                    has_criteria = True
                    contains = conds["contains"]
                    if isinstance(contains, (list, tuple, set)):
                        if not contains or not all(str(c) in combined_output for c in contains if str(c)):
                            return False
                    elif isinstance(contains, str):
                        if not contains.strip() or contains not in combined_output:
                            return False

                # Flags
                if "flags" in conds:
                    has_criteria = True
                    flags = conds["flags"]
                    if isinstance(flags, (list, tuple, set)):
                        if not flags or not all(str(f) in combined_output for f in flags if str(f)):
                            return False
                    elif isinstance(flags, str):
                        if not flags.strip() or flags not in combined_output:
                            return False

                # Regex / Pattern
                if "regex" in conds or "pattern" in conds:
                    has_criteria = True
                    pattern = conds.get("regex") or conds.get("pattern")
                    if isinstance(pattern, str) and pattern:
                        if not re.search(pattern, combined_output):
                            return False

                # Status Code
                if "status_code" in conds:
                    has_criteria = True
                    sc = str(conds["status_code"])
                    if sc not in combined_output:
                        return False

            elif isinstance(conds, (list, tuple, set)):
                has_criteria = True
                if not conds or not all(str(c) in combined_output for c in conds if str(c)):
                    return False
            elif isinstance(conds, str) and conds.strip():
                has_criteria = True
                if conds not in combined_output:
                    return False

        # 2. Check finding verification criteria / flags / assertions
        finding_expected = (
            getattr(finding, "expected_if_vulnerable", None)
            or (finding.get("expected_if_vulnerable") if isinstance(finding, dict) else None)
        )
        if finding_expected and isinstance(finding_expected, str) and finding_expected.strip():
            has_criteria = True
            if finding_expected not in combined_output:
                return False

        finding_flags = (
            getattr(finding, "verification_flags", None)
            or (finding.get("verification_flags") if isinstance(finding, dict) else None)
        )
        if finding_flags:
            has_criteria = True
            if isinstance(finding_flags, (list, tuple, set)):
                if not finding_flags or not all(str(f) in combined_output for f in finding_flags if str(f)):
                    return False
            elif isinstance(finding_flags, str) and finding_flags.strip():
                if finding_flags not in combined_output:
                    return False

        finding_assertions = (
            getattr(finding, "assertions", None)
            or (finding.get("assertions") if isinstance(finding, dict) else None)
        )
        if finding_assertions:
            has_criteria = True
            if isinstance(finding_assertions, (list, tuple, set)):
                if not finding_assertions or not all(str(a) in combined_output for a in finding_assertions if str(a)):
                    return False
            elif isinstance(finding_assertions, str) and finding_assertions.strip():
                if finding_assertions not in combined_output:
                    return False

        # 3. Check failure conditions if specified on plan
        if plan.failure_conditions:
            if cls._check_failure_conditions(plan.failure_conditions, combined_output):
                return False

        return has_criteria

    async def execute_reproduction(
        self,
        finding: ProvenancedFinding,
        plan: ReproductionPlan,
        workspace_id: str = "reproduction-sandbox",
        timeout_seconds: int = 120,
    ) -> tuple[bool, str, EvidenceItem | None]:
        """
        Execute reproduction plan in isolated compute sandbox.

        Returns:
            (success, output_or_error_message, evidence_item)
        """
        logger.info(
            "reproduction_starting",
            finding_id=finding.id,
            target=plan.target,
            tenant_id=finding.tenant_id,
        )

        # 1. No provider means no execution. Never manufacture an HTTP response
        # or evidence item when a live isolated runtime is unavailable.
        if not self.provider:
            return False, "Reproduction blocked: no isolated execution provider is attached", None

        # 2. Live ComputeProvider Execution (FAIL-CLOSED)
        cmd = plan.poc_command or (plan.steps[0] if plan.steps else "echo 'No PoC'")
        try:
            exec_res = await self.provider.execute(
                workspace_id=workspace_id,
                command=cmd,
                timeout=timeout_seconds,
            )

            stdout = exec_res.stdout or ""
            stderr = exec_res.stderr or ""
            combined_output = f"{stdout}\n{stderr}".strip()

            # Check expected results
            is_success = False
            expected = (plan.expected_result or "").strip()
            if expected:
                is_success = expected in combined_output
            else:
                # If no expected_result was specified, do not automatically mark success
                # just because curl/http returned exit 0!
                # Require finding verification criteria (e.g. check exec_res.exit_code == 0
                # and finding verification flags or assertions).
                if exec_res.exit_code == 0:
                    is_success = self._verify_criteria(finding, plan, combined_output)

            # Failure conditions override success
            if is_success and plan.failure_conditions:
                if self._check_failure_conditions(plan.failure_conditions, combined_output):
                    is_success = False

            ev_item = EvidenceItem(
                tenant_id=finding.tenant_id,
                engagement_id=finding.engagement_id,
                finding_id=finding.id,
                source_type="sandbox_runtime",
                source_agent="reproduction-engine",
                tool_name="poc_runner",
                execution_id=f"exec-{finding.id}-{exec_res.sandbox_id or workspace_id}",
                sandbox_id=workspace_id,
                artifact_type=ArtifactType.TOOL_OUTPUT,
                raw_content=combined_output,
            )
            ev_item.compute_and_set_hash()
            finding.add_evidence(ev_item)

            return is_success, combined_output, ev_item

        except Exception as e:
            logger.error("reproduction_sandbox_error", finding_id=finding.id, error=str(e))
            return False, f"Sandbox execution error: {str(e)}", None
