"""
SONIC — Headless Compute Provider (Dual Execution Architecture)
================================================================
Provides lightweight, direct execution capabilities without requiring a full
graphical desktop workstation, Docker daemon, or Daytona cloud container.

Supports:
    - Native terminal execution via asyncio.subprocess
    - Asynchronous TCP port scanning without nmap or Docker
    - Direct HTTP/REST probing via httpx
    - Sandboxed local filesystem operations with path traversal protection
    - Graceful fallback observations for unsupported GUI actions
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from sonic.computer.models import (
    ApplicationPolicy,
    ComputerAuditEvent,
    ComputerProfile,
    ComputerRiskLevel,
    ComputerSession,
    ComputerState,
    ComputerWorkspace,
    ComputerWorkspaceStatus,
    ComputerWorkspaceType,
    FileEntry,
    GitStatusInfo,
    GUIAction,
    GUIActionType,
    ProcessInfo,
    ScreenObservation,
    ServiceInfo,
    _new_id,
    _now,
)
from sonic.computer.provider import ComputerProvider
from sonic.logger import get_logger
from sonic.sandbox.egress import is_target_allowed
from sonic.sandbox.provider import (
    ComputeProvider,
    ExecResult,
    WorkspaceConfig,
    WorkspaceState,
    WorkspaceType,
)

logger = get_logger(__name__)


class HeadlessFileContent(str):
    """
    String subclass supporting .decode() for drop-in compatibility with callers
    expecting either str or bytes.
    """

    def decode(self, *args: Any, **kwargs: Any) -> str:
        return self


class HeadlessComputeProvider(ComputerProvider, ComputeProvider):
    """
    Headless Compute Provider for fast, container-free, display-free execution.
    Implements both ComputerProvider and ComputeProvider interfaces.
    """

    def __init__(
        self,
        base_dir: str | Path | None = None,
        allow_host_execution: bool = False,
        app_policy: ApplicationPolicy | None = None,
    ):
        if base_dir:
            self.base_dir = Path(base_dir).resolve()
        else:
            env_dir = os.environ.get("SONIC_WORKSPACE_DIR")
            if env_dir:
                self.base_dir = Path(env_dir).resolve()
            else:
                self.base_dir = (Path(tempfile.gettempdir()) / "sonic_headless_workspaces").resolve()

        self.allow_host_execution = allow_host_execution
        self.app_policy = app_policy or ApplicationPolicy()
        self.workspaces: dict[str, ComputerWorkspace] = {}
        self.sessions: dict[str, ComputerSession] = {}
        self.audit_log: list[ComputerAuditEvent] = []
        self._default_workspace_id = "ws-headless-default"

    # -------------------------------------------------------------
    # Workspace Directory & Path Resolution
    # -------------------------------------------------------------
    def _get_workspace_dir(self, workspace_id: str) -> Path:
        ws_id = workspace_id or self._default_workspace_id
        ws_dir = (self.base_dir / ws_id).resolve()
        ws_dir.mkdir(parents=True, exist_ok=True)
        return ws_dir

    def _resolve_path(self, workspace_id: str, path: str) -> Path:
        ws_dir = self._get_workspace_dir(workspace_id)
        # Normalize path
        p = Path(path)
        if p.is_absolute():
            try:
                resolved = p.resolve()
                if resolved.is_relative_to(ws_dir):
                    return resolved
            except Exception:
                pass
            clean_rel = path.lstrip("/\\")
            target = (ws_dir / clean_rel).resolve()
        else:
            target = (ws_dir / path).resolve()

        if not target.is_relative_to(ws_dir):
            raise ValueError(f"Path traversal attempted outside workspace root: {path}")
        return target

    def _ensure_workspace(
        self,
        workspace_id: str,
        tenant_id: str = "default",
        engagement_id: str = "default",
    ) -> ComputerWorkspace:
        ws_id = workspace_id or self._default_workspace_id
        if ws_id not in self.workspaces:
            ws = ComputerWorkspace(
                id=ws_id,
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                workspace_type=ComputerWorkspaceType.RESEARCH_LAB,
                profile=ComputerProfile.GENERIC_LINUX,
                provider_type="HeadlessComputeProvider",
                image="headless-local",
                status=ComputerWorkspaceStatus.READY,
                workspace_path=str(self._get_workspace_dir(ws_id)),
                capabilities=["terminal", "filesystem", "http_probe", "port_scan", "git"],
            )
            self.workspaces[ws_id] = ws
        return self.workspaces[ws_id]

    # -------------------------------------------------------------
    # 1. Lifecycle (ComputerProvider & ComputeProvider)
    # -------------------------------------------------------------
    async def create(
        self,
        tenant_id: str,
        engagement_id: str,
        workspace_type: ComputerWorkspaceType = ComputerWorkspaceType.MISSION_COMPUTER,
        profile: ComputerProfile = ComputerProfile.GENERIC_LINUX,
    ) -> ComputerWorkspace:
        workspace_id = _new_id("ws-headless")
        ws = ComputerWorkspace(
            id=workspace_id,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            workspace_type=workspace_type,
            profile=profile,
            provider_type="HeadlessComputeProvider",
            image="headless-local",
            status=ComputerWorkspaceStatus.READY,
            workspace_path=str(self._get_workspace_dir(workspace_id)),
            capabilities=["terminal", "filesystem", "http_probe", "port_scan", "git"],
        )
        self.workspaces[workspace_id] = ws
        self._record_audit(
            session_id="system",
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            actor="HeadlessComputeProvider",
            action="CREATE_HEADLESS_WORKSPACE",
            resource=workspace_id,
            result="SUCCESS",
        )
        return ws

    async def create_workspace(self, config: WorkspaceConfig) -> bool:
        self._ensure_workspace(
            workspace_id=config.workspace_id,
            tenant_id=config.tenant_id,
        )
        return True

    async def destroy(self, workspace_id: str) -> bool:
        ws = self.workspaces.pop(workspace_id, None)
        ws_dir = self.base_dir / (workspace_id or self._default_workspace_id)
        if ws_dir.exists():
            with suppress(Exception):
                shutil.rmtree(ws_dir, ignore_errors=True)
        if ws:
            ws.status = ComputerWorkspaceStatus.DESTROYED
            self._record_audit(
                session_id="system",
                workspace_id=workspace_id,
                tenant_id=ws.tenant_id,
                actor="HeadlessComputeProvider",
                action="DESTROY_HEADLESS_WORKSPACE",
                resource=workspace_id,
                result="SUCCESS",
            )
            return True
        return False

    async def destroy_workspace(self, workspace_id: str) -> bool:
        return await self.destroy(workspace_id)

    async def status(self, workspace_id: str) -> ComputerState:
        ws = self._ensure_workspace(workspace_id)
        ws_dir = self._get_workspace_dir(workspace_id)
        return ComputerState(
            workspace_id=ws.id,
            tenant_id=ws.tenant_id,
            status=ws.status,
            active_application="headless_terminal",
            open_applications=["headless_terminal"],
            active_window="Headless",
            working_directory=str(ws_dir),
            running_processes=[],
            installed_applications=["python3", "git", "curl"],
            current_project="headless-session",
            git_branch="main",
            resource_usage={"cpu_pct": 1.0, "memory_mb": 128.0},
        )

    async def get_state(self, workspace_id: str) -> WorkspaceState:
        ws = self.workspaces.get(workspace_id)
        if not ws:
            return WorkspaceState.STOPPED
        if ws.status == ComputerWorkspaceStatus.READY:
            return WorkspaceState.RUNNING
        if ws.status == ComputerWorkspaceStatus.DESTROYED:
            return WorkspaceState.DESTROYED
        return WorkspaceState.RUNNING

    # -------------------------------------------------------------
    # 2. Terminal Execution
    # -------------------------------------------------------------
    async def terminal(
        self,
        workspace_id: str,
        command: str,
        timeout: int = 60,
        actor: str = "operator",
    ) -> ExecResult:
        """Execute command in headless terminal."""
        ws = self._ensure_workspace(workspace_id)
        res = await self.execute(
            workspace_id=workspace_id,
            command=command,
            timeout=timeout,
        )
        self._record_audit(
            session_id=actor,
            workspace_id=ws.id,
            tenant_id=ws.tenant_id,
            actor=actor,
            action="EXECUTE_TERMINAL",
            resource=command[:100],
            result="SUCCESS" if res.exit_code == 0 else f"EXIT_{res.exit_code}",
        )
        return res

    async def execute(
        self,
        workspace_id: str,
        command: str | list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 120,
    ) -> ExecResult:
        """Execute a command via native asyncio.subprocess."""
        cmd_str = command if isinstance(command, str) else " ".join(command)
        ws_dir = self._get_workspace_dir(workspace_id)
        effective_cwd = cwd or str(ws_dir)

        if not self.allow_host_execution:
            logger.warning("headless_host_execution_blocked", command=cmd_str[:60])
            return ExecResult(
                command=cmd_str,
                exit_code=126,
                stdout="",
                stderr="FAIL-CLOSED: Host execution is disabled in HeadlessComputeProvider.",
                sandbox_id=workspace_id,
            )

        start_time = datetime.now(UTC)
        try:
            process = await asyncio.create_subprocess_shell(
                cmd_str,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=effective_cwd,
                env={**os.environ, **(env or {})},
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout if timeout > 0 else 60,
                )
            except (TimeoutError, asyncio.TimeoutError):
                with suppress(Exception):
                    process.kill()
                return ExecResult(
                    command=cmd_str,
                    exit_code=124,
                    stdout="",
                    stderr=f"Command timed out after {timeout} seconds",
                    duration_seconds=float(timeout),
                    timed_out=True,
                    sandbox_id=workspace_id,
                )

            duration = (datetime.now(UTC) - start_time).total_seconds()
            return ExecResult(
                command=cmd_str,
                exit_code=process.returncode if process.returncode is not None else 0,
                stdout=stdout_b.decode("utf-8", errors="replace"),
                stderr=stderr_b.decode("utf-8", errors="replace"),
                duration_seconds=round(duration, 2),
                sandbox_id=workspace_id,
            )
        except Exception as exc:
            return ExecResult(
                command=cmd_str,
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                duration_seconds=0.0,
                sandbox_id=workspace_id,
            )

    # -------------------------------------------------------------
    # 3. Native Port Scanning (No Nmap/Docker required)
    # -------------------------------------------------------------
    async def scan_ports(
        self,
        host: str,
        ports: list[int],
        timeout: float = 1.0,
    ) -> list[dict[str, Any]]:
        """
        Probe TCP ports asynchronously using native asyncio.open_connection.
        Does not require nmap, Docker, or root privileges.
        """
        async def _probe_port(p: int) -> dict[str, Any]:
            try:
                conn = asyncio.open_connection(host, p)
                reader, writer = await asyncio.wait_for(conn, timeout=timeout)
                writer.close()
                with suppress(Exception):
                    await writer.wait_closed()
                return {
                    "port": p,
                    "state": "open",
                    "open": True,
                    "protocol": "tcp",
                    "host": host,
                }
            except (TimeoutError, asyncio.TimeoutError):
                return {
                    "port": p,
                    "state": "timeout",
                    "open": False,
                    "protocol": "tcp",
                    "host": host,
                }
            except (ConnectionRefusedError, OSError):
                return {
                    "port": p,
                    "state": "closed",
                    "open": False,
                    "protocol": "tcp",
                    "host": host,
                }
            except Exception as exc:
                return {
                    "port": p,
                    "state": "error",
                    "open": False,
                    "protocol": "tcp",
                    "host": host,
                    "error": str(exc),
                }

        tasks = [_probe_port(port) for port in ports]
        return list(await asyncio.gather(*tasks))

    # -------------------------------------------------------------
    # 4. Native HTTP Probing (httpx)
    # -------------------------------------------------------------
    async def http_probe(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: str | None = None,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        """
        Perform direct HTTP probing using httpx.AsyncClient.
        Returns status_code, headers, and body snippet.
        """
        try:
            current_url = url
            async with httpx.AsyncClient(timeout=timeout, verify=True, follow_redirects=False) as client:
                for _ in range(5):
                    allowed, reason = is_target_allowed(current_url)
                    if not allowed:
                        return {
                            "status_code": 0,
                            "headers": {},
                            "body": "",
                            "body_snippet": "",
                            "url": current_url,
                            "ok": False,
                            "error": f"Egress blocked: {reason}",
                        }
                    resp = await client.request(
                        method=method.upper(),
                        url=current_url,
                        headers=headers,
                        content=body.encode("utf-8") if body is not None else None,
                    )
                    if not resp.is_redirect:
                        break
                    location = resp.headers.get("location")
                    if not location:
                        break
                    current_url = str(httpx.URL(current_url).join(location))
                body_snippet = resp.text[:2000] if resp.text else ""
                return {
                    "status_code": resp.status_code,
                    "headers": dict(resp.headers),
                    "body": body_snippet,
                    "body_snippet": body_snippet,
                    "url": str(resp.url),
                    "ok": resp.is_success,
                }
        except Exception as exc:
            return {
                "status_code": 0,
                "headers": {},
                "body": "",
                "body_snippet": "",
                "url": url,
                "ok": False,
                "error": str(exc),
            }

    # -------------------------------------------------------------
    # 5. Filesystem Operations
    # -------------------------------------------------------------
    async def read_file(self, workspace_id: str, path: str) -> HeadlessFileContent:
        target = self._resolve_path(workspace_id, path)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        content = target.read_text(encoding="utf-8", errors="replace")
        return HeadlessFileContent(content)

    async def read_file_bytes(self, workspace_id: str, path: str) -> bytes:
        target = self._resolve_path(workspace_id, path)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        return target.read_bytes()

    async def write_file(
        self,
        workspace_id: str,
        path: str,
        content: str | bytes,
        actor: str = "operator",
    ) -> bool:
        ws = self._ensure_workspace(workspace_id)
        target = self._resolve_path(workspace_id, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            target.write_text(content, encoding="utf-8")
        else:
            target.write_bytes(content)

        self._record_audit(
            session_id=actor,
            workspace_id=ws.id,
            tenant_id=ws.tenant_id,
            actor=actor,
            action="WRITE_FILE",
            resource=path,
            result="SUCCESS",
        )
        return True

    async def list_files(self, workspace_id: str, path: str = ".") -> list[FileEntry]:
        target = self._resolve_path(workspace_id, path)
        if not target.exists() or not target.is_dir():
            return []
        ws_dir = self._get_workspace_dir(workspace_id)
        entries: list[FileEntry] = []
        for item in target.iterdir():
            entries.append(
                FileEntry(
                    name=item.name,
                    path=str(item.relative_to(ws_dir)).replace("\\", "/"),
                    is_dir=item.is_dir(),
                    size_bytes=item.stat().st_size if item.is_file() else 0,
                    modified_at=datetime.fromtimestamp(item.stat().st_mtime, UTC).isoformat(),
                )
            )
        return entries

    # -------------------------------------------------------------
    # 6. GUI Actions (Graceful Headless Observation)
    # -------------------------------------------------------------
    async def screenshot(self, workspace_id: str = "") -> ScreenObservation:
        return ScreenObservation(
            screenshot_base64="",
            width=0,
            height=0,
            active_window="Headless",
            visible_text="[HEADLESS EXECUTION SUBSTRATE: NO GRAPHICAL DISPLAY ATTACHED]",
            detected_controls=[],
            desktop_state="HEADLESS",
        )

    async def gui_action(
        self,
        workspace_id: str,
        action: GUIAction,
        actor: str = "operator",
    ) -> ScreenObservation:
        action_name = action.action.value if hasattr(action.action, "value") else str(action.action)
        logger.info(
            "headless_gui_action_intercepted",
            workspace_id=workspace_id,
            action=action_name,
        )
        return ScreenObservation(
            screenshot_base64="",
            width=0,
            height=0,
            active_window="Headless",
            visible_text=f"[HEADLESS SUBSTRATE: GUI action '{action_name}' unsupported in headless mode]",
            detected_controls=[],
            desktop_state="HEADLESS",
        )

    async def click(self, workspace_id: str = "", x: int = 0, y: int = 0, **kwargs: Any) -> ScreenObservation:
        return await self.gui_action(
            workspace_id,
            GUIAction(action=GUIActionType.CLICK, x=x, y=y),
        )

    async def type(self, workspace_id: str = "", text: str = "", **kwargs: Any) -> ScreenObservation:
        return await self.gui_action(
            workspace_id,
            GUIAction(action=GUIActionType.TYPE, text=text),
        )

    # -------------------------------------------------------------
    # 7. Application & Services Management (Headless compatibility)
    # -------------------------------------------------------------
    async def process_list(self, workspace_id: str) -> list[ProcessInfo]:
        return []

    async def application_list(self, workspace_id: str) -> list[str]:
        installed: set[str] = set()

        # 1. Desktop entries (if standard desktop directories exist)
        desktop_dirs = [
            Path("/usr/share/applications"),
            Path("/usr/local/share/applications"),
            Path.home() / ".local/share/applications",
        ]
        for d in desktop_dirs:
            if d.is_dir():
                try:
                    for p in d.glob("*.desktop"):
                        installed.add(p.stem)
                except Exception:
                    pass

        # 2. Dynamic discovery of common utilities and policy-defined packages on PATH
        probe_candidates = set(self.app_policy.allowed_packages) | {
            "python3", "python", "git", "curl", "wget", "bash", "sh", "node", "npm", "zsh", "tmux"
        }
        for cmd in probe_candidates:
            if shutil.which(cmd):
                installed.add(cmd)

        return sorted(installed)

    async def launch_application(self, workspace_id: str, app_name: str, actor: str = "operator") -> bool:
        logger.info("headless_launch_application_noop", app=app_name)
        return False

    async def close_application(self, workspace_id: str, app_name: str, actor: str = "operator") -> bool:
        return True

    async def install_application(
        self,
        workspace_id: str,
        package_name: str,
        actor: str = "operator",
    ) -> tuple[bool, str]:
        allowed, reason = self.app_policy.is_package_allowed(package_name)
        if not allowed:
            return False, reason
        return True, f"Headless environment acknowledged package request: {package_name}"

    async def uninstall_application(
        self,
        workspace_id: str,
        package_name: str,
        actor: str = "operator",
    ) -> bool:
        return True

    async def service_action(
        self,
        workspace_id: str,
        service_name: str,
        action: str,
        actor: str = "operator",
    ) -> ServiceInfo:
        return ServiceInfo(
            name=service_name,
            status="HEADLESS_STANDBY",
            logs=[f"Headless environment service '{service_name}' simulated {action}"],
        )

    async def git_action(self, workspace_id: str, action: str, **kwargs: Any) -> Any:
        actor = kwargs.get("actor", "operator")
        ws_dir = self._get_workspace_dir(workspace_id)
        if action == "status":
            res = await self.execute(workspace_id, "git status --porcelain", cwd=str(ws_dir))
            if res.exit_code == 0:
                lines = res.stdout.strip().splitlines()
                modified = [l[3:] for l in lines if l.startswith(" M ")]
                untracked = [l[3:] for l in lines if l.startswith("?? ")]
                return GitStatusInfo(
                    branch="main",
                    is_clean=len(modified) == 0 and len(untracked) == 0,
                    modified_files=modified,
                    untracked_files=untracked,
                )
            return GitStatusInfo(branch="main", is_clean=True)
        elif action == "commit":
            msg = kwargs.get("message", "chore: headless automated commit")
            res = await self.execute(
                workspace_id,
                f"git add -A && git commit -m '{msg}' || true",
                cwd=str(ws_dir),
            )
            return res.exit_code == 0
        return False

    # -------------------------------------------------------------
    # Audit Logging Helper
    # -------------------------------------------------------------
    def _record_audit(
        self,
        session_id: str,
        workspace_id: str,
        tenant_id: str,
        actor: str,
        action: str,
        resource: str,
        result: str,
        application: str | None = None,
        risk_level: ComputerRiskLevel = ComputerRiskLevel.LOW,
    ) -> None:
        event = ComputerAuditEvent(
            session_id=session_id,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            application=application,
            resource=resource,
            result=result,
            risk_level=risk_level,
        )
        self.audit_log.append(event)
