"""
Tests for Phase 13: ComputerProvider Lifecycle, State & Audit.
"""

import asyncio
import pytest
from sonic.computer.models import ComputerProfile, ComputerWorkspaceStatus, ComputerWorkspaceType
from sonic.computer.provider import UnifiedComputerProvider
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_computer_lifecycle_create_status_destroy():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)

        # 1. Create Computer
        ws = await comp.create(
            tenant_id="tenant-alpha",
            engagement_id="eng-alpha",
            workspace_type=ComputerWorkspaceType.MISSION_COMPUTER,
            profile=ComputerProfile.KALI_SECURITY,
        )
        assert ws.status == ComputerWorkspaceStatus.READY
        assert ws.id in comp.workspaces

        # 2. Get Status
        st = await comp.status(ws.id)
        assert st.workspace_id == ws.id
        assert st.tenant_id == "tenant-alpha"
        assert "Desktop" in st.open_applications

        # 3. Verify Audit Log
        assert len(comp.audit_log) >= 1
        assert comp.audit_log[-1].action == "CREATE_COMPUTER"

        # 4. Destroy Computer
        ok = await comp.destroy(ws.id)
        assert ok is True
        assert ws.id not in comp.workspaces

    asyncio.run(_run())
