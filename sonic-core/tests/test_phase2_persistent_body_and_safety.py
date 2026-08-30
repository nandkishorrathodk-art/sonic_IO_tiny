"""
Phase 2 — Persistent Body + Safety verify tests (per PLAN Steps 2.0–2.4).

Proves the foundation's Body + Safety layer is real where it can be verified
without a live Daytona cloud desktop (which is environment-gated):

    2.0  Workstation state persists to disk and is reloaded on restart.
    2.1  get_or_create_home() reuses the persisted home instead of reprovisioning.
    2.3  Safety regression: host execution is hard-forced false outside dev,
         even when SONIC_ALLOW_HOST_EXECUTION=true is set. No host subprocess
         is reachable from the compute provider in production/staging.

The live end-to-end done-gate (Step 2.4: provision home -> screenshot ->
terminal -> restart -> re-attach) requires a real Daytona desktop and is
honestly skipped here when Daytona is unavailable (see conftest.py).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from sonic.computer.daytona_computer import DaytonaComputerProvider
from sonic.computer.models import (
    ComputerProfile, ComputerWorkspace, ComputerWorkspaceStatus, ComputerWorkspaceType,
)

# These tests exercise the provider's state-persistence, home-reuse, and
# safety logic only — no live Daytona sandbox is required.
pytestmark = pytest.mark.no_live_infra


@pytest.fixture()
def isolated_workstation_state(tmp_path, monkeypatch):
    state_file = str(tmp_path / "workstations.json")
    monkeypatch.setenv("SONIC_WORKSTATION_STATE_PATH", state_file)
    monkeypatch.setenv("SONIC_DATA_DIR", str(tmp_path))
    # No live Daytona in this env — ensure create() never silently succeeds.
    monkeypatch.delenv("DAYTONA_API_KEY", raising=False)
    monkeypatch.delenv("DAYTONA_SANDBOX_ID", raising=False)
    yield state_file


def test_workstation_state_persists_and_reloads(isolated_workstation_state):
    """A workspace created before restart is recoverable after restart (Step 2.0)."""
    state_file = isolated_workstation_state
    provider = DaytonaComputerProvider()
    # Simulate a successfully provisioned home desktop (no live API needed for
    # the state-persistence contract; we exercise the index, not the cloud).
    ws = ComputerWorkspace(
        id="ws-daytona-home-abc",
        tenant_id="tenant-A",
        engagement_id="home-tenant-A",
        workspace_type=ComputerWorkspaceType.MISSION_COMPUTER,
        profile=ComputerProfile.DEBIAN_ENGINEERING,
        provider_type="DaytonaComputerProvider",
        image="daytonaio/sandbox:0.9.0",
        status=ComputerWorkspaceStatus.READY,
    )
    provider.workspaces[ws.id] = ws
    provider._persist_state()

    # The state file exists and contains the workspace record.
    assert Path(state_file).exists()
    records = json.loads(Path(state_file).read_text())
    assert "ws-daytona-home-abc" in records
    assert records["ws-daytona-home-abc"]["tenant_id"] == "tenant-A"
    assert records["ws-daytona-home-abc"]["workspace_type"] == "MISSION_COMPUTER"

    # Simulate a restart: a brand-new provider instance loads the persisted state.
    provider_after = DaytonaComputerProvider()
    assert "ws-daytona-home-abc" in provider_after.workspaces
    recovered = provider_after.workspaces["ws-daytona-home-abc"]
    assert recovered.tenant_id == "tenant-A"
    assert recovered.workspace_type == ComputerWorkspaceType.MISSION_COMPUTER
    assert recovered.status == ComputerWorkspaceStatus.READY
    assert recovered.image == "daytonaio/sandbox:0.9.0"


def test_get_or_create_home_reuses_persisted_home(isolated_workstation_state):
    """get_or_create_home returns the existing home instead of reprovisioning (Step 2.1)."""
    import asyncio

    provider = DaytonaComputerProvider()
    ws = ComputerWorkspace(
        id="ws-home-existing",
        tenant_id="tenant-B",
        engagement_id="home-tenant-B",
        workspace_type=ComputerWorkspaceType.MISSION_COMPUTER,
        profile=ComputerProfile.DEBIAN_ENGINEERING,
        provider_type="DaytonaComputerProvider",
        image="daytonaio/sandbox:0.9.0",
        status=ComputerWorkspaceStatus.READY,
    )
    provider.workspaces[ws.id] = ws
    provider._persist_state()

    # New process: load state, then ask for the home. It MUST reuse, not create.
    provider_after = DaytonaComputerProvider()
    # Patch create to fail loudly if it is ever called (reuse path must NOT provision).
    called = {"create": False}

    async def boom(*a, **k):
        called["create"] = True
        raise AssertionError("get_or_create_home should reuse the existing home, not call create()")

    provider_after.create = boom  # type: ignore[method-assign]

    home = asyncio.new_event_loop().run_until_complete(
        provider_after.get_or_create_home("tenant-B")
    )
    assert called["create"] is False, "Home was reprovisioned instead of reused"
    assert home.id == "ws-home-existing"
    assert home.tenant_id == "tenant-B"


def test_get_or_create_home_is_tenant_scoped(isolated_workstation_state):
    """A home persisted for tenant-A is not returned as tenant-B's home."""
    import asyncio

    provider = DaytonaComputerProvider()
    ws = ComputerWorkspace(
        id="ws-home-A",
        tenant_id="tenant-A",
        engagement_id="home-tenant-A",
        workspace_type=ComputerWorkspaceType.MISSION_COMPUTER,
        profile=ComputerProfile.DEBIAN_ENGINEERING,
        provider_type="DaytonaComputerProvider",
        image="daytonaio/sandbox:0.9.0",
        status=ComputerWorkspaceStatus.READY,
    )
    provider.workspaces[ws.id] = ws
    provider._persist_state()

    provider_after = DaytonaComputerProvider()
    # tenant-B has no home; create() would be required. Patch it to raise so we
    # prove tenant-B did NOT pick up tenant-A's home.
    async def boom(*a, **k):
        raise AssertionError("tenant-B should not reuse tenant-A's home")

    provider_after.create = boom  # type: ignore[method-assign]
    with pytest.raises(AssertionError):
        asyncio.new_event_loop().run_until_complete(
            provider_after.get_or_create_home("tenant-B")
        )


