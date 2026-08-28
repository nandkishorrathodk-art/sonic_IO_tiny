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
        ok_write = await comp.write_file(ws.id, "/home/sonic/workspace/auth.py", "def check(): return True")
        assert ok_write is True

        # 2. Read file
        content = await comp.read_file(ws.id, "/home/sonic/workspace/auth.py")
        assert "def check()" in content

        # 3. List files
        files = await comp.list_files(ws.id, "/home/sonic/workspace")
        assert len(files) >= 1

        # 4. Git status & branch
        status = await comp.git_action(ws.id, "status")
        assert status.branch == "main"

        branch_ok = await comp.git_action(ws.id, "branch", branch_name="fix-vuln-01")
        assert branch_ok is True

        commit_ok = await comp.git_action(ws.id, "commit", message="feat: add auth validation check")
        assert commit_ok is True

        await comp.destroy(ws.id)

    asyncio.run(_run())
