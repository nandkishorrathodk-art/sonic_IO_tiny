"""
SONIC-REDA — Virtual Computer & Isolated Container Sandbox Engine
===================================================================
Provides safe, isolated environments where tools execute, files are manipulated,
and live targets are probed without endangering the host operating system.

Execution Providers:
    1. DockerSandbox: Direct Docker daemon container isolation (Linux /bin/bash)
    2. DaytonaSandbox: Remote/Cloud workspace daemon isolation
    3. LocalSandbox: Host OS fallback (LOCKED by default via allow_host_execution=False)
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import httpx

from sonic.logger import get_logger

logger = get_logger(__name__)


class WorkspaceState(StrEnum):
    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    DESTROYED = "destroyed"
    ERROR = "error"


@dataclass
class ExecResult:
    """Result of command execution in a virtual computer."""
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False


@dataclass
class FileInfo:
    """Metadata of a file in the virtual computer."""
    path: str
    name: str
    is_dir: bool
    size_bytes: int
    modified_at: str


@dataclass
class HomeWorkspace:
    """A per-tenant persistent "home" workspace (like Daytona's get_or_create_home)."""
    id: str
    workspace_root: str
    provider_type: str
    marker_path: str = ""
    name: str = "MISSION_COMPUTER"


class VirtualComputer(ABC):
    """Abstract interface for any virtual computer execution provider."""

    # ------------------------------------------------------------------
    # Tenanted persistent home workspace (Phase 2 / Persistent Body).
    # The being/engagement needs a long-lived per-tenant "home" like the
    # Daytona provider's get_or_create_home. Without one, the always-on life
    # loop aborts at boot (get_sandbox_provider returns a VirtualComputer
    # which never had that method) — the loop was dead-on-arrival.
    # friction-and-file based home so it works for every sandbox provider (no
    # provider-specific SDK): a marker file persists the tenant's workspace.

    _home_marker_prefix = ".sonic_home_"

    @abstractmethod
    async def initialize(self) -> bool:
        """Create and start the isolated environment."""
        pass

    @abstractmethod
    async def execute(
        self,
        command: str | list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 120,
    ) -> ExecResult:
        """Execute a command inside the virtual computer."""
        pass

    @abstractmethod
    async def read_file(self, path: str) -> str:
        """Read text content from a file inside the environment."""
        pass

    @abstractmethod
    async def write_file(self, path: str, content: str | bytes) -> bool:
        """Write content to a file inside the environment."""
        pass

    @abstractmethod
    async def list_files(self, path: str = ".") -> list[FileInfo]:
        """List files in a directory inside the environment."""
        pass

    @abstractmethod
    async def destroy(self) -> bool:
        """Destroy the workspace and free resources."""
        pass


# ============================================
# 1. Native Docker Container Sandbox (Primary)
# ============================================

class DockerSandbox(VirtualComputer):
    """
    Direct Docker-backed Sandbox.
    Spins up an isolated Linux container (Ubuntu/Debian) and runs all tools
    strictly inside the container's /bin/bash environment.
    """

    def __init__(
        self,
        container_name: str = "sonic-sandbox",
        image: str = "ubuntu:22.04",
        memory_limit: str = "2g",
        cpu_limit: str = "2.0",
    ):
        self.container_name = container_name
        self.image = image
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self.state = WorkspaceState.CREATING
        self._docker_available = bool(shutil.which("docker"))

    async def initialize(self) -> bool:
        """Ensure the Docker sandbox container is running."""
        if not self._docker_available:
            logger.warning("docker_not_found_on_path")
            self.state = WorkspaceState.ERROR
            return False

        try:
            # Check if container is already running
            check_proc = await asyncio.create_subprocess_exec(
                "docker", "inspect", "-f", "{{.State.Running}}", self.container_name,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await check_proc.communicate()
            if stdout.decode().strip() == "true":
                self.state = WorkspaceState.RUNNING
                logger.info("docker_sandbox_attached", name=self.container_name)
                return True

            # If stopped, remove old and start fresh
            await self.destroy()

            logger.info("docker_sandbox_creating", name=self.container_name, image=self.image)
            run_proc = await asyncio.create_subprocess_exec(
                "docker", "run", "-d",
                "--name", self.container_name,
                f"--memory={self.memory_limit}",
                f"--cpus={self.cpu_limit}",
                "--security-opt=no-new-privileges",
                self.image,
                "tail", "-f", "/dev/null",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await run_proc.communicate()

            if run_proc.returncode == 0:
                self.state = WorkspaceState.RUNNING
                logger.info("docker_sandbox_ready", name=self.container_name)
                return True
            else:
                self.state = WorkspaceState.ERROR
                return False
        except Exception as e:
            logger.error("docker_sandbox_init_failed", error=str(e))
            self.state = WorkspaceState.ERROR
            return False

    async def execute(
        self,
        command: str | list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 120,
    ) -> ExecResult:
        """Execute a command strictly inside the Docker container via /bin/bash."""
        cmd_str = command if isinstance(command, str) else " ".join(command)
        start_time = datetime.now(UTC)

        if self.state != WorkspaceState.RUNNING:
            ok = await self.initialize()
            if not ok:
                return ExecResult(
                    command=cmd_str, exit_code=1, stdout="",
                    stderr="ERROR: Docker sandbox container is not running.", duration_seconds=0
                )

        exec_args = ["docker", "exec"]
        if cwd:
            exec_args.extend(["-w", cwd])
        if env:
            for k, v in env.items():
                exec_args.extend(["-e", f"{k}={v}"])

        exec_args.extend([self.container_name, "/bin/bash", "-c", cmd_str])

        try:
            process = await asyncio.create_subprocess_exec(
                *exec_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            duration = (datetime.now(UTC) - start_time).total_seconds()
            return ExecResult(
                command=cmd_str,
                exit_code=process.returncode or 0,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                duration_seconds=round(duration, 2),
                timed_out=False,
            )
        except TimeoutError:
            return ExecResult(
                command=cmd_str, exit_code=-1, stdout="",
                stderr=f"TIMEOUT: Container execution exceeded {timeout}s", duration_seconds=timeout, timed_out=True
            )
        except Exception as e:
            return ExecResult(command=cmd_str, exit_code=-1, stdout="", stderr=str(e), duration_seconds=0)

    async def read_file(self, path: str) -> str:
        res = await self.execute(f"cat '{path}'")
        return res.stdout if res.exit_code == 0 else ""

    async def write_file(self, path: str, content: str | bytes) -> bool:
        escaped_content = content if isinstance(content, str) else content.decode("utf-8", errors="replace")
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", "-i", self.container_name, "/bin/bash", "-c", f"cat > '{path}'",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate(input=escaped_content.encode("utf-8"))
        return proc.returncode == 0

    async def list_files(self, path: str = ".") -> list[FileInfo]:
        res = await self.execute(f"ls -la '{path}'")
        if res.exit_code != 0:
            return []
        items = []
        for line in res.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 9:
                name = parts[8]
                if name in [".", ".."]:
                    continue
                is_dir = parts[0].startswith("d")
                size = int(parts[4]) if parts[4].isdigit() else 0
                items.append(FileInfo(path=f"{path}/{name}", name=name, is_dir=is_dir, size_bytes=size, modified_at=""))
        return items

    async def destroy(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", self.container_name,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            self.state = WorkspaceState.DESTROYED
            return True
        except Exception:
            return False

    async def get_or_create_home(self, tenant_id: str) -> Any:
        safe = tenant_id.replace("/", "_").replace("\\", "_")
        marker = f"/root/{self._home_marker_prefix}{safe}.json"
        await self.execute(f"mkdir -p /root && touch {marker}")
        return HomeWorkspace(
            id=f"docker-{safe}",
            workspace_root="/root",
            provider_type="docker",
            marker_path=marker,
        )


# ============================================
# 2. Daytona Remote Cloud Sandbox Provider
# ============================================

class DaytonaSandbox(VirtualComputer):
    """
    Daytona-backed Virtual Computer sandbox.
    Communicates with Daytona API daemon to spin up isolated cloud container workspaces.
    """

    def __init__(
        self,
        workspace_id: str = "sonic-workspace-01",
        api_url: str = "http://localhost:3986",
        api_key: str = "",
        image: str = "daytonaio/workspace-project:latest",
    ):
        self.workspace_id = workspace_id
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.image = image
        self.state = WorkspaceState.CREATING
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def initialize(self) -> bool:
        try:
            async with httpx.AsyncClient(base_url=self.api_url, headers=self._headers, timeout=15) as client:
                res = await client.post("/workspace", json={"id": self.workspace_id, "image": self.image})
                if res.status_code in [200, 201, 409]:
                    self.state = WorkspaceState.RUNNING
                    return True
        except Exception:
            pass
        self.state = WorkspaceState.ERROR
        return False

    async def execute(
        self,
        command: str | list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 120,
    ) -> ExecResult:
        cmd_str = command if isinstance(command, str) else " ".join(command)
        start_time = datetime.now(UTC)

        try:
            async with httpx.AsyncClient(base_url=self.api_url, headers=self._headers, timeout=timeout + 5) as client:
                res = await client.post(
                    f"/workspace/{self.workspace_id}/exec",
                    json={"command": cmd_str, "cwd": cwd, "env": env or {}},
                    timeout=timeout,
                )
                duration = (datetime.now(UTC) - start_time).total_seconds()
                if res.status_code == 200:
                    data = res.json()
                    return ExecResult(
                        command=cmd_str,
                        exit_code=data.get("exit_code", 0),
                        stdout=data.get("stdout", ""),
                        stderr=data.get("stderr", ""),
                        duration_seconds=round(duration, 2),
                    )
        except Exception as e:
            return ExecResult(command=cmd_str, exit_code=-1, stdout="", stderr=str(e), duration_seconds=0)

        return ExecResult(command=cmd_str, exit_code=-1, stdout="", stderr="Daytona execution failed", duration_seconds=0)

    async def read_file(self, path: str) -> str:
        try:
            async with httpx.AsyncClient(base_url=self.api_url, headers=self._headers, timeout=15) as client:
                res = await client.get(f"/workspace/{self.workspace_id}/files/read", params={"path": path})
                if res.status_code == 200:
                    return res.text
        except Exception:
            pass
        return ""

    async def write_file(self, path: str, content: str | bytes) -> bool:
        try:
            async with httpx.AsyncClient(base_url=self.api_url, headers=self._headers, timeout=15) as client:
                res = await client.post(
                    f"/workspace/{self.workspace_id}/files/write",
                    json={"path": path, "content": content if isinstance(content, str) else content.decode("latin1")},
                )
                return res.status_code == 200
        except Exception:
            return False

    async def list_files(self, path: str = ".") -> list[FileInfo]:
        return []

    async def destroy(self) -> bool:
        try:
            async with httpx.AsyncClient(base_url=self.api_url, headers=self._headers, timeout=15) as client:
                await client.delete(f"/workspace/{self.workspace_id}")
            self.state = WorkspaceState.DESTROYED
            return True
        except Exception:
            return False

    async def get_or_create_home(self, tenant_id: str) -> Any:
        safe = tenant_id.replace("/", "_").replace("\\", "_")
        marker = f"/root/{self._home_marker_prefix}{safe}.json"
        await self.execute(f"mkdir -p /root && touch {marker}")
        return HomeWorkspace(
            id=f"daytona-{safe}", workspace_root="/root", provider_type="daytona", marker_path=marker,
        )


# ============================================
# 3. Local Sandbox (LOCKED by default)
# ============================================

class LocalSandbox(VirtualComputer):
    """
    Host OS process execution.
    SECURITY LOCK: By default, allow_host_execution=False blocks all host commands
    to prevent accidental host compromise.
    """

    def __init__(self, allow_host_execution: bool = False):
        self.allow_host_execution = allow_host_execution
        self.state = WorkspaceState.RUNNING
        configured_dir = os.environ.get("SONIC_LOCAL_SANDBOX_DIR")
        self.base_dir = Path(configured_dir or (Path(tempfile.gettempdir()) / "sonic-local-sandbox")).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> bool:
        return True

    async def execute(
        self,
        command: str | list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 120,
    ) -> ExecResult:
        cmd_str = command if isinstance(command, str) else " ".join(command)

        if not self.allow_host_execution:
            msg = "BLOCKED BY SAFETY ENGINE: Direct host machine command execution is disabled. Please start Docker or Daytona sandbox."
            logger.warning("host_execution_blocked", command=cmd_str[:60])
            return ExecResult(
                command=cmd_str,
                exit_code=126,
                stdout="",
                stderr=msg,
                duration_seconds=0.0,
            )

        start_time = datetime.now(UTC)
        try:
            process = await asyncio.create_subprocess_shell(
                cmd_str,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env={**os.environ, **(env or {})},
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            duration = (datetime.now(UTC) - start_time).total_seconds()
            return ExecResult(
                command=cmd_str,
                exit_code=process.returncode or 0,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                duration_seconds=round(duration, 2),
            )
        except Exception as e:
            return ExecResult(command=cmd_str, exit_code=-1, stdout="", stderr=str(e), duration_seconds=0)

    async def read_file(self, path: str) -> str:
        p = Path(path)
        return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""

    async def write_file(self, path: str, content: str | bytes) -> bool:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            p.write_text(content, encoding="utf-8")
        else:
            p.write_bytes(content)
        return True

    async def list_files(self, path: str = ".") -> list[FileInfo]:
        p = Path(path)
        if not p.exists():
            return []
        return [
            FileInfo(
                path=str(c), name=c.name, is_dir=c.is_dir(),
                size_bytes=c.stat().st_size, modified_at=""
            )
            for c in p.iterdir()
        ]

    async def destroy(self) -> bool:
        return True

    async def get_or_create_home(self, tenant_id: str) -> Any:
        marker = Path(self.base_dir) / f"{self._home_marker_prefix}{tenant_id.replace('/', '_').replace('\\', '_')}_.json"
        marker.touch(exist_ok=True)
        return HomeWorkspace(
            id=f"local-{tenant_id}",
            workspace_root=str(self.base_dir),
            provider_type="local",
            marker_path=str(marker),
        )


# ============================================
# Smart Sandbox Provider Factory
# ============================================

async def get_sandbox_provider(
    container_name: str = "sonic-sandbox",
    allow_host_execution: bool = False,
) -> VirtualComputer:
    """
    Get the best available isolated sandbox.
    1. Checks Docker -> Returns DockerSandbox (Linux container)
    2. Checks Daytona -> Returns DaytonaSandbox
    3. Falls back to LocalSandbox with safety lock.
    """
    # 1. Try Docker Container
    if shutil.which("docker"):
        docker_sb = DockerSandbox(container_name=container_name)
        ok = await docker_sb.initialize()
        if ok:
            logger.info("sandbox_selected", provider="DockerSandbox", container=container_name)
            return docker_sb

    # 2. Try Daytona
    daytona_sb = DaytonaSandbox()
    ok = await daytona_sb.initialize()
    if ok:
        logger.info("sandbox_selected", provider="DaytonaSandbox")
        return daytona_sb

    # 3. Fallback to Safe Local Sandbox
    logger.warning("no_container_runtime_found", allow_host=allow_host_execution)
    return LocalSandbox(allow_host_execution=allow_host_execution)
