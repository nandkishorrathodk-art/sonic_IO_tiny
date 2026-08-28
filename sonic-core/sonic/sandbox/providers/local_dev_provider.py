"""
SONIC-REDA — Local Dev & Mock Sandbox Provider (Unit Testing Only)
=====================================================================
Strictly intended for offline unit tests with safety enforcement.
Blocks command execution by default unless explicit testing flag is active.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sonic.logger import get_logger
from sonic.sandbox.provider import ComputeProvider, ExecResult, WorkspaceConfig, WorkspaceState

logger = get_logger(__name__)


class LocalDevProvider(ComputeProvider):
    """
    Test-only sandbox provider. By default, refuses to execute commands on host.
    """

    def __init__(self, allow_host_execution: bool = False):
        self.allow_host_execution = allow_host_execution
        self._workspaces: dict[str, WorkspaceConfig] = {}
        self._states: dict[str, WorkspaceState] = {}
        self._mock_fs: dict[str, dict[str, bytes]] = {}

    async def create_workspace(self, config: WorkspaceConfig) -> bool:
        self._workspaces[config.workspace_id] = config
        self._states[config.workspace_id] = WorkspaceState.RUNNING
        self._mock_fs[config.workspace_id] = {}
        return True

    async def execute(
        self,
        workspace_id: str,
        command: str | list[str],
        cwd: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
        timeout: int = 120,
    ) -> ExecResult:
        cmd_str = command if isinstance(command, str) else " ".join(command)
        start_time = datetime.now(timezone.utc)

        # Strict safety check
        if not self.allow_host_execution:
            logger.warning("host_command_blocked_by_safety", command=cmd_str[:60])
            return ExecResult(
                command=cmd_str,
                exit_code=126,
                stdout="",
                stderr="FAIL-CLOSED: Host execution is strictly blocked by SONIC safety engine.",
                sandbox_id=workspace_id,
            )

        try:
            process = await asyncio.create_subprocess_shell(
                cmd_str,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env={**os.environ, **(env or {})},
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return ExecResult(
                command=cmd_str,
                exit_code=process.returncode or 0,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                duration_seconds=round(duration, 2),
                sandbox_id=workspace_id,
            )
        except Exception as e:
            return ExecResult(
                command=cmd_str,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                sandbox_id=workspace_id,
            )

    async def read_file(self, workspace_id: str, path: str) -> bytes:
        ws_fs = self._mock_fs.get(workspace_id, {})
        if path in ws_fs:
            return ws_fs[path]
        if self.allow_host_execution and os.path.exists(path):
            return Path(path).read_bytes()
        return b""

    async def write_file(self, workspace_id: str, path: str, data: bytes | str) -> bool:
        content = data.encode("utf-8") if isinstance(data, str) else data
        if workspace_id not in self._mock_fs:
            self._mock_fs[workspace_id] = {}
        self._mock_fs[workspace_id][path] = content
        if self.allow_host_execution:
            try:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                Path(path).write_bytes(content)
            except Exception:
                pass
        return True

    async def destroy_workspace(self, workspace_id: str) -> bool:
        self._states[workspace_id] = WorkspaceState.DESTROYED
        self._workspaces.pop(workspace_id, None)
        self._mock_fs.pop(workspace_id, None)
        return True

    async def get_state(self, workspace_id: str) -> WorkspaceState:
        return self._states.get(workspace_id, WorkspaceState.STOPPED)
