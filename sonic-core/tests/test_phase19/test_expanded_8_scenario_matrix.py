"""
Tests for Phase 19: Expanded 8-Domain Architectural Scenario Matrix.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.production_gate.models import ScenarioDomain, ScenarioExecutionResult
from sonic.production_gate.scenario_matrix import ScenarioMatrixRunner
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_individual_scenarios_in_matrix():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)

        # 1. Concurrency Race
        r1 = await ScenarioMatrixRunner.run_scenario_1_concurrency_race(comp, "tenant-scen-1")
        assert r1.domain == ScenarioDomain.CONCURRENCY_RACE
        assert r1.success is True

        # 2. Async Memory Leak
        r2 = await ScenarioMatrixRunner.run_scenario_2_async_memory_leak(comp, "tenant-scen-2")
        assert r2.domain == ScenarioDomain.ASYNC_MEMORY_LEAK
        assert r2.success is True

        # 3. Cryptographic Replay
        r3 = await ScenarioMatrixRunner.run_scenario_3_cryptographic_replay(comp, "tenant-scen-3")
        assert r3.domain == ScenarioDomain.CRYPTOGRAPHIC_REPLAY
        assert r3.success is True

        # 4. Connection Pooling
        r4 = await ScenarioMatrixRunner.run_scenario_4_connection_pooling(comp, "tenant-scen-4")
        assert r4.domain == ScenarioDomain.CONNECTION_POOLING
        assert r4.success is True

        # 5. AST Parser Recursion
        r5 = await ScenarioMatrixRunner.run_scenario_5_ast_parser_recursion(comp, "tenant-scen-5")
        assert r5.domain == ScenarioDomain.AST_PARSER_RECURSION
        assert r5.success is True

        # 6. Rate Limiter Off-by-One
        r6 = await ScenarioMatrixRunner.run_scenario_6_rate_limiter_off_by_one(comp, "tenant-scen-6")
        assert r6.domain == ScenarioDomain.RATE_LIMITER_OFF_BY_ONE
        assert r6.success is True

        # 7. Distributed Deadlock
        r7 = await ScenarioMatrixRunner.run_scenario_7_distributed_deadlock(comp, "tenant-scen-7")
        assert r7.domain == ScenarioDomain.DISTRIBUTED_DEADLOCK
        assert r7.success is True

        # 8. Protocol Framing
        r8 = await ScenarioMatrixRunner.run_scenario_8_protocol_framing(comp, "tenant-scen-8")
        assert r8.domain == ScenarioDomain.PROTOCOL_FRAMING
        assert r8.success is True

    asyncio.run(_run())
