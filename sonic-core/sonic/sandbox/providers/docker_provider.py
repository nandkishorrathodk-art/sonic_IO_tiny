"""
SONIC-REDA — Docker Compute Provider (Local / Dev / Staging)
==============================================================
Manages isolated Docker container sandboxes for Kali/Debian execution.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from datetime import datetime, timezone
from typing import Optional

from sonic.logger import get_logger
from sonic.sandbox.provider import ComputeProvider, ExecResult, WorkspaceConfig, WorkspaceState

logger = get_logger(__name__)


class DockerProvider(ComputeProvider):
    """
    Provisions and executes commands inside isolated Docker containers.
    """

    def __init__(self, default_network: str = "sonic-sandbox-net"):
        self.default_network = default_network
        self._workspaces: dict[str, WorkspaceConfig] = {}
        self._states: dict[str, WorkspaceState] = {}

    async def create_workspace(self, config: WorkspaceConfig) -> bool:
        """Create and start a new container workspace."""
        if not shutil.which("docker"):
            logger.error("docker_binary_not_found")
            self._states[config.workspace_id] = WorkspaceState.ERROR
            return False

        self._workspaces[config.workspace_id] = config
        self._states[config.workspace_id] = WorkspaceState.CREATING

        cmd = [
            "docker", "run", "-d",
            "--name", config.workspace_id,
            "--memory", config.memory_limit,
            "--cpus", config.cpu_limit,
            "--security-opt", "no-new-privileges:true",
            "--label", f"tenant_id={config.tenant_id}",
            "--label", f"workspace_type={config.workspace_type.value}",
        ]

        if config.network_isolated:
            cmd.extend(["--network", self.default_network])

        for k, v in config.env_vars.items():
            cmd.extend(["-e", f"{k}={v}"])

        cmd.extend([config.image, "tail", "-f", "/dev/null"])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                self._states[config.workspace_id] = WorkspaceState.RUNNING
                logger.info("docker_workspace_created", workspace_id=config.workspace_id, image=config.image)
                return True
            else:
                logger.error("docker_run_failed", error=stderr.decode("utf-8", errors="replace"))
                self._states[config.workspace_id] = WorkspaceState.ERROR
                return False
        except Exception as e:
            logger.error("docker_create_exception", error=str(e))
            self._states[config.workspace_id] = WorkspaceState.ERROR
            return False

    async def execute(
        self,
        workspace_id: str,
        command: str | list[str],
        cwd: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
        timeout: int = 120,
    ) -> ExecResult:
        """Execute a command strictly inside the Docker container."""
        cmd_str = command if isinstance(command, str) else " ".join(command)
        start_time = datetime.now(timezone.utc)

        if self._states.get(workspace_id) != WorkspaceState.RUNNING:
            # Try to verify if container is already running
            if not await self._is_container_running(workspace_id):
                return ExecResult(
                    command=cmd_str,
                    exit_code=126,
                    stdout="",
                    stderr=f"FAIL-CLOSED: Workspace '{workspace_id}' is not running. Host fallback is prohibited.",
                    sandbox_id=workspace_id,
                )

        exec_args = ["docker", "exec"]
        if cwd:
            exec_args.extend(["-w", cwd])
        if env:
            for k, v in env.items():
                exec_args.extend(["-e", f"{k}={v}"])

        exec_args.extend([workspace_id, "/bin/bash", "-c", cmd_str])

        try:
            process = await asyncio.create_subprocess_exec(
                *exec_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return ExecResult(
                command=cmd_str,
                exit_code=process.returncode or 0,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                duration_seconds=round(duration, 2),
                timed_out=False,
                sandbox_id=workspace_id,
            )
        except asyncio.TimeoutError:
            return ExecResult(
                command=cmd_str,
                exit_code=-1,
                stdout="",
                stderr=f"TIMEOUT: Container execution exceeded {timeout}s",
                duration_seconds=timeout,
                timed_out=True,
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
        """Read file from container."""
        res = await self.execute(workspace_id, f"cat '{path}'")
        return res.stdout.encode("utf-8") if res.exit_code == 0 else b""

    async def write_file(self, workspace_id: str, path: str, data: bytes | str) -> bool:
        """Write file into container."""
        content = data if isinstance(data, str) else data.decode("utf-8", errors="replace")
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "exec", "-i", workspace_id, "/bin/bash", "-c", f"cat > '{path}'",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate(input=content.encode("utf-8"))
            return proc.returncode == 0
        except Exception:
            return False

    async def destroy_workspace(self, workspace_id: str) -> bool:
        """Remove container workspace."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", workspace_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            self._states[workspace_id] = WorkspaceState.DESTROYED
            self._workspaces.pop(workspace_id, None)
            logger.info("docker_workspace_destroyed", workspace_id=workspace_id)
            return True
        except Exception:
            return False

    async def get_state(self, workspace_id: str) -> WorkspaceState:
        """Check container status."""
        if await self._is_container_running(workspace_id):
            self._states[workspace_id] = WorkspaceState.RUNNING
            return WorkspaceState.RUNNING
        return self._states.get(workspace_id, WorkspaceState.STOPPED)

    async def _is_container_running(self, workspace_id: str) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "inspect", "-f", "{{.State.Running}}", workspace_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            return stdout.decode().strip() == "true"
        except Exception:
            return False
