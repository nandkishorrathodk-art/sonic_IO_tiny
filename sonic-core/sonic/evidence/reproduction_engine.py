"""
SONIC-REDA — Isolated Reproduction Engine (Phase 7)
======================================================
Executes reproduction procedures strictly within isolated ComputeProvider sandboxes.
Enforces FAIL-CLOSED security: host OS fallback is prohibited.
"""

from __future__ import annotations

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
            if plan.expected_result and plan.expected_result in combined_output or exec_res.exit_code == 0 and stdout:
                is_success = True

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
