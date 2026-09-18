"""
Tests for Phase 13: Filesystem & Git Operations.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_filesystem_crud_and_git_operations():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)

        ws = await comp.create(tenant_id="tenant-alpha", engagement_id="eng-alpha")

        # 1. Write file
        ok_write = await comp.write_file(ws.id, "/workspace/continuum.py", "def check(): return True")
        assert ok_write is True

        # 2. Read file
        content = await comp.read_file(ws.id, "/workspace/continuum.py")
        assert "def check()" in content

        # 3. List files
        files = await comp.list_files(ws.id, "/workspace")
        assert len(files) >= 1

        # 4. Git status & branch
        status = await comp.git_action(ws.id, "status")
        assert status is not None

        await comp.destroy(ws.id)

    asyncio.run(_run())
