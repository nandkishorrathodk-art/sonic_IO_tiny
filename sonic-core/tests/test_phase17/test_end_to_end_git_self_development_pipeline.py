"""
Tests for Phase 17: End-to-End Git Self-Development Pipeline.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.open_world.self_development_orchestrator import SelfDevelopmentOrchestrator, SelfDevelopmentPR
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_complete_git_self_development_workflow():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)

        pr = await SelfDevelopmentOrchestrator.run_self_development_mission(
            computer=comp,
            tenant_id="tenant-alpha",
            issue_description="Telemetry ring buffer memory leak under burst traffic",
        )

        assert isinstance(pr, SelfDevelopmentPR)
        assert pr.branch_name == "feat/auto-optimize-telemetry-buffer"
        assert pr.target_branch == "main"
        assert pr.test_suite_passed is True
        assert pr.security_invariants_passed is True
        assert pr.canary_deployed is True
        assert pr.promoted_to_main is True
        assert len(pr.git_commit_hash) >= 7

    asyncio.run(_run())
