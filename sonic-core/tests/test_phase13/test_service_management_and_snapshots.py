"""
Tests for Phase 13: Service Management & Computer Snapshots.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_service_management_and_snapshots():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)

        ws = await comp.create(tenant_id="tenant-alpha", engagement_id="eng-alpha")

        # 1. Manage Service (start, stop, restart)
        svc_restart = await comp.service_action(ws.id, "continuum-service", "restart")
        assert svc_restart.status == "RESTART"

        svc_stop = await comp.service_action(ws.id, "continuum-service", "stop")
        assert svc_stop.status == "STOP"

        # 2. Snapshot Workspace
        snap_id = await comp.snapshot_workspace(ws.id, name="stable-baseline")
        assert snap_id.startswith("snap-")

        # 3. Restore Snapshot
        restored = await comp.restore_snapshot(snap_id)
        assert restored is True

        await comp.destroy(ws.id)

    asyncio.run(_run())
