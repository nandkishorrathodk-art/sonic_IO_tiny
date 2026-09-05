"""
SONIC-REDA — Docker Container Graphical Sandbox Adapter
======================================================
Provides a direct Daytona-compatible Sandbox interface to a local or remote
Docker desktop container (e.g. sonic-desktop-workstation).
Allows DaytonaComputerProvider to seamlessly drive local containers when
Daytona Cloud is offline, unconfigured, or in development/self-host mode.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
from typing import Any

from sonic.logger import get_logger

logger = get_logger(__name__)


class DockerProcessResult:
    def __init__(self, exit_code: int, result: str, error: str = ""):
        self.exit_code = exit_code
        self.result = result
        self.error = error
        self.stdout = result
        self.stderr = error


class DockerContainerProcess:
    def __init__(self, container_name: str):
        self.container_name = container_name

    async def exec(self, cmd: str, timeout: int | None = None) -> DockerProcessResult:
        if not shutil.which("docker"):
            return DockerProcessResult(exit_code=127, result="", error="docker binary not found on host")
        try:
            exec_args = ["docker", "exec", self.container_name, "bash", "-c", cmd]
            proc = await asyncio.create_subprocess_exec(
                *exec_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_data, stderr_data = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout if timeout and timeout > 0 else 60,
            )
            return DockerProcessResult(
                exit_code=proc.returncode if proc.returncode is not None else 0,
                result=stdout_data.decode("utf-8", errors="replace"),
                error=stderr_data.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            return DockerProcessResult(exit_code=124, result="", error="Command timed out")
        except Exception as e:
            return DockerProcessResult(exit_code=1, result="", error=str(e))


class DockerContainerFs:
    def __init__(self, container_name: str):
        self.container_name = container_name

    async def download_file(self, path: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", self.container_name, "cat", path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await proc.communicate()
        return out.decode("utf-8", errors="replace")

    async def upload_file(self, src: bytes, dst: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", "-i", self.container_name, "sh", "-c", f"cat > {shlex.quote(dst)}",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate(input=src)


class DockerContainerPreview:
    def __init__(self, port: int = 6080):
        self.url = f"http://localhost:{port}/vnc.html"
        self.token = None


class DockerContainerSandbox:
    """A Daytona Sandbox compatible duck-typed object wrapping a Docker desktop container."""

    def __init__(self, container_name: str = "sonic-desktop-workstation"):
        self.id = container_name
        self.state = "started"
        self.process = DockerContainerProcess(container_name)
        self.fs = DockerContainerFs(container_name)

    async def get_preview_link(self, port: int = 6080) -> DockerContainerPreview:
        return DockerContainerPreview(port)

    async def delete(self) -> None:
        pass

