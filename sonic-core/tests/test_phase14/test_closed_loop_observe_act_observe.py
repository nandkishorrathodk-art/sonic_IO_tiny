"""
Tests for Phase 14: Closed-Loop Observe -> Act -> Observe Cycle.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import ComputerActionType
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_closed_loop_observe_act_observe():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)
        ws = await comp.create(tenant_id="tenant-alpha", engagement_id="eng-alpha")

        agent = ComputerUseAgent(computer_provider=comp)

        # Step 1: Initial Observation
        obs1 = await agent.observe(ws.id)

        # Step 2: Choose action
        action_type, target, payload, expected = await agent.choose_action(
            "terminal: printf continuum-ok",
            obs1,
            1,
        )
        assert action_type == ComputerActionType.TERMINAL_EXEC

        # Step 3: Execute Action
        trace = await agent.execute_action(ws.id, action_type, target, payload, expected)
        assert trace.status == "SUCCESS"
        assert "continuum-ok" in trace.actual_observation

        # Step 4: Second Observation
        obs2 = await agent.observe(ws.id)
        assert obs2.screen.desktop_state == "NO_DISPLAY"

        await comp.destroy(ws.id)

    asyncio.run(_run())
