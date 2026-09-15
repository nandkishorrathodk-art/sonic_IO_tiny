"""
SONIC A-SEA — Docker Cyber Workstation Provider
================================================
First-class native Linux Workstation provider operating inside Docker
(sonic-desktop-workstation). Replaces cloud sandboxes (Daytona/E2B)
with a full, unrestricted, self-contained cyber environment:
- Desktop GUI: XFCE4, Xvfb :99 (1280x800x24), xdotool, wmctrl, ImageMagick
- Interactive Streaming: x11vnc (:5900) + noVNC websockify (:6080)
- Graphical desktop applications and an isolated operator workspace
- Zero cloud rate limits or connection resets.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import shlex
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from sonic.sandbox.provider import ExecResult

logger = get_logger(__name__)


def _get_display(workspace_id: str | None = None) -> str:
    """Check if environment has DISPLAY, default to :99 if running docker Xvfb."""
    return os.environ.get("DISPLAY") or ":99"


def _docker_binary() -> str | None:
    """Resolve Docker even when the backend is launched without the user PATH."""
    configured = os.environ.get("SONIC_DOCKER_BIN", "").strip()
    if configured:
        return configured if Path(configured).exists() else None
    found = shutil.which("docker")
    if found:
        return found
    if os.name == "nt":
        for candidate in (
            r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
            r"C:\ProgramData\DockerDesktop\version-bin\docker.exe",
        ):
            if Path(candidate).exists():
                return candidate
    return None


class DockerComputerProvider(ComputerProvider):
    """Native Docker-based Workstation Provider for SONIC A-SEA."""

    def _get_display(self, workspace_id: str | None = None) -> str:
        """Check if environment has DISPLAY, default to :99 if running docker Xvfb."""
        return _get_display(workspace_id)

    def __init__(
        self,
        container_name: str = "sonic-desktop-workstation",
        app_policy: ApplicationPolicy | None = None,
    ):
        self.container_name = os.environ.get("SONIC_DOCKER_WORKSTATION_CONTAINER", container_name).strip()
        self.app_policy = app_policy or ApplicationPolicy()
        self.workspaces: dict[str, ComputerWorkspace] = {}
        self._active_windows: dict[str, str] = {}
        self.audit_log: list[ComputerAuditEvent] = []
        self._last_exec: tuple[str, int, str, str] | None = None  # (cmd, exit, stdout, stderr)
        self._daemon_checked: bool | None = None
        self._daemon_checked_at: float | None = None
        self._container_running_cache: bool = False
        self._container_checked_at: float | None = None
        self._default_workspace_id = self.container_name
        # A single Docker desktop is not a tenant-isolated resource.  Refuse
        # cross-tenant reuse rather than silently moving ownership on every
        # create() call.
        self._workspace_owner: str | None = None
        self._exec_semaphore = asyncio.Semaphore(10)
        self._gui_lock = asyncio.Lock()
        self._last_screenshot: ScreenObservation | None = None
        self._last_screenshot_time: float = 0.0

    def _ensure_default_workspace(self, tenant_id: str = "default", engagement_id: str = "default") -> ComputerWorkspace:
        if self._default_workspace_id not in self.workspaces:
            ws = ComputerWorkspace(
                id=self._default_workspace_id,
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                workspace_type=ComputerWorkspaceType.MISSION_COMPUTER,
                profile=ComputerProfile.KALI_SECURITY,
                provider_type="DockerComputerProvider",
                image="sonic-workstation:latest",
                status=ComputerWorkspaceStatus.READY,
            )
            self.workspaces[self._default_workspace_id] = ws
        return self.workspaces[self._default_workspace_id]

    @property
    def name(self) -> str:
        return "DockerComputerProvider"

    async def _container_is_running(self) -> bool:
        """Probe the real Docker container state (fail-closed, short TTL cache)."""
        docker = _docker_binary()
        if not docker:
            return False
        now = asyncio.get_event_loop().time()
        if self._container_checked_at is not None and (now - self._container_checked_at) < 1.5:
            return self._container_running_cache
        try:
            probe = await asyncio.to_thread(
                subprocess.run,
                [docker, "inspect", "-f", "{{.State.Running}}", self.container_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            running = probe.stdout.decode("utf-8", errors="ignore").strip() == "true"
        except Exception:
            running = False
        self._container_running_cache = running
        self._container_checked_at = now
        return running

    async def _provision_workstation(self) -> bool:
        """Try to bring up the workstation container from repo compose files.

        Gated bye SONIC_AUTO_PROVISION_WORKSTATION (default off) — a full
        XFCE desktop image build can take minutes and should never silently
        trigger from a polling/status code path.
        """
        if os.environ.get("SONIC_AUTO_PROVISION_WORKSTATION", "0").strip() != "1":
            return False
        docker = _docker_binary()
        if not docker:
            return False

        candidates = [
            Path.cwd() / "docker-compose.yml",
            Path.cwd() / "docker-compose.prod.yml",
            Path.cwd().parent / "docker-compose.yml",
            Path(__file__).resolve().parents[3] / "docker-compose.yml",
        ]
        compose_file = next((p for p in candidates if p.exists()), None)
        if compose_file is None:
            logger.error("workstation_auto_provision_no_compose_file")
            return False
        try:
            proc = await asyncio.create_subprocess_exec(
                docker, "compose", "-f", str(compose_file), "up", "-d", "workstation",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
            if proc.returncode == 0:
                logger.info("workstation_auto_provisioned", container=self.container_name)
                return True
            logger.error("workstation_auto_provision_failed", error=stderr.decode("utf-8", errors="replace").strip()[:400])
            return False
        except Exception as e:
            logger.error("workstation_auto_provision_exception", error=str(e))
            return False

    async def _docker_exec(self, cmd: str, timeout: int = 60) -> tuple[int, str, str]:
        """Execute a bash command inside the docker container."""
        docker = _docker_binary()
        if not docker:
            return 127, "", "docker binary not found on host"
        if not await self._container_is_running():
            return 125, "", f"container {self.container_name} is not running; command blocked fail-closed"
        now = asyncio.get_event_loop().time()
        if (
            self._daemon_checked is None
            or not self._daemon_checked
            or (self._daemon_checked_at is not None and (now - self._daemon_checked_at) > 10.0)
        ):
            try:
                probe = await asyncio.to_thread(
                    subprocess.run,
                    [docker, "info", "--format", "{{.ServerVersion}}"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=10,
                )
                self._daemon_checked = probe.returncode == 0
                self._daemon_checked_at = now
            except Exception:
                self._daemon_checked = False
                self._daemon_checked_at = now
        if not self._daemon_checked:
            return 126, "", "docker daemon is unreachable; command execution failed-closed"
        async with self._exec_semaphore:
            try:
                exec_args = [docker, "exec", self.container_name, "bash", "-c", cmd]
                proc = await asyncio.create_subprocess_exec(
                    *exec_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout if timeout > 0 else 60,
                )
                exit_code = proc.returncode if proc.returncode is not None else 0
                stdout_str = stdout_data.decode("utf-8", errors="replace")
                stderr_str = stderr_data.decode("utf-8", errors="replace")
                self._last_exec = (cmd, exit_code, stdout_str, stderr_str)
                return exit_code, stdout_str, stderr_str
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await asyncio.sleep(0.05)
                except Exception:
                    pass
                return 124, "", f"Command timed out after {timeout} seconds"
            except Exception as e:
                try:
                    proc.kill()
                    await asyncio.sleep(0.05)
                except Exception:
                    pass
                return 126, "", str(e)

    # -------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------

    async def create(
        self,
        tenant_id: str,
        engagement_id: str,
        workspace_type: ComputerWorkspaceType = ComputerWorkspaceType.MISSION_COMPUTER,
        profile: ComputerProfile = ComputerProfile.KALI_SECURITY,
    ) -> ComputerWorkspace:
        if self._workspace_owner and self._workspace_owner != tenant_id:
            raise RuntimeError(
                "shared Docker workstation is already owned by another tenant; "
                "provision a dedicated workstation"
            )
        ws = self._ensure_default_workspace(tenant_id)
        self._workspace_owner = tenant_id
        ws.tenant_id = tenant_id
        ws.engagement_id = engagement_id
        if not await self._container_is_running():
            provisioned = await self._provision_workstation()
            if not provisioned:
                # Try to start existing container if it exists but is stopped
                try:
                    await asyncio.to_thread(
                        subprocess.run,
                        [docker, "start", self.container_name],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        timeout=10,
                    )
                    # Give container time to start
                    await asyncio.sleep(2)
                    self._container_running_cache = True
                    self._container_checked_at = asyncio.get_event_loop().time()
                except Exception:
                    # Fail-closed: never report a desktop that was not actually provisioned.
                    ws.status = ComputerWorkspaceStatus.STOPPED if _docker_binary() else ComputerWorkspaceStatus.FAILED
                    return ws
            else:
                self._container_running_cache = True
                self._container_checked_at = asyncio.get_event_loop().time()
        ws.status = ComputerWorkspaceStatus.RUNNING
        return ws

    async def get_or_create_home(self, tenant_id: str) -> ComputerWorkspace:
        """Return the tenant's long-lived MISSION_COMPUTER home (persistent body)."""
        if self._workspace_owner and self._workspace_owner != tenant_id:
            raise RuntimeError(
                "shared Docker workstation is already owned by another tenant"
            )
        for ws in self.workspaces.values():
            if (
                ws.tenant_id == tenant_id
                and ws.workspace_type == ComputerWorkspaceType.MISSION_COMPUTER
                and ws.status not in (ComputerWorkspaceStatus.DESTROYED, ComputerWorkspaceStatus.FAILED)
            ):
                logger.info(
                    "home_workstation_reused",
                    workspace_id=ws.id,
                    tenant_id=tenant_id,
                )
                return ws
        ws = ComputerWorkspace(
            id=f"home-{tenant_id}",
            tenant_id=tenant_id,
            name="MISSION_COMPUTER",
            workspace_type=ComputerWorkspaceType.MISSION_COMPUTER,
            status=ComputerWorkspaceStatus.RUNNING,
        )
        self.workspaces[ws.id] = ws
        self._workspace_owner = tenant_id
        return ws

    async def destroy(self, workspace_id: str) -> bool:
        if workspace_id in self.workspaces:

            del self.workspaces[workspace_id]
        if workspace_id == self._default_workspace_id:
            self._workspace_owner = None
        return True

    async def close(self) -> None:
        """Release provider resources (no-op for statelessdocker CLI wrapper)."""

        return None

    async def get_vnc_url(self, workspace_id: str) -> str | None:
        # Fail-closed: a stream URL is only real when the container actually
        # runs and a VNC/noVNC listener is reachable on the configured port.
        if not await self._container_is_running():
            return None
        port = os.environ.get("SONIC_WORKSTATION_VNC_PORT", "6080")
        code, out, _ = await self._docker_exec(
            f"if (exec 3<>/dev/tcp/127.0.0.1/{port}) 2>/dev/null; then echo 0; else echo 1; fi",
            timeout=8,
        )
        if code == 0 and out.strip() == "0":
            return f"http://localhost:{port}/vnc.html"
        return None

    async def get_stream_url(self, workspace_id: str) -> str | None:
        return await self.get_vnc_url(workspace_id)

    # -------------------------------------------------------------
    # Status & Telemetry
    # -------------------------------------------------------------

    async def status(self, workspace_id: str) -> ComputerState:
        ws = self._ensure_default_workspace()
        if not await self._container_is_running():
            # Fail-closed: no synthetic RUNNING/apps/windows when the container
            # does not actually exist. Report DEGRADED and empty telemetry.

            ws.status = ComputerWorkspaceStatus.DEGRADED
            return ComputerState(
                workspace_id=workspace_id or self.container_name,
                tenant_id=ws.tenant_id,
                status=ComputerWorkspaceStatus.DEGRADED,
                active_application="",
                open_applications=[],
                active_window="",
                working_directory="/root",
                running_processes=[],
                installed_applications=[],
                current_project="",
                git_branch="",
                resource_usage={},
            )

        ws.status = ComputerWorkspaceStatus.RUNNING
        disp = self._get_display(workspace_id)
        active_window = "Desktop"
        open_windows: list[str] = ["Desktop", "Terminal"]  # Default fallback for running container

        # Check real open windows via wmctrl
        code, out, _ = await self._docker_exec(f"DISPLAY={disp} wmctrl -l 2>/dev/null", timeout=5)
        if code == 0 and out.strip():
            for line in out.splitlines():
                parts = line.split(maxsplit=3)
                if len(parts) >= 4:
                    title = parts[3].strip()
                    if title and title not in ("xfce4-panel", "Desktop") and title not in open_windows:
                        open_windows.append(title)
        
        # Always ensure Desktop is in the list for running containers
        if "Desktop" not in open_windows:
            open_windows.insert(0, "Desktop")

        # Check active window via xdotool
        code, out, _ = await self._docker_exec(f"DISPLAY={disp} xdotool getactivewindow getwindowname 2>/dev/null", timeout=5)
        if code == 0 and out.strip():
            active_window = out.strip()
        else:
            active_window = open_windows[-1] if len(open_windows) > 2 else "Desktop"

        # Check running processes
        procs = await self.process_list(workspace_id)
        proc_names = [p.name for p in procs]
        installed = await self.application_list(workspace_id)

        return ComputerState(
            workspace_id=workspace_id or self.container_name,
            tenant_id=ws.tenant_id,
            status=ComputerWorkspaceStatus.RUNNING,
            active_application=active_window,
            open_applications=open_windows,
            active_window=active_window,
            working_directory="/root",
            running_processes=proc_names,
            installed_applications=installed,
            current_project="sonic-repo",
            git_branch="main",
            resource_usage={"cpu_pct": 5.0, "memory_mb": 512.0},
        )

    # -------------------------------------------------------------
    # Multi-Modal Perception: Screen Observation
    # -------------------------------------------------------------

    async def screenshot(self, workspace_id: str) -> ScreenObservation:
        now = asyncio.get_event_loop().time()
        if self._last_screenshot is not None and (now - self._last_screenshot_time) < 2.0:
            return self._last_screenshot

        disp = self._get_display(workspace_id)
        scr_cmd = (
            f"DISPLAY={disp} scrot -o /tmp/sonic_screen.png 2>/dev/null || "
            f"DISPLAY={disp} import -window root /tmp/sonic_screen.png 2>/dev/null; "
            f"base64 -w0 /tmp/sonic_screen.png 2>/dev/null && "
            f"echo '___ACTIVE_WINDOW___' && "
            f"DISPLAY={disp} xdotool getactivewindow getwindowname 2>/dev/null || true"
        )
        code, out, _ = await self._docker_exec(scr_cmd, timeout=15)
        b64 = ""
        active_win = "Desktop"
        if code == 0 and out:
            if "___ACTIVE_WINDOW___" in out:
                parts = out.split("___ACTIVE_WINDOW___", 1)
                b64 = parts[0].strip()
                active_win = parts[1].strip() or "Desktop"
            else:
                b64 = out.strip()

        obs = ScreenObservation(
            screenshot_base64=b64,
            width=1280,
            height=800,
            active_window=active_win,
            visible_text=f"Active Window: {active_win}" if active_win != "Desktop" else "",
            detected_controls=[],
            desktop_state="INTERACTIVE" if b64 else "NO_DISPLAY",
        )
        if b64:
            self._last_screenshot = obs
            self._last_screenshot_time = now
        return obs

    # -------------------------------------------------------------
    # Graphical Actions (Human Takeover & Agent GUI Actions)
    # -------------------------------------------------------------

    async def gui_action(
        self,
        workspace_id: str,
        action: GUIAction,
        actor: str = "operator",
    ) -> ScreenObservation:
        async with self._gui_lock:
            atype = action.action
            disp = self._get_display(workspace_id)

            async def exec_gui(command: str) -> None:
                code, _, err = await self._docker_exec(command)
                if code != 0:
                    raise RuntimeError(f"GUI action failed with exit code {code}: {err.strip()}")

            if atype in (GUIActionType.CLICK, GUIActionType.DOUBLE_CLICK):
                repeat = 2 if atype == GUIActionType.DOUBLE_CLICK else 1
                if action.x is not None and action.y is not None:
                    await exec_gui(f"DISPLAY={disp} xdotool mousemove {action.x} {action.y} click --repeat {repeat} 1")
                else:
                    await exec_gui(f"DISPLAY={disp} xdotool click --repeat {repeat} 1")

            elif atype == GUIActionType.RIGHT_CLICK:
                if action.x is not None and action.y is not None:
                    await exec_gui(f"DISPLAY={disp} xdotool mousemove {action.x} {action.y} click 3")
                else:
                    await exec_gui(f"DISPLAY={disp} xdotool click 3")

            elif atype == GUIActionType.MOVE and action.x is not None and action.y is not None:
                await exec_gui(f"DISPLAY={disp} xdotool mousemove {action.x} {action.y}")

            elif atype == GUIActionType.DRAG:
                sx, sy = action.x or 0, action.y or 0
                dx = action.x2 if action.x2 is not None else sx
                dy = action.y2 if action.y2 is not None else sy
                await exec_gui(f"DISPLAY={disp} xdotool mousemove {sx} {sy} mousedown 1 mousemove {dx} {dy} mouseup 1")

            elif atype == GUIActionType.TYPE and action.text:
                safe_text = shlex.quote(action.text)
                await exec_gui(f"DISPLAY={disp} xdotool type --delay 25 --clearmodifiers {safe_text}")

            elif atype == GUIActionType.KEYPRESS and action.key:
                safe_key = shlex.quote(action.key)
                await exec_gui(f"DISPLAY={disp} xdotool key {safe_key}")

            elif atype == GUIActionType.SCROLL:
                btn = 5 if action.scroll_delta < 0 else 4
                times = abs(action.scroll_delta) if action.scroll_delta != 0 else 3
                await exec_gui(f"DISPLAY={disp} xdotool click --repeat {times} {btn}")

            elif atype == GUIActionType.OPEN_APP and action.app_name:
                clean_app = action.app_name.strip()
                parts = shlex.split(clean_app) if clean_app else []
                if parts:
                    spawn = f"DISPLAY={disp} nohup {' '.join(shlex.quote(p) for p in parts)} >/dev/null 2>&1 &"
                    await exec_gui(spawn)
                    self._active_windows[workspace_id] = parts[0]

            elif atype == GUIActionType.CLOSE_APP and action.app_name:
                await exec_gui(f"pkill -f -- {shlex.quote(action.app_name)}")

            elif atype == GUIActionType.SELECT_WINDOW:
                target = action.window_id or action.app_name
                if target:
                    await self._docker_exec(
                        f"DISPLAY={disp} (wmctrl -i -a {shlex.quote(target)} 2>/dev/null || "
                        f"wmctrl -a {shlex.quote(target)} 2>/dev/null || "
                        f"xdotool search --name {shlex.quote(target)} windowactivate 2>/dev/null) || true"
                    )

            # Invalidate 2-second cache so fresh post-action screen is captured
            self._last_screenshot_time = 0.0
            await asyncio.sleep(0.3)
            return await self.screenshot(workspace_id)

    async def tile_workstation(self, workspace_id: str) -> bool:
        """
        Executes wmctrl commands to tile windows side-by-side:
        - First discovered application window: left half
        - Second discovered application window: right half
        Discovers open windows dynamically via wmctrl while maintaining compatibility
        with direct wmctrl targeting.
        """
        disp = self._get_display(workspace_id)
        windows: list[tuple[str, str]] = []
        code_l, out_l, _ = await self._docker_exec(f"DISPLAY={disp} wmctrl -l 2>/dev/null", timeout=5)
        if code_l == 0 and out_l.strip():
            for line in out_l.splitlines():
                parts = line.split(maxsplit=3)
                if len(parts) >= 4:
                    win_id = parts[0]
                    title = parts[3].strip()
                    if title and title not in ("xfce4-panel", "Desktop"):
                        windows.append((win_id, title))

        code1 = 1
        code2 = 1
        client_windows = [w for w in windows if w[1] not in ("xfce4-panel", "Desktop", "desktop")]
        if client_windows:
            left_win = client_windows[0]
            code1, _, _ = await self._docker_exec(f'DISPLAY={disp} wmctrl -i -r "{left_win[0]}" -e 0,0,0,640,800')
            if len(client_windows) > 1:
                right_win = client_windows[1]
                code2, _, _ = await self._docker_exec(f'DISPLAY={disp} wmctrl -i -r "{right_win[0]}" -e 0,640,0,640,800')

        return (not windows and code_l == 0) or code1 == 0 or code2 == 0

    async def settle_screen(
        self,
        workspace_id: str,
        max_wait: float = 2.0,
        interval: float = 0.3,
    ) -> ScreenObservation:
        """
        Captures screenshots with interval. When two consecutive screenshot
        hashes match (screen is static / loaded), returns the settled observation.
        """
        def _calc_hash(obs: ScreenObservation) -> str:
            payload = (obs.screenshot_base64 or f"{obs.active_window}:{obs.visible_text}" or "empty").encode("utf-8")
            return hashlib.md5(payload).hexdigest()

        start = asyncio.get_event_loop().time()
        self._last_screenshot_time = 0.0
        last_obs = await self.screenshot(workspace_id)
        last_hash = _calc_hash(last_obs)

        while (asyncio.get_event_loop().time() - start) < max_wait:
            await asyncio.sleep(interval)
            self._last_screenshot_time = 0.0
            curr_obs = await self.screenshot(workspace_id)
            curr_hash = _calc_hash(curr_obs)
            if curr_hash == last_hash:
                return curr_obs
            last_obs = curr_obs
            last_hash = curr_hash

        return last_obs

    # -------------------------------------------------------------
    # Terminal PTY Execution
    # -------------------------------------------------------------

    async def terminal(
        self,
        workspace_id: str,
        command: str,
        timeout: int = 60,
        actor: str = "operator",
    ) -> ExecResult:
        code, stdout, stderr = await self._docker_exec(command, timeout=timeout)
        return ExecResult(
            command=command,
            exit_code=code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=0.0,
            timed_out=(code == 124),
            sandbox_id=self.container_name,
        )

    async def execute(
        self,
        workspace_id: str,
        command: str | list[str],
        timeout: int = 60,
        actor: str = "operator",
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> ExecResult:
        """Executes a command inside the container (ComputeProvider interface for SecurityTool)."""
        if isinstance(command, list):
            cmd_str = " ".join(shlex.quote(c) for c in command)
        else:
            cmd_str = str(command)
        if cwd:
            cmd_str = f"cd {shlex.quote(cwd)} && {cmd_str}"
        return await self.terminal(workspace_id, cmd_str, timeout=timeout, actor=actor)

    # -------------------------------------------------------------
    # Filesystem & Git Operations
    # -------------------------------------------------------------

    async def read_file(self, workspace_id: str, path: str) -> str:
        code, out, _ = await self._docker_exec(f"cat {shlex.quote(path)}", timeout=10)
        return out if code == 0 else ""

    async def write_file(self, workspace_id: str, path: str, content: str, actor: str = "operator") -> bool:
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", "-i", self.container_name, "sh", "-c", f"cat > {shlex.quote(path)}",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate(input=content.encode("utf-8"))
        return proc.returncode == 0

    async def list_files(self, workspace_id: str, path: str = ".") -> list[FileEntry]:
        code, out, _ = await self._docker_exec(f"ls -la {shlex.quote(path)} 2>/dev/null", timeout=10)
        entries: list[FileEntry] = []
        if code == 0 and out.strip():
            for line in out.splitlines()[1:]:  # skip 'total'
                parts = line.split(maxsplit=8)
                if len(parts) >= 9:
                    fname = parts[8].strip()
                    if fname not in (".", ".."):
                        is_dir = parts[0].startswith("d")
                        entries.append(
                            FileEntry(
                                path=f"{path}/{fname}".replace("//", "/"),
                                name=fname,
                                is_directory=is_dir,
                                size_bytes=int(parts[4]) if parts[4].isdigit() else 0,
                            )
                        )
        return entries

    async def git_action(
        self,
        workspace_id: str,
        action: str,
        args: list[str] | None = None,
        actor: str = "operator",
    ) -> GitStatusInfo:
        cmd = f"git -C /root/workspace {action} " + " ".join(shlex.quote(a) for a in (args or []))
        code, out, _ = await self._docker_exec(cmd, timeout=15)
        clean = "nothing to commit" in out.lower()
        branch = "main"
        if "on branch" in out.lower():
            for line in out.splitlines():
                if "on branch" in line.lower():
                    branch = line.split()[-1]
                    break
        return GitStatusInfo(branch=branch, is_clean=clean, modified_files=[])

    async def process_list(self, workspace_id: str) -> list[ProcessInfo]:
        code, out, _ = await self._docker_exec("ps -eo pid,user,%cpu,%mem,comm --no-headers 2>/dev/null | head -30", timeout=5)
        procs: list[ProcessInfo] = []
        if code == 0 and out.strip():
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5:
                    procs.append(
                        ProcessInfo(
                            pid=int(parts[0]) if parts[0].isdigit() else 0,
                            name=parts[4],
                            cpu_pct=float(parts[2]) if parts[2].replace(".", "").isdigit() else 0.0,
                            memory_mb=float(parts[3]) if parts[3].replace(".", "").isdigit() else 0.0,
                        )
                    )
        return procs

    async def install_application(self, workspace_id: str, package_name: str, actor: str = "operator") -> tuple[bool, str]:
        allowed, reason = self.app_policy.is_package_allowed(package_name)
        if not allowed:
            return False, reason
        code, out, err = await self._docker_exec(f"DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y {shlex.quote(package_name)}", timeout=180)
        return (code == 0), out if code == 0 else err

    async def uninstall_application(self, workspace_id: str, package_name: str, actor: str = "operator") -> bool:
        code, _, _ = await self._docker_exec(f"DEBIAN_FRONTEND=noninteractive apt-get remove -y {shlex.quote(package_name)}", timeout=120)
        return code == 0

    async def application_list(self, workspace_id: str) -> list[str]:
        std_utils = list(dict.fromkeys(self.app_policy.allowed_packages))
        utils_str = " ".join(std_utils)
        discovery_cmd = (
            "find /usr/share/applications /usr/local/share/applications ~/.local/share/applications -name '*.desktop' 2>/dev/null | while read -r f; do "
            "[ -f \"$f\" ] || continue; "
            "b=$(basename \"$f\" .desktop); echo \"$b\"; "
            "ex=$(grep -m1 -E '^Exec=' \"$f\" 2>/dev/null | cut -d= -f2- | awk '{print $1}'); "
            "[ -n \"$ex\" ] && basename \"$ex\"; "
            "done; "
            "find /usr/local/bin -maxdepth 1 -type f 2>/dev/null | while read -r p; do [ -x \"$p\" ] && basename \"$p\"; done; "
            f"for b in {utils_str}; do command -v \"$b\" 2>/dev/null; done; true"
        )
        code, out, _ = await self._docker_exec(discovery_cmd, timeout=10)
        apps: list[str] = []
        if code == 0 and out.strip():
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    continue
                app = line.rsplit("/", 1)[-1].strip()
                if app.endswith(".desktop"):
                    app = app[:-8]
                app = app.strip("\"' ")
                if app and app not in apps:
                    apps.append(app)
        return apps

    async def launch_application(self, workspace_id: str, app_name: str, actor: str = "operator") -> bool:
        clean_app = (app_name or "").strip()
        if not clean_app:
            return False
        parts = shlex.split(clean_app)
        if not parts:
            return False
        if hasattr(self, "app_policy") and self.app_policy:
            allowed, _ = self.app_policy.is_package_allowed(parts[0])
            if not allowed:
                return False
        disp = self._get_display(workspace_id)
        spawn = f"DISPLAY={disp} nohup {' '.join(shlex.quote(p) for p in parts)} >/dev/null 2>&1 &"
        self._active_windows[workspace_id] = parts[0]
        code, _, _ = await self._docker_exec(spawn)
        return code == 0

    async def close_application(self, workspace_id: str, app_name: str, actor: str = "operator") -> bool:
        action = GUIAction(action=GUIActionType.CLOSE_APP, app_name=app_name)
        await self.gui_action(workspace_id, action, actor=actor)
        return True

    async def service_action(self, workspace_id: str, service_name: str, action: str, actor: str = "operator") -> ServiceInfo:
        code, out, err = await self._docker_exec(f"service {shlex.quote(service_name)} {shlex.quote(action)} 2>&1", timeout=30)
        st = "RUNNING" if code == 0 and action in ("start", "restart") else action.upper()
        return ServiceInfo(
            name=service_name,
            status=st,
            port=0,
            logs=(out + err).splitlines(),
        )
