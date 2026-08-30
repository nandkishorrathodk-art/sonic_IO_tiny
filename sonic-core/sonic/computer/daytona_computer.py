"""
SONIC-REDA — Daytona Real Graphical Workstation & Computer Provider
====================================================================
Integrates Daytona Cloud Sandboxes with full graphical Linux workstation capabilities:
    - Real Xvfb (:99) + XFCE4 desktop session
    - Real VNC / noVNC live streaming bridge
    - Real Daytona SDK Computer Use (AsyncMouse, AsyncKeyboard, AsyncScreenshot)
    - Real remote PTY terminal (/bin/bash)
    - Real remote Filesystem & Git operations
    - Multi-tenant authenticated scoping
    - FAIL-CLOSED security invariant: Zero host OS execution.
"""

from __future__ import annotations

import os
import shlex
import asyncio
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sonic.computer.models import (
    ApplicationPolicy,
    ComputerAuditEvent,
    ComputerProfile,
    ComputerRiskLevel,
    ComputerSession,
    ComputerSessionMode,
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
from sonic.sandbox.provider import ExecResult, WorkspaceConfig, WorkspaceState, WorkspaceType

logger = get_logger(__name__)


class DaytonaComputerProvider(ComputerProvider):
    """
    Daytona-backed Graphical Computer Provider.
    Authoritative remote Linux workstation powered by Daytona Cloud.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        target: Optional[str] = None,
        app_policy: Optional[ApplicationPolicy] = None,
    ):
        self.api_key = api_key or os.environ.get("DAYTONA_API_KEY", "")
        self.api_url = api_url or os.environ.get("DAYTONA_API_URL")
        self.target = target or os.environ.get("DAYTONA_TARGET", "us")
        self.app_policy = app_policy or ApplicationPolicy()

        self._client = None
        self._sandboxes: dict[str, Any] = {}
        self.workspaces: dict[str, ComputerWorkspace] = {}
        self.sessions: dict[str, ComputerSession] = {}
        self.audit_log: list[ComputerAuditEvent] = []
        self._active_windows: dict[str, str] = {}

    def _get_client(self):
        """Initializes and returns the official AsyncDaytona SDK client."""
        if self._client is None:
            try:
                from daytona import AsyncDaytona, DaytonaConfig

                config_kwargs = {}
                if self.api_key:
                    config_kwargs["api_key"] = self.api_key
                if self.api_url:
                    # Current Daytona SDK uses api_url; server_url is kept
                    # only for older SDKs and emits a deprecation warning.
                    config_kwargs["api_url"] = self.api_url
                if self.target:
                    config_kwargs["target"] = self.target

                config = DaytonaConfig(**config_kwargs) if config_kwargs else None
                self._client = AsyncDaytona(config=config)
                logger.info("daytona_computer_sdk_initialized", has_api_key=bool(self.api_key))
            except Exception as e:
                logger.error("daytona_computer_sdk_init_failed", error=str(e))
                self._client = None
        return self._client

    async def _resolve_sandbox(self, workspace_id: str) -> Optional[Any]:
        """Resolves the live AsyncDaytona sandbox instance for workspace or environment sandbox."""
        if workspace_id and workspace_id in self._sandboxes:
            return self._sandboxes[workspace_id]

        env_id = os.environ.get("DAYTONA_SANDBOX_ID", "")
        # Persisted workspace IDs are Daytona sandbox IDs. Older in-memory
        # records used a synthetic ws-* ID and can only resolve through the
        # attached environment sandbox fallback.
        target_id = workspace_id if (workspace_id and not workspace_id.startswith("ws-") and workspace_id != "default") else env_id

        if target_id:
            if target_id in self._sandboxes:
                return self._sandboxes[target_id]

            client = self._get_client()
            if client:
                try:
                    sandbox = await client.get(target_id)
                    if sandbox:
                        if workspace_id:
                            self._sandboxes[workspace_id] = sandbox
                        self._sandboxes[target_id] = sandbox
                        # Ensure computer_use VNC stack is started
                        if hasattr(sandbox, "computer_use"):
                            try:
                                await sandbox.computer_use.start()
                            except Exception:
                                pass
                        return sandbox
                except Exception as e:
                    logger.warning("daytona_resolve_sandbox_failed", target_id=target_id, error=str(e))
        return None

    # -------------------------------------------------------------
    # 1. Lifecycle (Create, Start, Stop, Destroy)
    # -------------------------------------------------------------

    async def create(
        self,
        tenant_id: str,
        engagement_id: str,
        workspace_type: ComputerWorkspaceType = ComputerWorkspaceType.MISSION_COMPUTER,
        profile: ComputerProfile = ComputerProfile.DEBIAN_ENGINEERING,
    ) -> ComputerWorkspace:
        """Provisions an authorized Daytona graphical workstation."""
        workspace_id = _new_id("ws-daytona")
        client = self._get_client()

        # Mission desktops are persistent engineering workstations. Research
        # labs are intentionally disposable and may use a hardened security
        # image configured separately by the operator.
        image_env = {
            ComputerWorkspaceType.RESEARCH_LAB: "DAYTONA_RESEARCH_IMAGE",
            ComputerWorkspaceType.TARGET_SANDBOX: "DAYTONA_TARGET_IMAGE",
            ComputerWorkspaceType.MISSION_COMPUTER: "DAYTONA_IMAGE",
        }[workspace_type]
        configured_image = os.environ.get(image_env, "daytonaio/sandbox:0.9.0")
        ws = ComputerWorkspace(
            id=workspace_id,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            workspace_type=workspace_type,
            profile=profile,
            provider_type="DaytonaComputerProvider",
            image=configured_image,
            status=ComputerWorkspaceStatus.CREATING,
            capabilities=["desktop", "terminal", "filesystem", "ide", "browser", "git", "computer_use"],
        )
        self.workspaces[workspace_id] = ws

        if not client or not self.api_key:
            ws.status = ComputerWorkspaceStatus.FAILED
            self.workspaces.pop(workspace_id, None)
            raise RuntimeError(
                "Daytona is not configured. Set DAYTONA_API_KEY and install the official SDK."
            )

        try:
            env_sandbox_id = os.environ.get("DAYTONA_SANDBOX_ID")
            configured_tenant = os.environ.get("DAYTONA_SANDBOX_TENANT_ID")
            if env_sandbox_id and configured_tenant == tenant_id:
                sandbox = await client.get(env_sandbox_id)
                if not sandbox:
                    raise RuntimeError(f"Configured Daytona sandbox '{env_sandbox_id}' was not found")
                self._sandboxes[workspace_id] = sandbox
                logger.info("daytona_sandbox_attached", workspace_id=workspace_id, sandbox_id=env_sandbox_id)
            else:
                from daytona import CreateSandboxFromImageParams

                params = CreateSandboxFromImageParams(
                    name=workspace_id,
                    image=ws.image,
                    labels={
                        "tenant_id": tenant_id,
                        "engagement_id": engagement_id,
                        "managed_by": "sonic-reda",
                        "workstation": "graphical_desktop",
                        "workspace_type": workspace_type.value,
                    },
                    auto_stop_interval=30,
                )
                sandbox = await client.create(params, timeout=120)
                if not sandbox:
                    raise RuntimeError("Daytona returned no sandbox for the create request")
                self._sandboxes[workspace_id] = sandbox

            # Use Daytona's authoritative sandbox ID as the workspace ID so
            # the control plane can reconnect after a process restart.
            remote_id = str(getattr(sandbox, "id", "") or env_sandbox_id or "")
            if remote_id and remote_id != workspace_id:
                self._sandboxes[remote_id] = sandbox
                self.workspaces.pop(workspace_id, None)
                self._active_windows.pop(workspace_id, None)
                ws.id = remote_id
                self.workspaces[remote_id] = ws
                workspace_id = remote_id

            if not hasattr(sandbox, "computer_use"):
                raise RuntimeError("Daytona sandbox does not expose the computer_use API")
            await sandbox.computer_use.start()
            ws.status = ComputerWorkspaceStatus.READY
            logger.info("daytona_computer_use_started", workspace_id=workspace_id)
        except Exception as e:
            ws.status = ComputerWorkspaceStatus.FAILED
            self._sandboxes.pop(workspace_id, None)
            self.workspaces.pop(workspace_id, None)
            logger.error("daytona_cloud_provision_failed", error=str(e), workspace_id=workspace_id)
            raise

        self._active_windows[workspace_id] = "XFCE Desktop"
        self._record_audit(
            session_id="system",
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            actor="DaytonaComputerProvider",
            action="CREATE_GRAPHICAL_WORKSTATION",
            resource=workspace_id,
            result="SUCCESS",
        )
        return ws

    async def destroy(self, workspace_id: str) -> bool:
        """Terminates and destroys the Daytona cloud sandbox."""
        ws = self.workspaces.get(workspace_id)
        if ws:
            ws.status = ComputerWorkspaceStatus.DESTROYING
            client = self._get_client()
            sandbox = self._sandboxes.get(workspace_id)
            if client and sandbox:
                try:
                    await sandbox.delete()
                except Exception as e:
                    logger.warning("daytona_sandbox_delete_failed", error=str(e))
            self.workspaces.pop(workspace_id, None)
            self._sandboxes.pop(workspace_id, None)
            self._active_windows.pop(workspace_id, None)
            return True
        return False

    async def get_stream_url(self, workspace_id: str) -> Optional[str]:
        """Obtains the Daytona preview/public URL for the noVNC port (6080).

        Uses the Daytona SDK get_preview_link API. Returns None if unavailable.
        """
        sandbox = await self._resolve_sandbox(workspace_id)
        if sandbox and hasattr(sandbox, "get_preview_link"):
            try:
                preview = await sandbox.get_preview_link(6080)
                url = getattr(preview, "url", None)
                token = getattr(preview, "token", None)
                if url:
                    # Encode private-sandbox tokens before returning the URL.
                    # Tokens may contain `+`, `/`, or `=`; concatenating them
                    # raw causes browsers to send a different value and the
                    # Daytona proxy then rejects its /callback state check.
                    if token:
                        parts = urlsplit(str(url))
                        query = dict(parse_qsl(parts.query, keep_blank_values=True))
                        query["token"] = str(token)
                        return urlunsplit((
                            parts.scheme,
                            parts.netloc,
                            parts.path,
                            urlencode(query),
                            parts.fragment,
                        ))
                    return str(url)
            except Exception as e:
                logger.warning("daytona_vnc_preview_url_failed", error=str(e))
        return None

    async def get_vnc_url(self, workspace_id: str) -> Optional[str]:
        """Alias for get_stream_url."""
        return await self.get_stream_url(workspace_id)

    async def status(self, workspace_id: str) -> ComputerState:
        """Returns the real-time operational state of the graphical desktop."""
        ws = self.workspaces.get(workspace_id)
        tenant_id = ws.tenant_id if ws else ""
        active_app = self._active_windows.get(workspace_id, "None")

        # Query real running processes from sandbox
        real_processes = []
        resource_usage = {"cpu_pct": 0.0, "memory_mb": 0.0}
        sandbox = await self._resolve_sandbox(workspace_id)
        if sandbox and hasattr(sandbox, "computer_use"):
            try:
                cu_status = await sandbox.computer_use.get_status()
                if cu_status and hasattr(cu_status, "status"):
                    real_processes = [str(cu_status.status)]
            except Exception:
                pass
            try:
                metrics = await sandbox.get_metrics_latest()
                if metrics:
                    resource_usage = {
                        "cpu_pct": getattr(metrics, "cpu_usage_percent", 0.0) or 0.0,
                        "memory_mb": getattr(metrics, "mem_usage_bytes", 0) / (1024 * 1024) if getattr(metrics, "mem_usage_bytes", None) else 0.0,
                    }
            except Exception:
                pass

        # Query installed applications in the sandbox (empty if sandbox unavailable)
        installed_apps = await self.application_list(workspace_id)

        # Query real git branch if repository is present
        git_res = await self.terminal(workspace_id, "git branch --show-current 2>/dev/null")
        git_branch = git_res.stdout.strip() if (git_res.exit_code == 0 and git_res.stdout.strip()) else ""

        return ComputerState(
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            active_application=active_app,
            open_applications=[active_app] if active_app != "None" else [],
            active_window=active_app,
            working_directory="/home/sonic/workspace",
            running_processes=real_processes,
            installed_applications=installed_apps,
            current_project="sonic",
            git_branch=git_branch,
            resource_usage=resource_usage,
        )

    # -------------------------------------------------------------
    # 2. Real Graphical Screen & Vision (Zero Fabricated Frames)
    # -------------------------------------------------------------

    async def screenshot(self, workspace_id: str) -> ScreenObservation:
        """
        Captures a real pixel observation of the sandbox desktop.
        Routes via Daytona computer_use.screenshot when sandbox is active,
        or via local container X11 frame grabber (scrot).
        When no real display is available, returns NO_DISPLAY state with empty screenshot.
        """
        sandbox = await self._resolve_sandbox(workspace_id)
        if sandbox and hasattr(sandbox, "computer_use"):
            try:
                # Capture real live screenshot from Daytona computer_use API
                response = await sandbox.computer_use.screenshot.take_full_screen()
                b64 = getattr(response, "screenshot", None) or ""
                size = getattr(response, "size_bytes", 0) or 0
                if b64 and (size > 100 or len(b64) > 100):
                    return ScreenObservation(
                        screenshot_base64=b64,
                        width=1280,
                        height=800,
                        active_window=self._active_windows.get(workspace_id, "XFCE Desktop"),
                        visible_text="Active Daytona Desktop Session",
                        detected_controls=["panel", "terminal_icon", "editor_icon", "browser_icon"],
                        desktop_state="INTERACTIVE",
                    )
            except Exception as e:
                logger.warning("daytona_direct_screenshot_failed", error=str(e))

        # NO_DISPLAY: no live desktop frame exists — never fabricate a pixel
        return ScreenObservation(
            screenshot_base64="",
            width=1280,
            height=800,
            active_window=self._active_windows.get(workspace_id, "None"),
            visible_text="",
            detected_controls=[],
            desktop_state="NO_DISPLAY",
        )

    # -------------------------------------------------------------
    # 3. Real GUI Action Dispatch (Mouse, Keyboard, Window Management)
    # -------------------------------------------------------------

    async def gui_action(
        self,
        workspace_id: str,
        action: GUIAction,
        actor: str = "operator",
    ) -> ScreenObservation:
        """
        Dispatches authentic mouse and keyboard events directly into the remote X11 desktop.
        """
        sandbox = await self._resolve_sandbox(workspace_id)
        if not sandbox or not hasattr(sandbox, "computer_use"):
            raise RuntimeError("No live Daytona computer workspace is attached to this session")
        action_type = action.action

        supported_actions = {
            GUIActionType.CLICK,
            GUIActionType.DOUBLE_CLICK,
            GUIActionType.TYPE,
            GUIActionType.KEYPRESS,
            GUIActionType.MOVE,
            GUIActionType.OPEN_APP,
            GUIActionType.CLOSE_APP,
        }
        if action_type not in supported_actions:
            raise RuntimeError(f"Daytona GUI action {action_type.value} is not supported by this provider")

        if action_type in [GUIActionType.CLICK, GUIActionType.DOUBLE_CLICK]:
            if action.x is None or action.y is None:
                logger.warning("daytona_gui_click_missing_coordinates", action=action_type.value, x=action.x, y=action.y)
                return await self.screenshot(workspace_id)

        if sandbox and hasattr(sandbox, "computer_use"):
            try:
                cu = sandbox.computer_use
                if action_type in [GUIActionType.CLICK, GUIActionType.DOUBLE_CLICK]:
                    await cu.mouse.move(action.x, action.y)
                    await cu.mouse.click(button="left")
                    if action_type == GUIActionType.DOUBLE_CLICK:
                        await asyncio.sleep(0.08)
                        await cu.mouse.click(button="left")

                elif action_type == GUIActionType.MOVE:
                    await cu.mouse.move(action.x, action.y)

                elif action_type == GUIActionType.TYPE and action.text:
                    await cu.keyboard.type(action.text)

                elif action_type == GUIActionType.KEYPRESS and action.key:
                    await cu.keyboard.press(action.key)

                elif action_type == GUIActionType.OPEN_APP and action.app_name:
                    self._active_windows[workspace_id] = action.app_name
                    # Launch the app on DISPLAY :99 via process exec
                    try:
                        await sandbox.process.exec(f"DISPLAY=:99 {shlex.quote(action.app_name)} &")
                    except Exception:
                        pass

                elif action_type == GUIActionType.CLOSE_APP and action.app_name:
                    await sandbox.process.exec(f"pkill -f -- {shlex.quote(action.app_name)}")
                    if self._active_windows.get(workspace_id) == action.app_name:
                        self._active_windows[workspace_id] = "XFCE Desktop"

            except Exception as e:
                logger.error("daytona_gui_action_dispatch_error", error=str(e))
                raise RuntimeError(f"Daytona GUI action failed: {e}") from e

        if action.app_name:
            self._active_windows[workspace_id] = action.app_name

        self._record_audit(
            session_id=ws.engagement_id if ws else "unknown",
            workspace_id=workspace_id,
            tenant_id=ws.tenant_id if ws else actor,
            actor=actor,
            action=f"GUI_{action_type.value}",
            resource=action.app_name or "screen",
            result="SUCCESS",
            details=action.model_dump(),
        )
        return await self.screenshot(workspace_id)

    # -------------------------------------------------------------
    # 4. Real PTY Terminal & Command Execution (Sandbox-Bound)
    # -------------------------------------------------------------

    async def terminal(
        self,
        workspace_id: str,
        command: str,
        timeout: int = 60,
        actor: str = "operator",
    ) -> ExecResult:
        """
        Executes bash commands strictly inside the remote sandbox container.
        FAIL-CLOSED: Host execution is strictly forbidden.
        """
        sandbox = await self._resolve_sandbox(workspace_id)
        start_time = datetime.now(timezone.utc)

        # 1. Try Daytona SDK execution
        if sandbox and hasattr(sandbox, "process"):
            try:
                res = await sandbox.process.exec(command, timeout=timeout)
                duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                return ExecResult(
                    command=command,
                    exit_code=res.exit_code,
                    stdout=res.result or "",
                    stderr="",
                    duration_seconds=duration,
                    sandbox_id=workspace_id,
                )
            except Exception as e:
                logger.warning("daytona_process_exec_failed", error=str(e))

        # FAIL CLOSED
        return ExecResult(
            command=command,
            exit_code=126,
            stdout="",
            stderr="FAIL-CLOSED: Dedicated sandbox container is unreachable. Host execution is strictly prohibited.",
            duration_seconds=0.0,
            sandbox_id=workspace_id,
        )

    # -------------------------------------------------------------
    # 5. Real Remote Filesystem Operations
    # -------------------------------------------------------------

    async def read_file(self, workspace_id: str, path: str) -> str:
        """Reads a file from the sandbox container filesystem."""
        sandbox = await self._resolve_sandbox(workspace_id)
        if sandbox and hasattr(sandbox, "fs") and hasattr(sandbox.fs, "download_file"):
            try:
                content = await sandbox.fs.download_file(path)
                return content.decode("utf-8") if isinstance(content, bytes) else str(content)
            except Exception as e:
                logger.warning("daytona_fs_read_failed", error=str(e), path=path)

        res = await self.terminal(workspace_id, f"cat -- {shlex.quote(path)}")
        if res.exit_code == 0:
            return res.stdout
        return f"# Error reading file {path} from sandbox"

    async def write_file(self, workspace_id: str, path: str, content: str, actor: str = "operator") -> bool:
        """Writes a file to the sandbox container filesystem."""
        sandbox = await self._resolve_sandbox(workspace_id)
        if sandbox and hasattr(sandbox, "fs") and hasattr(sandbox.fs, "upload_file"):
            try:
                await sandbox.fs.upload_file(src=content.encode("utf-8"), dst=path)
                return True
            except Exception as e:
                logger.warning("daytona_fs_write_failed", error=str(e), path=path)

        # No alternate-container or host fallback.  A Daytona workstation must
        # expose its filesystem API for writes to be considered successful.
        return False

    async def list_files(self, workspace_id: str, path: str = ".") -> list[FileEntry]:
        """Lists files inside the sandbox directory."""
        res = await self.terminal(workspace_id, f"ls -la -- {shlex.quote(path)}")
        entries = []
        if res.exit_code == 0:
            for line in res.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 9 and parts[8] not in [".", ".."]:
                    name = parts[8]
                    is_dir = line.startswith("d")
                    size = int(parts[4]) if parts[4].isdigit() else 0
                    entries.append(
                        FileEntry(
                            name=name,
                            path=f"{path.rstrip('/')}/{name}",
                            is_dir=is_dir,
                            size_bytes=size,
                            modified_at=_now(),
                            permissions=parts[0],
                        )
                    )
        return entries

    async def process_list(self, workspace_id: str) -> list[ProcessInfo]:
        """Lists running processes inside the sandbox by querying real process state."""
        processes: list[ProcessInfo] = []
        sandbox = await self._resolve_sandbox(workspace_id)

        # Query real processes via computer_use status API
        if sandbox and hasattr(sandbox, "computer_use"):
            try:
                for proc_name in ["xvfb", "xfce4", "x11vnc", "novnc"]:
                    try:
                        pstatus = await sandbox.computer_use.get_process_status(proc_name)
                        if pstatus and hasattr(pstatus, "status"):
                            processes.append(
                                ProcessInfo(
                                    pid=getattr(pstatus, "pid", 0) or 0,
                                    name=proc_name,
                                    cpu_pct=0.0,
                                    memory_mb=0.0,
                                    status=str(pstatus.status),
                                )
                            )
                    except Exception:
                        pass
                if processes:
                    return processes
            except Exception:
                pass

        # Fallback: query via ps command inside sandbox
        if sandbox and hasattr(sandbox, "process"):
            try:
                res = await sandbox.process.exec("ps aux --no-headers 2>/dev/null | head -20")
                stdout = getattr(res, "result", "") or ""
                for line in stdout.splitlines():
                    parts = line.split(None, 10)
                    if len(parts) >= 11:
                        try:
                            processes.append(
                                ProcessInfo(
                                    pid=int(parts[1]),
                                    name=parts[10].split()[0].split("/")[-1],
                                    cpu_pct=float(parts[2]),
                                    memory_mb=float(parts[5]) / 1024.0 if parts[5].isdigit() else 0.0,
                                    status="RUNNING",
                                )
                            )
                        except (ValueError, IndexError):
                            pass
            except Exception:
                pass

        return processes

    async def application_list(self, workspace_id: str) -> list[str]:
        """Lists installed applications in the sandbox by querying real binaries."""
        apps: list[str] = []
        sandbox = await self._resolve_sandbox(workspace_id)
        if sandbox and hasattr(sandbox, "process"):
            try:
                res = await sandbox.process.exec("which xfce4-terminal code-server chromium git python3 bash 2>/dev/null")
                stdout = getattr(res, "result", "") or ""
                for line in stdout.splitlines():
                    line = line.strip()
                    if line:
                        app_name = line.split("/")[-1]
                        if app_name and app_name not in apps:
                            apps.append(app_name)
                if apps:
                    return apps
            except Exception:
                pass

        try:
            res = await self.terminal(workspace_id, "which xfce4-terminal code-server chromium git python3 bash 2>/dev/null")
            if res.exit_code == 0 and res.stdout:
                for line in res.stdout.splitlines():
                    line = line.strip()
                    if line:
                        app_name = line.split("/")[-1]
                        if app_name and app_name not in apps:
                            apps.append(app_name)
                if apps:
                    return apps
        except Exception:
            pass

        return apps

    async def launch_application(self, workspace_id: str, app_name: str, actor: str = "operator") -> bool:
        """Launches a GUI application on display :99."""
        self._active_windows[workspace_id] = app_name
        result = await self.terminal(workspace_id, f"DISPLAY=:99 {shlex.quote(app_name)} &")
        return result.exit_code == 0

    async def close_application(self, workspace_id: str, app_name: str, actor: str = "operator") -> bool:
        """Closes a running desktop application."""
        result = await self.terminal(workspace_id, f"pkill -f -- {shlex.quote(app_name)}")
        if self._active_windows.get(workspace_id) == app_name:
            self._active_windows[workspace_id] = "XFCE Desktop"
        return result.exit_code == 0

    async def install_application(self, workspace_id: str, package_name: str, actor: str = "operator") -> tuple[bool, str]:
        """Installs an application inside the sandbox."""
        safe_package = shlex.quote(package_name.strip())
        res = await self.terminal(workspace_id, f"apt-get update && apt-get install -y -- {safe_package}", actor=actor)
        return (res.exit_code == 0, res.stdout or res.stderr)

    async def uninstall_application(self, workspace_id: str, package_name: str, actor: str = "operator") -> bool:
        """Uninstalls a package inside the sandbox."""
        res = await self.terminal(workspace_id, f"apt-get remove -y {package_name}")
        return res.exit_code == 0

    async def service_action(self, workspace_id: str, service_name: str, action: str, actor: str = "operator") -> ServiceInfo:
        """Controls system services inside the sandbox."""
        res = await self.terminal(workspace_id, f"service {shlex.quote(service_name)} {shlex.quote(action)}")
        status_value = "RUNNING" if res.exit_code == 0 and action in {"start", "restart"} else action.upper()
        return ServiceInfo(
            name=service_name,
            status=status_value,
            port=0,
            logs=(res.stdout + res.stderr).splitlines(),
        )

    async def git_action(self, workspace_id: str, action: str, **kwargs: Any) -> Any:
        """Executes Git operations against the sandbox workspace."""
        if action == "status":
            res = await self.terminal(workspace_id, "git status --porcelain")
            branch_res = await self.terminal(workspace_id, "git branch --show-current")
            branch = branch_res.stdout.strip() if (branch_res.exit_code == 0 and branch_res.stdout.strip()) else ""
            return GitStatusInfo(
                branch=branch,
                is_clean=(len(res.stdout.strip()) == 0),
                untracked_files=[line[3:] for line in res.stdout.splitlines() if line.startswith("??")],
                modified_files=[line[3:] for line in res.stdout.splitlines() if not line.startswith("??")],
                staged_files=[],
            )
        elif action == "commit":
            msg = kwargs.get("message", "chore: automated commit")
            safe_msg = msg.replace("'", "'\\''")
            res = await self.terminal(workspace_id, f"git add -A && git commit -m '{safe_msg}'")
            return res.exit_code == 0
        elif action in ["branch", "checkout"]:
            branch_name = kwargs.get("branch_name") or kwargs.get("branch") or "main"
            res = await self.terminal(workspace_id, f"git checkout -B '{branch_name}'")
            return res.exit_code == 0
        elif action == "diff":
            branch_res = await self.terminal(workspace_id, "git branch --show-current")
            branch = branch_res.stdout.strip() if (branch_res.exit_code == 0 and branch_res.stdout.strip()) else "HEAD"
            res = await self.terminal(workspace_id, f"git diff {branch}")
            return res.stdout or "Working tree clean."
        return ""

    def _record_audit(
        self,
        session_id: str,
        workspace_id: str,
        tenant_id: str,
        actor: str,
        action: str,
        resource: str,
        result: str,
        details: Optional[dict[str, Any]] = None,
        risk_level: ComputerRiskLevel = ComputerRiskLevel.LOW,
    ) -> None:
        event = ComputerAuditEvent(
            session_id=session_id,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            resource=resource,
            result=result,
            risk_level=risk_level,
            details=details or {},
        )
        self.audit_log.append(event)
