"""
Tests for Phase 18: End-to-End Continuous Production Proving.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.continuous_dev.continuous_loop import ContinuousAutonomousDevLoop
from sonic.continuous_dev.models import ContinuousDevTelemetryEvent, GenerationStatus
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_complete_e2e_continuous_production_lifecycle():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)
        dev_loop = ContinuousAutonomousDevLoop(computer_provider=comp)

        event = ContinuousDevTelemetryEvent(
            metric_name="payload_serializer_throughput_ops",
            observed_value=250.0,
            threshold=1000.0,
            anomaly_type="THROUGHPUT_DEGRADATION",
            target_subsystem="serializer",
        )
        patch = (
            "import json\n\n"
            "class Serializer:\n"
            "    @staticmethod\n"
            "    def dump(data: dict) -> str:\n"
            "        return json.dumps(data)\n"
        )
        cmd = "python -c 'from serializer import Serializer; assert Serializer.dump({\"a\": 1}) == \"{\\\"a\\\": 1}\"; print(\"SERIALIZER_OK\")'"

        gen = await dev_loop.advance_generation(
            tenant_id="tenant-alpha",
            current_version="v3.0.0",
            target_version="v4.0.0",
            telemetry_event=event,
            optimization_patch_code=patch,
            test_verification_command=cmd,
        )

        assert gen.version == "v4.0.0"
        assert gen.parent_version == "v3.0.0"
        assert gen.status == GenerationStatus.PROMOTED
        assert gen.test_exit_code == 0
        assert gen.security_violations == 0
        assert len(dev_loop.lineage) == 1

    asyncio.run(_run())
