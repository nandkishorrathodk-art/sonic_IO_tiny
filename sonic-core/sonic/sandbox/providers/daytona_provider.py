"""
SONIC-REDA — Daytona Remote Cloud Compute Provider (Production SDK)
=====================================================================
Integrates with the official Daytona Cloud / Self-Hosted SDK (`daytona` package)
to provision, execute inside, transfer files, inspect, and destroy isolated cloud Linux sandboxes.

FAIL-CLOSED INVARIANT:
    If Daytona API is unreachable or fails, the system FAILS CLOSED.
    It NEVER falls back to host OS execution.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Optional

from sonic.logger import get_logger
from sonic.sandbox.provider import ComputeProvider, ExecResult, WorkspaceConfig, WorkspaceState

logger = get_logger(__name__)


class DaytonaProvider(ComputeProvider):
    """
    Provisions and executes commands inside remote Daytona cloud sandboxes
    using the official Daytona Python SDK.
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        target: Optional[str] = None,
    ):
        self.api_url = api_url or os.environ.get("DAYTONA_API_URL")
        self.api_key = api_key or os.environ.get("DAYTONA_API_KEY", "")
        self.target = target or os.environ.get("DAYTONA_TARGET")
        self._states: dict[str, WorkspaceState] = {}
        self._sandboxes: dict[str, Any] = {}
        self._async_client = None

    def _get_client(self):
        """Lazy load and configure the AsyncDaytona SDK client."""
        if self._async_client is None:
            try:
                from daytona import AsyncDaytona, DaytonaConfig
                config_kwargs = {}
                if self.api_key:
                    config_kwargs["api_key"] = self.api_key
                if self.api_url:
                    config_kwargs["server_url"] = self.api_url
                if self.target:
                    config_kwargs["target"] = self.target

                config = DaytonaConfig(**config_kwargs) if config_kwargs else None
                self._async_client = AsyncDaytona(config=config)
                logger.info("daytona_sdk_client_initialized", has_api_key=bool(self.api_key))
            except Exception as e:
                logger.error("daytona_sdk_init_failed", error=str(e))
                self._async_client = None
        return self._async_client

    async def create_workspace(self, config: WorkspaceConfig) -> bool:
        """Create and start a new Daytona cloud sandbox."""
        client = self._get_client()
        if not client:
            logger.error("daytona_client_unavailable_fail_closed")
            self._states[config.workspace_id] = WorkspaceState.ERROR
            return False

        self._states[config.workspace_id] = WorkspaceState.CREATING

        try:
            from daytona import CreateSandboxFromImageParams

            params = CreateSandboxFromImageParams(
                name=config.workspace_id,
                image=config.image if config.image and ":" in config.image else "daytonaio/sandbox:0.8.0",
                env_vars=config.env_vars,
                labels={
                    "tenant_id": config.tenant_id,
                    "workspace_type": config.workspace_type.value,
                    "managed_by": "sonic-reda",
                },
                auto_stop_interval=15,  # 15 min auto-stop
            )

            sandbox = await client.create(params, timeout=120)
            if sandbox:
                sandbox_id = getattr(sandbox, "id", config.workspace_id)
                self._sandboxes[config.workspace_id] = sandbox
                self._sandboxes[sandbox_id] = sandbox
                self._states[config.workspace_id] = WorkspaceState.RUNNING
                self._states[sandbox_id] = WorkspaceState.RUNNING
                logger.info(
                    "daytona_sandbox_created",
                    workspace_id=config.workspace_id,
                    sandbox_id=sandbox_id,
                )
                return True
            else:
                self._states[config.workspace_id] = WorkspaceState.ERROR
                return False
        except Exception as e:
            logger.error("daytona_create_sandbox_failed", error=str(e), workspace_id=config.workspace_id)
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
        """Execute a command strictly inside the Daytona remote sandbox."""
        cmd_str = command if isinstance(command, str) else " ".join(command)
        start_time = datetime.now(timezone.utc)

        client = self._get_client()
        if not client:
            return ExecResult(
                command=cmd_str,
                exit_code=126,
                stdout="",
                stderr="FAIL-CLOSED: Daytona SDK client unavailable. Host fallback is prohibited.",
                sandbox_id=workspace_id,
            )

        try:
            # 1. Fetch sandbox instance
            sandbox = self._sandboxes.get(workspace_id)
            if not sandbox:
                try:
                    sandbox = await client.get(workspace_id)
                    if sandbox:
                        self._sandboxes[workspace_id] = sandbox
                except Exception as get_err:
                    logger.warning("daytona_get_sandbox_lookup_failed", error=str(get_err))

            if not sandbox:
                return ExecResult(
                    command=cmd_str,
                    exit_code=126,
                    stdout="",
                    stderr=f"FAIL-CLOSED: Daytona sandbox '{workspace_id}' not found or unreachable. Host fallback is prohibited.",
                    sandbox_id=workspace_id,
                )

            # 2. Execute process via Daytona SDK
            exec_response = await sandbox.process.exec(
                command=cmd_str,
                cwd=cwd,
                env=env,
                timeout=timeout,
            )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            stdout_res = getattr(exec_response, "result", "") or ""
            exit_code = getattr(exec_response, "exit_code", 0)

            return ExecResult(
                command=cmd_str,
                exit_code=exit_code,
                stdout=stdout_res,
                stderr="" if exit_code == 0 else stdout_res,
                duration_seconds=round(duration, 2),
                sandbox_id=workspace_id,
            )

        except asyncio.TimeoutError:
            return ExecResult(
                command=cmd_str,
                exit_code=-1,
                stdout="",
                stderr=f"TIMEOUT: Daytona execution exceeded {timeout}s",
                duration_seconds=timeout,
                timed_out=True,
                sandbox_id=workspace_id,
            )
        except Exception as e:
            logger.error("daytona_exec_exception", error=str(e), workspace_id=workspace_id)
            return ExecResult(
                command=cmd_str,
                exit_code=126,
                stdout="",
                stderr=f"FAIL-CLOSED: Daytona execution failed ({str(e)}). Host fallback is prohibited.",
                sandbox_id=workspace_id,
            )

    async def read_file(self, workspace_id: str, path: str) -> bytes:
        """Read a file from the remote Daytona sandbox filesystem."""
        try:
            client = self._get_client()
            sandbox = self._sandboxes.get(workspace_id)
            if not sandbox and client:
                sandbox = await client.get(workspace_id)

            if sandbox and hasattr(sandbox, "fs") and hasattr(sandbox.fs, "download_file"):
                data = await sandbox.fs.download_file(path)
                return data if data is not None else b""
            else:
                # Fallback to cat command inside sandbox
                res = await self.execute(workspace_id, f"cat '{path}'")
                return res.stdout.encode("utf-8") if res.exit_code == 0 else b""
        except Exception as e:
            logger.error("daytona_read_file_error", path=path, error=str(e))
            # Fallback to cat command inside sandbox
            res = await self.execute(workspace_id, f"cat '{path}'")
            return res.stdout.encode("utf-8") if res.exit_code == 0 else b""

    async def write_file(self, workspace_id: str, path: str, data: bytes | str) -> bool:
        """Write a file into the remote Daytona sandbox filesystem."""
        try:
            client = self._get_client()
            sandbox = self._sandboxes.get(workspace_id)
            if not sandbox and client:
                sandbox = await client.get(workspace_id)

            content_bytes = data.encode("utf-8") if isinstance(data, str) else data

            if sandbox and hasattr(sandbox, "fs") and hasattr(sandbox.fs, "upload_file"):
                await sandbox.fs.upload_file(src=content_bytes, dst=path)
                return True
            else:
                # Fallback to base64 echo inside sandbox
                import base64
                b64_content = base64.b64encode(content_bytes).decode("ascii")
                res = await self.execute(
                    workspace_id,
                    f"mkdir -p $(dirname '{path}') && echo '{b64_content}' | base64 -d > '{path}'",
                )
                return res.exit_code == 0
        except Exception as e:
            logger.error("daytona_write_file_error", path=path, error=str(e))
            # Fallback to base64 echo inside sandbox
            import base64
            content_bytes = data.encode("utf-8") if isinstance(data, str) else data
            b64_content = base64.b64encode(content_bytes).decode("ascii")
            res = await self.execute(
                workspace_id,
                f"mkdir -p $(dirname '{path}') && echo '{b64_content}' | base64 -d > '{path}'",
            )
            return res.exit_code == 0


    async def destroy_workspace(self, workspace_id: str) -> bool:
        """Delete/terminate a Daytona cloud sandbox."""
        client = self._get_client()
        if not client:
            return False

        try:
            sandbox = self._sandboxes.pop(workspace_id, None)
            if sandbox and hasattr(sandbox, "delete"):
                await sandbox.delete()
            else:
                await client.delete(workspace_id)

            self._states[workspace_id] = WorkspaceState.DESTROYED
            logger.info("daytona_sandbox_destroyed", workspace_id=workspace_id)
            return True
        except Exception as e:
            logger.warning("daytona_destroy_error", error=str(e))
            self._states[workspace_id] = WorkspaceState.DESTROYED
            return False

    async def get_state(self, workspace_id: str) -> WorkspaceState:
        """Query real-time state of the Daytona sandbox."""
        client = self._get_client()
        if not client:
            return self._states.get(workspace_id, WorkspaceState.ERROR)

        try:
            sandbox = await client.get(workspace_id)
            if sandbox:
                state_str = str(getattr(sandbox, "state", "")).lower()
                if "running" in state_str or "started" in state_str:
                    return WorkspaceState.RUNNING
                elif "stopped" in state_str or "paused" in state_str:
                    return WorkspaceState.STOPPED
                elif "archived" in state_str or "deleted" in state_str:
                    return WorkspaceState.DESTROYED
                return WorkspaceState.RUNNING
            return WorkspaceState.DESTROYED
        except Exception:
            return self._states.get(workspace_id, WorkspaceState.ERROR)
