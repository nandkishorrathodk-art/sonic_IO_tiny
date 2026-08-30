"""
Adapter exposing a ``ComputerProvider`` (Daytona) as a ``ComputeProvider``.

The security tool adapters (nmap/nuclei/ffuf/http) are bound to the
``ComputeProvider`` interface (``.execute(workspace_id, command, timeout)``),
while the mission executor operates on a ``ComputerProvider`` (Daytona, with
``.terminal``). This thin adapter bridges the two so the real security scanners
can run against the same target sandbox the mission executor already uses —
without a second provisioning hierarchy.

Every command still runs strictly inside the resolved workspace (fail-closed:
the underlying ComputerProvider.terminal forbids host execution). This adapter
only translates the call signature; it adds no new execution path.
"""

from __future__ import annotations

from typing import Any, Optional

from sonic.sandbox.provider import ComputeProvider, ExecResult, WorkspaceConfig, WorkspaceState


class ComputerAsComputeProvider(ComputeProvider):
    """Wrap a ComputerProvider (Daytona) to satisfy the ComputeProvider contract."""

    def __init__(self, computer: Any):
        self._computer = computer

    async def execute(
        self,
        workspace_id: str,
        command: str | list[str],
        cwd: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
        timeout: int = 120,
    ) -> ExecResult:
        cmd = " ".join(command) if isinstance(command, list) else command
        if cwd:
            cmd = f"cd {cwd} && {cmd}"
        # ComputerProvider.terminal runs strictly inside the resolved sandbox.
        return await self._computer.terminal(workspace_id, cmd, timeout=timeout)

    async def create_workspace(self, config: WorkspaceConfig) -> WorkspaceState:
        raise NotImplementedError("Use the wrapped ComputerProvider for workspace creation")

    async def destroy_workspace(self, workspace_id: str) -> bool:
        raise NotImplementedError("Use the wrapped ComputerProvider for workspace destruction")

    async def read_file(self, workspace_id: str, path: str) -> bytes:
        content = await self._computer.read_file(workspace_id, path)
        return content.encode() if isinstance(content, str) else content

    async def write_file(self, workspace_id: str, path: str, data: bytes | str) -> bool:
        return await self._computer.write_file(workspace_id, path, data)
