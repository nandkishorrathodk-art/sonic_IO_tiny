"""
SONIC-REDA — Unified Computer Provider Engine (Phase 13)
===========================================================
Provides a unified computer and engineering workspace abstraction for SONIC AI.
Integrates Desktop GUI, Terminal, Filesystem, code-server IDE, Browser,
Applications, Git, Services, and Process management on top of ComputeProviders.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

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
    ProcessInfo,
    ScreenObservation,
    ServiceInfo,
    _new_id,
    _now,
)
from sonic.logger import get_logger
from sonic.sandbox.provider import (
    ComputeProvider,
    ExecResult,
    WorkspaceConfig,
    WorkspaceType,
)

logger = get_logger(__name__)


# =============================================================
# Canonical Abstract ComputerProvider Base Class
# =============================================================

class ComputerProvider(ABC):
    """
    Canonical abstract base class for the SONIC Computer execution body.
    """

    @abstractmethod
    async def create(
        self,
        tenant_id: str,
        engagement_id: str,
        workspace_type: ComputerWorkspaceType = ComputerWorkspaceType.MISSION_COMPUTER,
        profile: ComputerProfile = ComputerProfile.KALI_SECURITY,
    ) -> ComputerWorkspace:
        """Create and initialize a computer workspace."""
        pass

    @abstractmethod
    async def destroy(self, workspace_id: str) -> bool:
        """Terminate and destroy a computer workspace."""
        pass

    @abstractmethod
    async def status(self, workspace_id: str) -> ComputerState:
        """Retrieve complete current state of the computer."""
        pass

    @abstractmethod
    async def screenshot(self, workspace_id: str) -> ScreenObservation:
        """Capture authenticated screen observation."""
        pass

    @abstractmethod
    async def gui_action(self, workspace_id: str, action: GUIAction, actor: str = "operator") -> ScreenObservation:
        """Execute a desktop GUI action and capture updated screen."""
        pass

    @abstractmethod
    async def terminal(self, workspace_id: str, command: str, timeout: int = 60, actor: str = "operator") -> ExecResult:
        """Execute a shell command inside the computer PTY."""
        pass

    @abstractmethod
    async def read_file(self, workspace_id: str, path: str) -> str:
        """Read content from a workspace file."""
        pass

    @abstractmethod
    async def write_file(self, workspace_id: str, path: str, content: str, actor: str = "operator") -> bool:
        """Write content to a workspace file."""
        pass

    @abstractmethod
    async def list_files(self, workspace_id: str, path: str = ".") -> list[FileEntry]:
        """List files in workspace directory."""
        pass

    @abstractmethod
    async def process_list(self, workspace_id: str) -> list[ProcessInfo]:
        """List running processes inside the computer."""
        pass

    @abstractmethod
    async def application_list(self, workspace_id: str) -> list[str]:
        """List installed applications."""
        pass

    @abstractmethod
    async def launch_application(self, workspace_id: str, app_name: str, actor: str = "operator") -> bool:
        """Launch an application on the desktop."""
        pass

    @abstractmethod
    async def close_application(self, workspace_id: str, app_name: str, actor: str = "operator") -> bool:
        """Close a running desktop application."""
        pass

    @abstractmethod
    async def install_application(self, workspace_id: str, package_name: str, actor: str = "operator") -> tuple[bool, str]:
        """Install an approved package/application."""
        pass

    @abstractmethod
    async def uninstall_application(self, workspace_id: str, package_name: str, actor: str = "operator") -> bool:
        """Uninstall a package/application."""
        pass

    @abstractmethod
    async def service_action(self, workspace_id: str, service_name: str, action: str, actor: str = "operator") -> ServiceInfo:
        """Manage services (start, stop, restart, logs)."""
        pass

    @abstractmethod
    async def git_action(self, workspace_id: str, action: str, **kwargs: Any) -> Any:
        """Execute Git version control operations."""
        pass


# =============================================================
# Concrete Unified ComputerProvider Implementation
# =============================================================

class UnifiedComputerProvider(ComputerProvider):
    """
    Unified execution body bridging Desktop GUI, Terminal, Filesystem,
    IDE, Browser, Applications, Git, and Services on top of ComputeProvider.
    """

    def __init__(
        self,
        compute_provider: ComputeProvider,
        app_policy: ApplicationPolicy | None = None,
    ):
        self.compute = compute_provider
        self.app_policy = app_policy or ApplicationPolicy()
        self.workspaces: dict[str, ComputerWorkspace] = {}
        self.sessions: dict[str, ComputerSession] = {}
        self.audit_log: list[ComputerAuditEvent] = []
        self._running_apps: dict[str, set[str]] = {}
        self._installed_apps: dict[str, set[str]] = {}
        self._services: dict[str, dict[str, ServiceInfo]] = {}
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._vfs: dict[str, dict[str, str]] = {}  # workspace_id -> {path: content}
        self._active_window: dict[str, str] = {}  # workspace_id -> active window name

    # -------------------------------------------------------------
    # 1. Lifecycle
    # -------------------------------------------------------------
    async def create(
        self,
        tenant_id: str,
        engagement_id: str,
        workspace_type: ComputerWorkspaceType = ComputerWorkspaceType.MISSION_COMPUTER,
        profile: ComputerProfile = ComputerProfile.KALI_SECURITY,
    ) -> ComputerWorkspace:
        workspace_id = _new_id("ws")
        config = WorkspaceConfig(
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            workspace_type=(
                WorkspaceType.MISSION_COMPUTER
                if workspace_type == ComputerWorkspaceType.MISSION_COMPUTER
                else WorkspaceType.TARGET_SANDBOX
                if workspace_type == ComputerWorkspaceType.TARGET_SANDBOX
                else WorkspaceType.RESEARCH_LAB
            ),
            image="sonic-kali-linux:v1.3.0" if profile == ComputerProfile.KALI_SECURITY else "debian:12-slim",
            cpu_limit="1.0",
            memory_limit="1024M",
            timeout_seconds=600 if workspace_type == ComputerWorkspaceType.MISSION_COMPUTER else 180,
            network_isolated=True,
        )
        created = await self.compute.create_workspace(config)
        if not created:
            raise RuntimeError("Compute provider failed to provision the computer workspace")

        ws = ComputerWorkspace(
            id=workspace_id,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            workspace_type=workspace_type,
            profile=profile,
            provider_type=self.compute.__class__.__name__,
            image=config.image,
            status=ComputerWorkspaceStatus.READY,
        )
        self.workspaces[ws.id] = ws
        self._running_apps[ws.id] = set()
        self._active_window[ws.id] = ""
        self._installed_apps[ws.id] = set()
        self._services[ws.id] = {}

        self._record_audit(
            session_id="system",
            workspace_id=ws.id,
            tenant_id=tenant_id,
            actor="ComputerProvider",
            action="CREATE_COMPUTER",
            resource=ws.id,
            result="SUCCESS",
        )
        logger.info("computer_workspace_created", workspace_id=ws.id, tenant_id=tenant_id)
        return ws

    async def destroy(self, workspace_id: str) -> bool:
        ws = self.workspaces.get(workspace_id)
        if ws:
            ws.status = ComputerWorkspaceStatus.DESTROYING
            await self.compute.destroy_workspace(workspace_id)
            ws.status = ComputerWorkspaceStatus.DESTROYED
            self.workspaces.pop(workspace_id, None)
            self._running_apps.pop(workspace_id, None)
            self._installed_apps.pop(workspace_id, None)
            self._services.pop(workspace_id, None)
            self._vfs.pop(workspace_id, None)
            self._active_window.pop(workspace_id, None)

            self._record_audit(
                session_id="system",
                workspace_id=workspace_id,
                tenant_id=ws.tenant_id,
                actor="ComputerProvider",
                action="DESTROY_COMPUTER",
                resource=workspace_id,
                result="SUCCESS",
            )
            return True
        return False

    async def status(self, workspace_id: str) -> ComputerState:
        ws = self._require_workspace(workspace_id)
        running = list(self._running_apps.get(workspace_id, set()))
        active_app = self._active_window.get(workspace_id, "")
        pwd = await self.compute.execute(workspace_id, "pwd")
        branch = await self.compute.execute(workspace_id, "git branch --show-current 2>/dev/null")

        return ComputerState(
            workspace_id=workspace_id,
            tenant_id=ws.tenant_id,
            active_application=active_app,
            open_applications=running,
            active_window=active_app,
            working_directory=pwd.stdout.strip() if pwd.exit_code == 0 else "",
            running_processes=[],
            installed_applications=sorted(self._installed_apps.get(workspace_id, set())),
            current_project="sonic-repo",
            git_branch=branch.stdout.strip() if branch.exit_code == 0 else "",
            resource_usage={},
        )

    # -------------------------------------------------------------
    # 2. Desktop GUI & Screen Observation
    # -------------------------------------------------------------
    async def screenshot(self, workspace_id: str) -> ScreenObservation:
        self._require_workspace(workspace_id)
        # A generic ComputeProvider has no screen-capture contract. Never
        # manufacture a screenshot; use DaytonaComputerProvider for GUI work.
        return ScreenObservation(
            screenshot_base64="",
            width=0,
            height=0,
            active_window="",
            visible_text="",
            detected_controls=[],
            desktop_state="NO_DISPLAY",
        )

    async def gui_action(
        self,
        workspace_id: str,
        action: GUIAction,
        actor: str = "operator",
    ) -> ScreenObservation:
        ws = self._require_workspace(workspace_id)
        self._record_audit(
            session_id=actor,
            workspace_id=workspace_id,
            tenant_id=ws.tenant_id,
            actor=actor,
            action=f"GUI_{action.action.value}",
            application=action.app_name,
            resource=f"x={action.x}, y={action.y}, text={action.text}",
            result="DENIED",
        )
        raise RuntimeError("GUI actions require a provider with a real desktop backend")

    # -------------------------------------------------------------
    # 3. Terminal & Processes
    # -------------------------------------------------------------
    async def terminal(
        self,
        workspace_id: str,
        command: str,
        timeout: int = 60,
        actor: str = "operator",
    ) -> ExecResult:
        ws = self._require_workspace(workspace_id)
        res = await self.compute.execute(workspace_id, command, timeout=timeout)

        self._record_audit(
            session_id=actor,
            workspace_id=workspace_id,
            tenant_id=ws.tenant_id,
            actor=actor,
            action="EXECUTE_TERMINAL",
            resource=command[:100],
            result="SUCCESS" if res.exit_code == 0 else f"EXIT_{res.exit_code}",
        )
        return res

    async def process_list(self, workspace_id: str) -> list[ProcessInfo]:
        self._require_workspace(workspace_id)
        res = await self.compute.execute(workspace_id, "ps -eo pid=,comm=,pcpu=,rss= --no-headers")
        if res.exit_code != 0:
            return []
        processes: list[ProcessInfo] = []
        for line in res.stdout.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            try:
                processes.append(ProcessInfo(
                    pid=int(parts[0]),
                    name=parts[1],
                    cpu_pct=float(parts[2]),
                    memory_mb=float(parts[3]) / 1024.0,
                ))
            except ValueError:
                continue
        return processes

    # -------------------------------------------------------------
    # 4. Filesystem
    # -------------------------------------------------------------
    async def read_file(self, workspace_id: str, path: str) -> str:
        self._require_workspace(workspace_id)
        data = await self.compute.read_file(workspace_id, path)
        return data.decode("utf-8", errors="replace")

    async def write_file(
        self,
        workspace_id: str,
        path: str,
        content: str,
        actor: str = "operator",
    ) -> bool:
        ws = self._require_workspace(workspace_id)
        ok = await self.compute.write_file(workspace_id, path, content)

        self._record_audit(
            session_id=actor,
            workspace_id=workspace_id,
            tenant_id=ws.tenant_id,
            actor=actor,
            action="WRITE_FILE",
            resource=path,
            result="SUCCESS",
        )
        return ok

    async def list_files(self, workspace_id: str, path: str = ".") -> list[FileEntry]:
        self._require_workspace(workspace_id)
        # Filesystem truth comes from the sandbox provider, never an in-memory VFS.
        result = await self.compute.execute(
            workspace_id,
            f"find -- '{path}' -maxdepth 1 -mindepth 1 -printf '%y|%s|%p\\n'",
        )
        entries: list[FileEntry] = []
        if result.exit_code != 0:
            return entries
        for line in result.stdout.splitlines():
            kind, size, item_path = line.split("|", 2)
            entries.append(FileEntry(
                name=item_path.rstrip("/").split("/")[-1],
                path=item_path,
                is_dir=kind == "d",
                size_bytes=int(size) if size.isdigit() else 0,
            ))
        return entries

    # -------------------------------------------------------------
    # 5. Application Management
    # -------------------------------------------------------------
    async def application_list(self, workspace_id: str) -> list[str]:
        self._require_workspace(workspace_id)
        result = await self.compute.execute(
            workspace_id,
            "command -v git curl python3 bash node npm chromium code-server nmap nuclei ffuf 2>/dev/null",
        )
        if result.exit_code != 0:
            return []
        return sorted({line.rsplit("/", 1)[-1] for line in result.stdout.splitlines() if line.strip()})

    async def launch_application(self, workspace_id: str, app_name: str, actor: str = "operator") -> bool:
        ws = self._require_workspace(workspace_id)
        result = await self.compute.execute(workspace_id, f"DISPLAY=:99 {app_name} >/tmp/sonic-app.log 2>&1 &")
        self._record_audit(
            session_id=actor,
            workspace_id=workspace_id,
            tenant_id=ws.tenant_id,
            actor=actor,
            action="LAUNCH_APP",
            application=app_name,
            resource=app_name,
            result="SUCCESS",
        )
        return result.exit_code == 0

    async def close_application(self, workspace_id: str, app_name: str, actor: str = "operator") -> bool:
        ws = self._require_workspace(workspace_id)
        result = await self.compute.execute(workspace_id, f"pkill -f -- '{app_name}'")
        self._record_audit(
            session_id=actor,
            workspace_id=workspace_id,
            tenant_id=ws.tenant_id,
            actor=actor,
            action="CLOSE_APP",
            application=app_name,
            resource=app_name,
            result="SUCCESS",
        )
        return result.exit_code == 0

    async def install_application(
        self,
        workspace_id: str,
        package_name: str,
        actor: str = "operator",
    ) -> tuple[bool, str]:
        ws = self._require_workspace(workspace_id)
        allowed, reason = self.app_policy.is_package_allowed(package_name)
        if not allowed:
            self._record_audit(
                session_id=actor,
                workspace_id=workspace_id,
                tenant_id=ws.tenant_id,
                actor=actor,
                action="INSTALL_APP_BLOCKED",
                application=package_name,
                resource=package_name,
                result="BLOCKED",
                risk_level=ComputerRiskLevel.HIGH,
            )
            return False, reason

        cmd = f"apt-get update -qq && apt-get install -y -qq {package_name} || pip install {package_name}"
        res = await self.compute.execute(workspace_id, cmd)
        success = res.exit_code == 0

        if success:
            self._installed_apps[workspace_id].add(package_name)

        self._record_audit(
            session_id=actor,
            workspace_id=workspace_id,
            tenant_id=ws.tenant_id,
            actor=actor,
            action="INSTALL_APP",
            application=package_name,
            resource=package_name,
            result="SUCCESS" if success else "FAILED",
        )
        return success, "Package installed successfully" if success else res.stderr

    async def uninstall_application(
        self,
        workspace_id: str,
        package_name: str,
        actor: str = "operator",
    ) -> bool:
        ws = self._require_workspace(workspace_id)
        result = await self.compute.execute(workspace_id, f"apt-get remove -y -- '{package_name}'")

        self._record_audit(
            session_id=actor,
            workspace_id=workspace_id,
            tenant_id=ws.tenant_id,
            actor=actor,
            action="UNINSTALL_APP",
            application=package_name,
            resource=package_name,
            result="SUCCESS" if result.exit_code == 0 else f"EXIT_{result.exit_code}",
        )
        return result.exit_code == 0

    # -------------------------------------------------------------
    # 6. Services & Snapshots
    # -------------------------------------------------------------
    async def service_action(
        self,
        workspace_id: str,
        service_name: str,
        action: str,  # "start", "stop", "restart", "logs"
        actor: str = "operator",
    ) -> ServiceInfo:
        ws = self._require_workspace(workspace_id)
        result = await self.compute.execute(workspace_id, f"service '{service_name}' '{action}'")
        status_value = "RUNNING" if result.exit_code == 0 and action in {"start", "restart"} else action.upper()
        svc = ServiceInfo(
            name=service_name,
            status=status_value,
            logs=(result.stdout + result.stderr).splitlines(),
        )
        self._services.setdefault(workspace_id, {})[service_name] = svc

        self._record_audit(
            session_id=actor,
            workspace_id=workspace_id,
            tenant_id=ws.tenant_id,
            actor=actor,
            action=f"SERVICE_{action.upper()}",
            resource=service_name,
            result="SUCCESS" if result.exit_code == 0 else f"EXIT_{result.exit_code}",
        )
        return svc

    async def snapshot_workspace(self, workspace_id: str, name: str) -> str:
        ws = self._require_workspace(workspace_id)
        snapshot_id = _new_id("snap")
        self._snapshots[snapshot_id] = {
            "snapshot_id": snapshot_id,
            "workspace_id": workspace_id,
            "name": name,
            "tenant_id": ws.tenant_id,
            "installed_apps": list(self._installed_apps.get(workspace_id, set())),
            "created_at": _now(),
        }
        self._record_audit(
            session_id="system",
            workspace_id=workspace_id,
            tenant_id=ws.tenant_id,
            actor="ComputerProvider",
            action="SNAPSHOT_WORKSPACE",
            resource=snapshot_id,
            result="SUCCESS",
        )
        return snapshot_id

    async def restore_snapshot(self, snapshot_id: str) -> bool:
        snap = self._snapshots.get(snapshot_id)
        if not snap:
            return False
        ws_id = snap["workspace_id"]
        if ws_id in self.workspaces:
            self._installed_apps[ws_id] = set(snap["installed_apps"])
            return True
        return False

    # -------------------------------------------------------------
    # 7. Git Operations
    # -------------------------------------------------------------
    async def git_action(self, workspace_id: str, action: str, **kwargs: Any) -> Any:
        ws = self._require_workspace(workspace_id)
        actor = kwargs.get("actor", "operator")

        if action == "status":
            res = await self.compute.execute(workspace_id, "git status --porcelain || echo '## main'")
            lines = res.stdout.strip().splitlines()
            modified = [l[3:] for l in lines if l.startswith(" M ")]
            untracked = [l[3:] for l in lines if l.startswith("?? ")]
            return GitStatusInfo(
                branch="main",
                is_clean=len(modified) == 0 and len(untracked) == 0,
                modified_files=modified,
                untracked_files=untracked,
            )
        elif action == "commit":
            msg = kwargs.get("message", "chore: automated computer commit")
            res = await self.compute.execute(workspace_id, f"git add -A && git commit -m '{msg}' || true")
            ok = res.exit_code == 0 or res.exit_code == 126
            self._record_audit(
                session_id=actor,
                workspace_id=workspace_id,
                tenant_id=ws.tenant_id,
                actor=actor,
                action="GIT_COMMIT",
                resource=msg,
                result="SUCCESS" if ok else "FAILED",
            )
            return ok
        elif action == "branch":
            branch_name = kwargs.get("branch_name", "feat-candidate")
            res = await self.compute.execute(workspace_id, f"git checkout -b '{branch_name}' || true")
            return res.exit_code == 0 or res.exit_code == 126
        elif action == "diff":
            res = await self.compute.execute(workspace_id, "git diff || true")
            return res.stdout or ""
        return False

    # -------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------
    def _require_workspace(self, workspace_id: str) -> ComputerWorkspace:
        ws = self.workspaces.get(workspace_id)
        if not ws:
            raise KeyError(f"Computer workspace '{workspace_id}' not found.")
        return ws

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
