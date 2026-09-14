"""
Adapter exposing a ``ComputerProvider`` (Daytona) as a ``ComputeProvider``.

Explicitly registered security capabilities are bound to the
``ComputeProvider`` interface (``.execute(workspace_id, command, timeout)``),
while the mission executor operates on a ``ComputerProvider`` (Daytona, with
``.terminal``). This thin adapter bridges the two so registered capabilities
can run against the same target sandbox the mission executor already uses —
without a second provisioning hierarchy.

Every command still runs strictly inside the resolved workspace (fail-closed:
the underlying ComputerProvider.terminal forbids host execution). This adapter
only translates the call signature; it adds no new execution path.
"""

from __future__ import annotations

from typing import Any

from sonic.computer.models import ComputerWorkspaceStatus
from sonic.sandbox.provider import ComputeProvider, ExecResult, WorkspaceConfig, WorkspaceState


_STATUS_MAP = {
    ComputerWorkspaceStatus.CREATING: WorkspaceState.CREATING,
    ComputerWorkspaceStatus.STARTING: WorkspaceState.CREATING,
    ComputerWorkspaceStatus.READY: WorkspaceState.RUNNING,
    ComputerWorkspaceStatus.RUNNING: WorkspaceState.RUNNING,
    ComputerWorkspaceStatus.STOPPED: WorkspaceState.STOPPED,
    ComputerWorkspaceStatus.DEGRADED: WorkspaceState.ERROR,
    ComputerWorkspaceStatus.DESTROYING: WorkspaceState.STOPPED,
    ComputerWorkspaceStatus.DESTROYED: WorkspaceState.DESTROYED,
    ComputerWorkspaceStatus.FAILED: WorkspaceState.ERROR,
}


class ComputerAsComputeProvider(ComputeProvider):
    """Wrap a ComputerProvider (Daytona) to satisfy the ComputeProvider contract."""

    def __init__(self, computer: Any):
        self._computer = computer

    async def execute(
        self,
        workspace_id: str,
        command: str | list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 120,
    ) -> ExecResult:
        cmd = " ".join(command) if isinstance(command, list) else command
        if cwd:
            cmd = f"cd {cwd} && {cmd}"
        # ComputerProvider.terminal runs strictly inside the resolved sandbox.
        return await self._computer.terminal(workspace_id, cmd, timeout=timeout)

    async def create_workspace(self, config: WorkspaceConfig) -> bool:
        # Delegate to the wrapped ComputerProvider; the caller is responsible for
        # provisioning (it already created the target sandbox this adapter runs in).
        return True

    async def destroy_workspace(self, workspace_id: str) -> bool:
        return await self._computer.destroy(workspace_id)

    async def get_state(self, workspace_id: str) -> WorkspaceState:
        try:
            state = await self._computer.status(workspace_id)
            return _STATUS_MAP.get(state.status, WorkspaceState.ERROR)
        except Exception:
            return WorkspaceState.ERROR

    async def read_file(self, workspace_id: str, path: str) -> bytes:
        content = await self._computer.read_file(workspace_id, path)
        return content.encode() if isinstance(content, str) else content

    async def write_file(self, workspace_id: str, path: str, data: bytes | str) -> bool:
        return await self._computer.write_file(workspace_id, path, data)
