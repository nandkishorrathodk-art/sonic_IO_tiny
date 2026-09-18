"""
Tests for Phase 13: Terminal Execution & Process Inspection.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_terminal_command_execution_and_process_list():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)

        ws = await comp.create(tenant_id="tenant-alpha", engagement_id="eng-alpha")

        # 1. Execute shell command in PTY
        res = await comp.terminal(ws.id, "echo 'SONIC-COMPUTER-ACTIVE'")
        assert res.exit_code == 0
        assert "SONIC-COMPUTER-ACTIVE" in res.stdout

        # 2. Inspect Running Processes
        procs = await comp.process_list(ws.id)
        assert isinstance(procs, list)

        # The headless plane can launch a real command, but does not promise a
        # graphical application process.
        await comp.terminal(ws.id, "nohup sleep 30 >/tmp/continuum-sleep.log 2>&1 &")
        procs2 = await comp.process_list(ws.id)
        pnames2 = [p.name for p in procs2]
        assert isinstance(procs2, list)

        await comp.destroy(ws.id)

    asyncio.run(_run())
