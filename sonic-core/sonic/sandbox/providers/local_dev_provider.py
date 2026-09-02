"""
SONIC-REDA — Local Dev & Mock Sandbox Provider (Unit Testing Only)
=====================================================================
Strictly intended for offline unit tests with safety enforcement.
Blocks command execution by default unless explicit testing flag is active.
"""

from __future__ import annotations

import asyncio
import os
import signal
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from sonic.logger import get_logger
from sonic.sandbox.provider import ComputeProvider, ExecResult, WorkspaceConfig, WorkspaceState

logger = get_logger(__name__)


def _kill_process_group(process: asyncio.subprocess.Process) -> None:
    """Kill a subprocess and its entire process group on timeout.

    ``process.kill()`` only kills the immediate child (e.g. the shell), leaving
    grandchildren (e.g. ``sleep``) as orphans. Starting the subprocess with
    ``start_new_session=True`` puts it in its own process group whose PGID
    equals the child PID, so ``os.killpg`` can reap the whole tree.
    """
    try:
        pgid = os.getpgid(process.pid)
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except Exception as e:
        # Fall back to a direct kill if the group kill is not possible.
        logger.debug("killpg_failed", error=str(e))
        with suppress(ProcessLookupError):
            process.kill()
    # Reap the zombie. This is a blocking OS-level wait — safe because the
    # process was just SIGKILLed, so it exits immediately.
    with suppress(ChildProcessError):
        os.waitpid(process.pid, 0)


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
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 120,
    ) -> ExecResult:
        cmd_str = command if isinstance(command, str) else " ".join(command)
        start_time = datetime.now(UTC)

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
                # Start in a new process group so a timeout can kill the whole
                # tree (shell + children like `sleep`) instead of just the
                # shell, which would orphan the child.
                start_new_session=True,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except TimeoutError:
                # Kill the entire process group so child processes spawned by
                # the shell (e.g. `sleep`) do not leak as orphans.
                _kill_process_group(process)
                return ExecResult(
                    command=cmd_str,
                    exit_code=-1,
                    stdout="",
                    stderr=f"TIMEOUT: Execution exceeded {timeout}s",
                    duration_seconds=timeout,
                    timed_out=True,
                    sandbox_id=workspace_id,
                )
            duration = (datetime.now(UTC) - start_time).total_seconds()
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
