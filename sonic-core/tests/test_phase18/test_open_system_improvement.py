"""
Tests for Phase 18: Unprompted Open-System Improver ("Improve this system").
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.continuous_dev.open_system_improver import OpenSystemImprover
from sonic.continuous_dev.models import OpenSystemImprovementReport
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_unprompted_open_system_improvement():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)

        report = await OpenSystemImprover.improve(
            computer=comp,
            tenant_id="tenant-alpha",
            goal="Improve this system.",
        )

        assert isinstance(report, OpenSystemImprovementReport)
        assert report.success is True
        assert report.test_suite_passed is True
        assert report.improvement_pct > 90.0
        assert "RouterTable" in report.discovered_bottleneck
        assert len(report.git_commit_hash) >= 7

    asyncio.run(_run())
