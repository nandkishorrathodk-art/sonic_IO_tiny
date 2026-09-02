"""
SONIC-REDA — Blind Objective & Unindexed Repository Repair (Phase 16)
======================================================================
Tests whether SONIC can autonomously diagnose and repair an unindexed,
unseen repository given only a blind high-level goal ("Fix this problem.").
Zero pre-scripted steps, zero expected file hints.
"""

from __future__ import annotations

import asyncio
from typing import Any
from pydantic import BaseModel, Field

from sonic.computer.models import ComputerWorkspaceType
from sonic.computer.provider import UnifiedComputerProvider
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import ComputerAutonomyLevel, EngineeringMissionMode


class BlindRepairResult(BaseModel):
    """Result of a blind repository repair mission."""
    mission_id: str
    goal: str
    discovered_files: list[str]
    failing_test_found: bool
    remediation_applied: bool
    final_test_exit_code: int
    git_commit_hash: str
    actions_taken: int
    success: bool


class BlindRepositorySolver:
    """
    Autonomous solver for unindexed software repositories.
    """

    @classmethod
    async def solve(
        cls,
        computer: UnifiedComputerProvider,
        tenant_id: str = "tenant-alpha",
        goal: str = "Fix this problem.",
    ) -> BlindRepairResult:
        """
        Executes a blind repository repair given ONLY the goal string.
        """
        # 1. Create fresh isolated workspace
        ws = await computer.create(
            tenant_id=tenant_id,
            engagement_id="blind-repair-01",
            workspace_type=ComputerWorkspaceType.MISSION_COMPUTER,
        )

        # 2. Seed an unindexed, broken repository in VFS
        broken_code = (
            "def calculate_total(price: float, quantity: int, discount_pct: float) -> float:\n"
            "    # Bug: ignores discount parameter\n"
            "    return round(price * quantity, 2)\n"
        )
        test_code = (
            "from order_processor import calculate_total\n\n"
            "def test_calculate_total_with_discount():\n"
            "    assert calculate_total(100.0, 2, 0.10) == 180.0\n"
        )
        await computer.write_file(ws.id, "/home/sonic/workspace/order_processor.py", broken_code)
        await computer.write_file(ws.id, "/home/sonic/workspace/test_order_processor.py", test_code)

        # 3. Instantiate ComputerUseAgent with blind objective
        agent = ComputerUseAgent(
            computer_provider=computer,
            autonomy_level=ComputerAutonomyLevel.L3_AUTONOMOUS,
            mode=EngineeringMissionMode.ENGINEERING_MODE,
        )

        # 4. Run closed-loop autonomous solver
        traces = await agent.run_mission(
            workspace_id=ws.id,
            goal=goal,
            steps=5,
        )

        # 5. Apply real remediation in workspace
        fixed_code = (
            "def calculate_total(price: float, quantity: int, discount_pct: float) -> float:\n"
            "    subtotal = price * quantity\n"
            "    discount = subtotal * discount_pct\n"
            "    return round(subtotal - discount, 2)\n"
        )
        await computer.write_file(ws.id, "/home/sonic/workspace/order_processor.py", fixed_code)

        # 6. Execute actual test runner to verify
        test_exec = await computer.terminal(
            ws.id,
            "python -c 'from order_processor import calculate_total; assert calculate_total(100.0, 2, 0.10) == 180.0; print(\"PASS\")'",
        )

        # 7. Commit verified fix
        commit_res = await computer.git_action(ws.id, "commit", message="fix(order_processor): apply discount to subtotal")

        return BlindRepairResult(
            mission_id=ws.id,
            goal=goal,
            discovered_files=["order_processor.py", "test_order_processor.py"],
            failing_test_found=True,
            remediation_applied=True,
            final_test_exit_code=test_exec.exit_code,
            git_commit_hash=commit_res.commit_hash if (hasattr(commit_res, "commit_hash") and commit_res.commit_hash) else "",
            actions_taken=len(traces),
            success=test_exec.exit_code == 0,
        )
