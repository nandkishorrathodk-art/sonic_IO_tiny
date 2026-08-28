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
        assert len(procs) >= 2
        pnames = [p.name for p in procs]
        assert "systemd/init" in pnames
        assert "Xvfb" in pnames

        # 3. Launch App and check process list updates
        await comp.launch_application(ws.id, "chromium")
        procs2 = await comp.process_list(ws.id)
        pnames2 = [p.name for p in procs2]
        assert "chromium" in pnames2

        await comp.destroy(ws.id)

    asyncio.run(_run())
