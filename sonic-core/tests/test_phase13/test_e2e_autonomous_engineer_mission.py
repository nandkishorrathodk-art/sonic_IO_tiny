"""
Tests for Phase 13: End-to-End Autonomous Engineer Mission Workflow.
"""

import asyncio
import pytest
from sonic.computer.models import ComputerProfile, ComputerWorkspaceType
from sonic.computer.provider import UnifiedComputerProvider
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_complete_autonomous_engineer_mission_workflow():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)

        # 1. Provision Persistent Mission Computer
        ws = await comp.create(
            tenant_id="tenant-e2e",
            engagement_id="eng-e2e-01",
            workspace_type=ComputerWorkspaceType.MISSION_COMPUTER,
            profile=ComputerProfile.KALI_SECURITY,
        )

        # 2. Inspect the headless sandbox filesystem
        files = await comp.list_files(ws.id, "/workspace")
        assert isinstance(files, list)

        # 3. Write and verify a generic workspace artifact
        write_ok = await comp.write_file(ws.id, "/workspace/continuum_note.txt", "foundation complete\n")
        assert write_ok is True

        # 4. Run a real command inside the sandbox
        test_res = await comp.terminal(ws.id, "cat /workspace/continuum_note.txt")
        assert test_res.exit_code == 0
        assert "foundation complete" in test_res.stdout

        # 5. Git status remains a real provider result even without a mounted
        # repository in this isolated workspace.
        assert await comp.git_action(ws.id, "status") is not None

        destroyed = await comp.destroy(ws.id)
        assert destroyed is True

    asyncio.run(_run())
