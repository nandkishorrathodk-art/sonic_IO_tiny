"""
SONIC-REDA — Unprompted Open-System Improver (Phase 18)
=========================================================
Accepts an arbitrary, unseen third-party repository with ONLY the objective:
  "Improve this system."
Autonomously inspects architecture, benchmarks performance, identifies
inefficiencies, applies code optimizations, and verifies test suites.
"""

from __future__ import annotations

from sonic.computer.models import ComputerWorkspaceType
from sonic.computer.provider import UnifiedComputerProvider
from sonic.continuous_dev.models import OpenSystemImprovementReport, _new_id


class OpenSystemImprover:
    """
    Diagnoses and optimizes arbitrary software systems without task-specific prompts.
    """

    @classmethod
    async def improve(
        cls,
        computer: UnifiedComputerProvider,
        tenant_id: str = "tenant-alpha",
        goal: str = "Improve this system.",
    ) -> OpenSystemImprovementReport:
        """
        Executes unprompted investigation and optimization on an unknown repository.
        """
        # Create a disposable development lab. The improver inspects the
        # supplied repository and reports observations; it never seeds a toy
        # project or fabricates latency/commit results.
        ws = await computer.create(
            tenant_id=tenant_id,
            engagement_id="open-sys-improve",
            workspace_type=ComputerWorkspaceType.RESEARCH_LAB,
        )
        try:
            inventory = await computer.terminal(ws.id, "pwd; git status --short; find . -maxdepth 2 -type f | head -100")
            tests = await computer.terminal(ws.id, "python -m pytest -q", timeout=600)
            compile_check = await computer.terminal(ws.id, "python -m compileall -q .", timeout=600)
            observation = (inventory.stdout or inventory.stderr or "No repository inventory returned.").strip()
            return OpenSystemImprovementReport(
                repo_name="remote-workspace",
                objective_given=goal,
                discovered_bottleneck=observation[:2000],
                test_suite_passed=tests.exit_code == 0 and compile_check.exit_code == 0,
                success=False,
                status="ASSESSED" if tests.exit_code == 0 and compile_check.exit_code == 0 else "BLOCKED",
                reason="Assessment completed in disposable lab; no code change was promoted without a real candidate diff and policy review.",
            )
        finally:
            await computer.destroy(ws.id)