# ---------------------------------------------------------------------------
# Step 2.3 — Safety regression (no host execution outside dev)
# ---------------------------------------------------------------------------

def test_host_execution_forced_false_in_production(monkeypatch):
    """SONIC_ALLOW_HOST_EXECUTION=true is hard-forced false outside dev."""
    from sonic.config import get_settings
    from sonic.sandbox import factory

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SONIC_ALLOW_HOST_EXECUTION", "true")
    # Force LocalDev path (no docker, no daytona).
    monkeypatch.setenv("SONIC_COMPUTE_PROVIDER", "local")
    monkeypatch.delenv("DAYTONA_API_KEY", raising=False)
    monkeypatch.delenv("DAYTONA_API_URL", raising=False)
    monkeypatch.setattr("shutil.which", lambda *_: None)
    get_settings.cache_clear()
    factory._active_provider = None  # reset singleton

    provider = factory.get_compute_provider()
    assert provider.allow_host_execution is False, (
        "Host execution must be fail-closed false in production even when "
        "SONIC_ALLOW_HOST_EXECUTION=true is set."
    )
    get_settings.cache_clear()
    factory._active_provider = None


def test_host_execution_blocked_when_disabled():
    """LocalDevProvider.execute refuses to run host commands when disabled."""
    import asyncio

    from sonic.sandbox.providers.local_dev_provider import LocalDevProvider

    provider = LocalDevProvider(allow_host_execution=False)
    # execute() must NOT spawn a host subprocess; it returns a blocked result.
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(provider.execute("ws-test", "whoami", timeout=5))
    finally:
        loop.close()
    # The provider signals refusal (non-zero exit + fail-closed stderr) — never real host stdout.
    assert result is not None
    assert result.exit_code == 126
    assert "FAIL-CLOSED" in result.stderr


# ---------------------------------------------------------------------------
# Step 2.2 — Screenshot/render guarantee (verify-only, code path check)
# ---------------------------------------------------------------------------

def test_computer_use_start_is_in_every_provisioning_path():
    """computer_use.start() is called on both create() and _resolve_sandbox().

    This is a static guarantee that no provisioning path can return a sandbox
    whose VNC/desktop stack was never started (which would yield NO_DISPLAY).
    """
    import inspect
    src = inspect.getsource(DaytonaComputerProvider.create)
    assert "computer_use.start()" in src, "create() must start computer_use"
    src_resolve = inspect.getsource(DaytonaComputerProvider._resolve_sandbox)
    assert "computer_use.start()" in src_resolve, "_resolve_sandbox() must start computer_use"
