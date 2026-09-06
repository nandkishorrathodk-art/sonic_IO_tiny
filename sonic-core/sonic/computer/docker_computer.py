"""
SONIC A-SEA — Docker Cyber Workstation Provider
================================================
First-class native Linux Workstation provider operating inside Docker
(sonic-desktop-workstation). Replaces cloud sandboxes (Daytona/E2B)
with a full, unrestricted, self-contained cyber environment:
- Desktop GUI: XFCE4, Xvfb :99 (1280x800x24), xdotool, wmctrl, ImageMagick
- Interactive Streaming: x11vnc (:5900) + noVNC websockify (:6080)
- Web Browser: Google Chrome Stable (unrestricted internet)
- Terminal & Security Tools: nmap, net-tools, python3, bash, git
- Zero cloud rate limits or connection resets.
"""

from __future__ import annotations

import asyncio
import base64
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


class DockerComputerProvider(ComputerProvider):
    """Native Docker-based Workstation Provider for SONIC A-SEA."""

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
        self._daemon_checked: bool | None = None
        self._default_workspace_id = self.container_name

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

    async def _docker_exec(self, cmd: str, timeout: int = 60) -> tuple[int, str, str]:
        """Execute a bash command inside the docker container."""
        if not shutil.which("docker"):
            return 127, "", "docker binary not found on host"
        if self._daemon_checked is None:
            probe = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            self._daemon_checked = probe.returncode == 0
        if not self._daemon_checked:
            return 126, "", "docker daemon is unreachable; command execution failed-closed"
        try:
            exec_args = ["docker", "exec", self.container_name, "bash", "-c", cmd]
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
            return exit_code, stdout_str, stderr_str
        except asyncio.TimeoutError:
            return 124, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            # Infra failure (daemon down, exec error) is a fail-closed condition.
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
        ws = self._ensure_default_workspace(tenant_id)
        ws.tenant_id = tenant_id
        ws.engagement_id = engagement_id
        return ws

    async def destroy(self, workspace_id: str) -> bool:
        if workspace_id in self.workspaces:
            del self.workspaces[workspace_id]
        return True

    async def get_vnc_url(self, workspace_id: str) -> str | None:
        port = os.environ.get("SONIC_WORKSTATION_VNC_PORT", "6080")
        return f"http://localhost:{port}/vnc.html"

    async def get_stream_url(self, workspace_id: str) -> str | None:
        return await self.get_vnc_url(workspace_id)

    # -------------------------------------------------------------
    # Status & Telemetry
    # -------------------------------------------------------------

    async def status(self, workspace_id: str) -> ComputerState:
        ws = self._ensure_default_workspace()
        active_window = "Desktop"
        open_windows: list[str] = ["Desktop", "Terminal"]

        # Check real open windows via wmctrl
        code, out, _ = await self._docker_exec("DISPLAY=:99 wmctrl -l 2>/dev/null", timeout=5)
        if code == 0 and out.strip():
            for line in out.splitlines():
                parts = line.split(maxsplit=3)
                if len(parts) >= 4:
                    title = parts[3].strip()
                    if title and title not in ("xfce4-panel", "Desktop") and title not in open_windows:
                        open_windows.append(title)

        # Check active window via xdotool
        code, out, _ = await self._docker_exec("DISPLAY=:99 xdotool getactivewindow getwindowname 2>/dev/null", timeout=5)
        if code == 0 and out.strip():
            active_window = out.strip()
        else:
            active_window = open_windows[-1] if len(open_windows) > 2 else "Desktop"

        # Check running processes
        procs = await self.process_list(workspace_id)
        proc_names = [p.name for p in procs]

        return ComputerState(
            workspace_id=workspace_id or self.container_name,
            tenant_id=ws.tenant_id,
            status=ComputerWorkspaceStatus.RUNNING,
            active_application=active_window,
            open_applications=open_windows,
            active_window=active_window,
            working_directory="/root",
            running_processes=proc_names,
            installed_applications=["google-chrome-stable", "xfce4-terminal", "thunar", "nmap", "xdotool", "wmctrl"],
            current_project="sonic-repo",
            git_branch="main",
            resource_usage={"cpu_pct": 5.0, "memory_mb": 512.0},
        )

    # -------------------------------------------------------------
    # Multi-Modal Perception: Screen Observation
    # -------------------------------------------------------------

    async def screenshot(self, workspace_id: str) -> ScreenObservation:
        scr_cmd = (
            "DISPLAY=:99 import -window root /tmp/sonic_screen.png 2>/dev/null && "
            "(LOC=$(DISPLAY=:99 xdotool getmouselocation --shell 2>/dev/null); "
            "if [ $? -eq 0 ] && [ -n \"$LOC\" ]; then eval \"$LOC\"; "
            "DISPLAY=:99 convert /tmp/sonic_screen.png -stroke black -strokewidth 1 -fill '#00ffcc' "
            "-draw \"polygon $X,$Y $(($X+15)),$(($Y+12)) $(($X+9)),$(($Y+12)) $(($X+14)),$(($Y+22)) $(($X+10)),$(($Y+24)) $(($X+5)),$(($Y+14)) $X,$(($Y+18))\" "
            "/tmp/sonic_screen.png 2>/dev/null || true; fi) && "
            "base64 -w0 /tmp/sonic_screen.png"
        )
        code, out, _ = await self._docker_exec(scr_cmd, timeout=10)
        b64 = out.strip() if code == 0 else ""

        # Extract visible text from active window
        visible_text = ""
        code, txt_out, _ = await self._docker_exec(
            "DISPLAY=:99 xdotool getactivewindow getwindowname 2>/dev/null", timeout=5
        )
        if code == 0 and txt_out.strip():
            visible_text = f"Active Window: {txt_out.strip()}"

        return ScreenObservation(
            screenshot_base64=b64,
            width=1280,
            height=800,
            active_window=txt_out.strip() if code == 0 and txt_out.strip() else "Desktop",
            visible_text=visible_text,
            detected_controls=[],
            desktop_state="INTERACTIVE" if b64 else "NO_DISPLAY",
        )

    # -------------------------------------------------------------
    # Graphical Actions (Human Takeover & Agent GUI Actions)
    # -------------------------------------------------------------

    async def gui_action(
        self,
        workspace_id: str,
        action: GUIAction,
        actor: str = "operator",
    ) -> ScreenObservation:
        atype = action.action

        if atype in (GUIActionType.CLICK, GUIActionType.DOUBLE_CLICK):
            repeat = 2 if atype == GUIActionType.DOUBLE_CLICK else 1
            if action.x is not None and action.y is not None:
                await self._docker_exec(f"DISPLAY=:99 xdotool mousemove {action.x} {action.y} click --repeat {repeat} 1")
            else:
                await self._docker_exec(f"DISPLAY=:99 xdotool click --repeat {repeat} 1")

        elif atype == GUIActionType.MOVE and action.x is not None and action.y is not None:
            await self._docker_exec(f"DISPLAY=:99 xdotool mousemove {action.x} {action.y}")

        elif atype == GUIActionType.DRAG:
            sx, sy = action.x or 0, action.y or 0
            dx = action.x2 if action.x2 is not None else sx
            dy = action.y2 if action.y2 is not None else sy
            await self._docker_exec(f"DISPLAY=:99 xdotool mousemove {sx} {sy} mousedown 1 mousemove {dx} {dy} mouseup 1")

        elif atype == GUIActionType.TYPE and action.text:
            safe_text = shlex.quote(action.text)
            await self._docker_exec(f"DISPLAY=:99 xdotool type --clearmodifiers {safe_text}")

        elif atype == GUIActionType.KEYPRESS and action.key:
            safe_key = shlex.quote(action.key)
            await self._docker_exec(f"DISPLAY=:99 xdotool key {safe_key}")

        elif atype == GUIActionType.SCROLL:
            btn = 5 if action.scroll_delta < 0 else 4
            times = abs(action.scroll_delta) if action.scroll_delta != 0 else 3
            await self._docker_exec(f"DISPLAY=:99 xdotool click --repeat {times} {btn}")

        elif atype == GUIActionType.OPEN_APP and action.app_name:
            app = action.app_name.strip().lower()
            if "chrome" in app or "browser" in app:
                spawn = "DISPLAY=:99 nohup /usr/local/bin/chrome >/dev/null 2>&1 &"
            elif "term" in app:
                spawn = "DISPLAY=:99 nohup xfce4-terminal >/dev/null 2>&1 &"
            elif "thunar" in app or "file" in app:
                spawn = "DISPLAY=:99 nohup thunar >/dev/null 2>&1 &"
            else:
                spawn = f"DISPLAY=:99 nohup {shlex.quote(action.app_name)} >/dev/null 2>&1 &"
            await self._docker_exec(spawn)

        elif atype == GUIActionType.CLOSE_APP and action.app_name:
            await self._docker_exec(f"pkill -f -- {shlex.quote(action.app_name)}")

        elif atype == GUIActionType.SELECT_WINDOW and action.window_id:
            await self._docker_exec(f"DISPLAY=:99 wmctrl -i -a {shlex.quote(action.window_id)}")

        await asyncio.sleep(0.3)
        return await self.screenshot(workspace_id)

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
        code, out, _ = await self._docker_exec("which google-chrome-stable xfce4-terminal thunar nmap xdotool wmctrl python3 bash git 2>/dev/null", timeout=10)
        apps = []
        if code == 0 and out.strip():
            for line in out.splitlines():
                line = line.strip()
                if line:
                    app = line.split("/")[-1]
                    if app and app not in apps:
                        apps.append(app)
        return apps or ["google-chrome-stable", "xfce4-terminal", "thunar", "nmap", "python3", "bash"]

    async def launch_application(self, workspace_id: str, app_name: str, actor: str = "operator") -> bool:
        action = GUIAction(action=GUIActionType.OPEN_APP, app_name=app_name)
        await self.gui_action(workspace_id, action, actor=actor)
        return True

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
