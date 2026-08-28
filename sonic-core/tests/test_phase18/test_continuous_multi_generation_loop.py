"""
Tests for Phase 18: Continuous Multi-Generation Development Loop (v1 -> v2 -> v3).
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.continuous_dev.continuous_loop import ContinuousAutonomousDevLoop
from sonic.continuous_dev.models import GenerationStatus
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_continuous_multi_generation_lifecycle():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)
        dev_loop = ContinuousAutonomousDevLoop(computer_provider=comp)

        # Execute 3-generation self-development cycle (v1 -> v2 -> v3)
        generations = await dev_loop.run_multi_generation_lifecycle(tenant_id="tenant-alpha")

        assert len(generations) == 2
        gen1, gen2 = generations[0], generations[1]

        # Gen 1 (v1.0 -> v2.0)
        assert gen1.version == "v2.0.0"
        assert gen1.parent_version == "v1.0.0"
        assert gen1.status == GenerationStatus.PROMOTED
        assert gen1.test_exit_code == 0
        assert gen1.security_violations == 0
        assert "stream_buffer.py" in gen1.files_modified
        assert gen1.latency_improvement_pct > 50.0

        # Gen 2 (v2.0 -> v3.0)
        assert gen2.version == "v3.0.0"
        assert gen2.parent_version == "v2.0.0"
        assert gen2.status == GenerationStatus.PROMOTED
        assert gen2.test_exit_code == 0
        assert gen2.security_violations == 0
        assert "query_cache.py" in gen2.files_modified
        assert gen2.latency_improvement_pct > 50.0

    asyncio.run(_run())
