"""
SONIC-REDA — Headless Sandbox Execution Plane
================================================
A thin operator-plane adapter that exposes the sandbox subset of the
``ComputerProvider`` surface (terminal, files, services) over any
``ComputeProvider`` (Docker / remote).

Why this exists
---------------
The graphical Workstation and the headless sandbox are two independent planes.
Previously every sandbox endpoint (command / file / git / services) resolved its
``workspace_id`` from a *provisioned desktop*, so a missing or broken desktop
took the whole operator plane down with it. This adapter lets those endpoints
run against a dedicated headless container, so terminal/file/git work no longer
depends on the GUI workstation.

It deliberately implements ONLY the sandbox surface — no screenshot / GUI
methods, so the plane boundary stays explicit.

Fail-closed invariant: if the container cannot be provisioned or reached, every
method returns the provider's fail-closed result (exit 126). Host execution is
never attempted.
"""

from __future__ import annotations

import shlex
from typing import Any

from sonic.computer.models import FileEntry, ServiceInfo
from sonic.logger import get_logger
from sonic.sandbox.provider import ComputeProvider, ExecResult, WorkspaceConfig, WorkspaceType

logger = get_logger(__name__)


class SandboxComputePlane:
    """Operator/headless plane bound to one compute workspace (container)."""

    plane_kind = "headless_sandbox"

    def __init__(
        self,
        compute: ComputeProvider,
        workspace_id: str,
        tenant_id: str = "default",
        workspace_root: str = "/home/sonic/workspace",
        image: str = "debian:12-slim",
    ):
        self._compute = compute
        self.workspace_id = workspace_id
        self.tenant_id = tenant_id
        self.workspace_root = workspace_root
        self.image = image

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def _probe_ok(self) -> bool:
        """True only when a trivial command actually runs in the container."""
        try:
            res = await self._compute.execute(self.workspace_id, "true", timeout=10)
            return res.exit_code == 0
        except Exception:
            return False

    async def attach(self) -> bool:
        """Attach to an already-running sandbox container without provisioning.

        Read-only telemetry endpoints must never silently create a container;
        they use this and degrade gracefully when nothing is running.
        """
        return await self._probe_ok()

    async def ensure(self) -> bool:
        """Attach to the sandbox container, provisioning it if needed.

        Idempotent: a live container is reused. Returns False (fail-closed) when
        no container could be provisioned or reached.
        """
        if await self._probe_ok():
            return True
        try:
            created = await self._compute.create_workspace(
                WorkspaceConfig(
                    workspace_id=self.workspace_id,
                    tenant_id=self.tenant_id,
                    workspace_type=WorkspaceType.RESEARCH_LAB,
                    image=self.image,
                    network_isolated=False,
                )
            )
        except Exception as e:
            logger.warning("sandbox_plane_provision_failed", workspace_id=self.workspace_id, error=str(e))
            created = False
        if not created:
            # The container may already exist but be stopped; one final probe
            # distinguishes "unusable" from "already running".
            return await self._probe_ok()
        try:
            await self._compute.execute(
                self.workspace_id, f"mkdir -p {shlex.quote(self.workspace_root)}", timeout=15
            )
        except Exception:
            pass
        logger.info("sandbox_plane_ready", workspace_id=self.workspace_id, image=self.image)
        return True

    # ------------------------------------------------------------------
    # Sandbox operations (ComputerProvider-compatible surface)
    # ------------------------------------------------------------------
    async def terminal(
        self,
        workspace_id: str = "",
        command: str = "",
        timeout: int = 60,
        actor: str = "operator",
        **kwargs: Any,
    ) -> ExecResult:
        # Run inside the workspace root so `pwd`/relative paths match the
        # documented operator workspace, not the container's default `/`.
        return await self._compute.execute(
            self.workspace_id, command, cwd=self.workspace_root, timeout=timeout
        )

    async def execute(
        self,
        workspace_id: str = "",
        command: str | list[str] = "",
        timeout: int = 60,
        actor: str = "operator",
        **kwargs: Any,
    ) -> ExecResult:
        return await self._compute.execute(
            self.workspace_id, command, cwd=self.workspace_root, timeout=timeout
        )

    async def read_file(self, workspace_id: str = "", path: str = "", **kwargs: Any) -> str:
        data = await self._compute.read_file(self.workspace_id, path)
        if isinstance(data, bytes):
            return data.decode("utf-8", errors="replace")
        return str(data or "")

    async def write_file(
        self,
        workspace_id: str = "",
        path: str = "",
        content: str = "",
        actor: str = "operator",
        **kwargs: Any,
    ) -> bool:
        return await self._compute.write_file(self.workspace_id, path, content)

    async def list_files(self, workspace_id: str = "", path: str = ".") -> list[FileEntry]:
        res = await self._compute.execute(
            self.workspace_id, f"ls -la {shlex.quote(path)} 2>/dev/null", timeout=10
        )
        entries: list[FileEntry] = []
        if res.exit_code == 0 and res.stdout.strip():
            for line in res.stdout.splitlines()[1:]:  # skip 'total'
                parts = line.split(maxsplit=8)
                if len(parts) >= 9:
                    name = parts[8].strip()
                    if name in (".", ".."):
                        continue
                    entries.append(
                        FileEntry(
                            path=f"{path}/{name}".replace("//", "/"),
                            name=name,
                            is_dir=parts[0].startswith("d"),
                            size_bytes=int(parts[4]) if parts[4].isdigit() else 0,
                        )
                    )
        return entries

    async def service_action(
        self,
        workspace_id: str = "",
        service_name: str = "",
        action: str = "status",
        actor: str = "operator",
    ) -> ServiceInfo:
        res = await self._compute.execute(
            self.workspace_id, f"service {shlex.quote(service_name)} {shlex.quote(action)} 2>&1", timeout=30
        )
        status = "RUNNING" if res.exit_code == 0 and action in ("start", "restart") else action.upper()
        return ServiceInfo(
            name=service_name, status=status, port=0, logs=(res.stdout or "").splitlines()
        )
