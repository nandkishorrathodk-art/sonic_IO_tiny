"""
SONIC-REDA — Autonomous Computer & Engineering Workspace Models (Phase 13)
=============================================================================
Data models for persistent computer workspaces, sessions, GUI actions,
screen observations, application policies, processes, files, git status,
services, and audit events.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str = "comp") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ============================================
# Enums
# ============================================

class ComputerWorkspaceStatus(StrEnum):
    CREATING = "CREATING"
    STARTING = "STARTING"
    READY = "READY"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    DEGRADED = "DEGRADED"
    DESTROYING = "DESTROYING"
    DESTROYED = "DESTROYED"
    FAILED = "FAILED"


class ComputerWorkspaceType(StrEnum):
    MISSION_COMPUTER = "MISSION_COMPUTER"  # Persistent long-term environment
    RESEARCH_LAB = "RESEARCH_LAB"          # Disposable single-task sandbox
    TARGET_SANDBOX = "TARGET_SANDBOX"      # Disposable authorized target environment


class ComputerProfile(StrEnum):
    DEBIAN_ENGINEERING = "DEBIAN_ENGINEERING"
    KALI_SECURITY = "KALI_SECURITY"
    GENERIC_LINUX = "GENERIC_LINUX"


class ComputerSessionMode(StrEnum):
    AUTONOMOUS = "AUTONOMOUS"
    ASSISTED = "ASSISTED"
    MANUAL = "MANUAL"


class GUIActionType(StrEnum):
    CLICK = "CLICK"
    DOUBLE_CLICK = "DOUBLE_CLICK"
    RIGHT_CLICK = "RIGHT_CLICK"
    TYPE = "TYPE"
    KEYPRESS = "KEYPRESS"
    SCROLL = "SCROLL"
    MOVE = "MOVE"
    DRAG = "DRAG"
    SELECT_WINDOW = "SELECT_WINDOW"
    OPEN_APP = "OPEN_APP"
    CLOSE_APP = "CLOSE_APP"


class ComputerRiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ============================================
# Models
# ============================================

class ComputerWorkspace(BaseModel):
    """A persistent or disposable engineering computer sandbox workspace."""
    id: str = Field(default_factory=lambda: _new_id("ws"))
    tenant_id: str
    engagement_id: str
    workspace_type: ComputerWorkspaceType = ComputerWorkspaceType.MISSION_COMPUTER
    profile: ComputerProfile = ComputerProfile.KALI_SECURITY
    provider_type: str = "DockerProvider"  # DockerProvider, DaytonaProvider, LocalDevProvider
    image: str = "sonic-kali-linux:v1.3.0"
    status: ComputerWorkspaceStatus = ComputerWorkspaceStatus.READY
    workspace_path: str = "/home/sonic/workspace"
    capabilities: list[str] = Field(default_factory=lambda: [
        "desktop", "terminal", "filesystem", "ide", "browser", "git", "services", "package_manager"
    ])
    resource_profile: dict[str, Any] = Field(default_factory=lambda: {
        "cpu_cores": 4, "memory_gb": 8, "disk_gb": 32
    })
    created_at: str = Field(default_factory=_now)
    last_active_at: str = Field(default_factory=_now)


class ComputerSession(BaseModel):
    """An active user or agent interaction session attached to a ComputerWorkspace."""
    id: str = Field(default_factory=lambda: _new_id("sess"))
    workspace_id: str
    user_id: str
    tenant_id: str
    mode: ComputerSessionMode = ComputerSessionMode.AUTONOMOUS
    permissions: list[str] = Field(default_factory=lambda: ["read", "write", "execute", "gui"])
    started_at: str = Field(default_factory=_now)
    last_activity: str = Field(default_factory=_now)


class GUIAction(BaseModel):
    """A structured graphical desktop action."""
    action: GUIActionType
    x: int | None = None
    y: int | None = None
    # Destination coordinates for DRAG (source is x,y). Lets the agent move a
    # file onto a folder, slide a wizard control, or rearrange windows — like a
    # human press-move-release gesture.
    x2: int | None = None
    y2: int | None = None
    text: str | None = None
    key: str | None = None
    window_id: str | None = None
    app_name: str | None = None
    scroll_delta: int = 0


class ScreenObservation(BaseModel):
    """Visual and state perception of the computer desktop screen."""
    screenshot_base64: str = ""
    width: int = 1920
    height: int = 1080
    active_window: str = "Desktop"
    visible_text: str = ""
    detected_controls: list[str] = Field(default_factory=list)
    desktop_state: str = "INTERACTIVE"
    timestamp: str = Field(default_factory=_now)


class ComputerState(BaseModel):
    """Complete persistent state representation of the SONIC Computer."""
    workspace_id: str
    tenant_id: str
    status: ComputerWorkspaceStatus = ComputerWorkspaceStatus.READY
    active_application: str = "Desktop"
    open_applications: list[str] = Field(default_factory=lambda: ["Desktop", "Terminal"])
    active_window: str = "Terminal"
    working_directory: str = "/home/sonic/workspace"
    running_processes: list[str] = Field(default_factory=list)
    installed_applications: list[str] = Field(default_factory=list)
    current_project: str = "sonic-repo"
    git_branch: str = "main"
    resource_usage: dict[str, float] = Field(default_factory=lambda: {"cpu_pct": 12.5, "memory_mb": 1024.0})
    last_observation: ScreenObservation | None = None


class ApplicationPolicy(BaseModel):
    """Security rules governing application and package installations."""
    allowed_packages: list[str] = Field(default_factory=lambda: [
        "nmap", "nuclei", "ffuf", "git", "curl", "wget", "jq", "python3-pip",
        "playwright", "chromium", "nodejs", "npm", "zsh", "tmux", "vim", "code-server",
        "wireshark", "gdb", "sqlmap", "nikto", "zap"
    ])
    forbidden_packages: list[str] = Field(default_factory=lambda: [
        "wireshark-root", "tor-relay", "cryptominer", "kernel-mod", "ddos-bot",
        "burpsuite", "burp"
    ])
    max_install_size_mb: int = 2048
    require_approval: bool = False

    def is_package_allowed(self, package_name: str) -> tuple[bool, str]:
        pkg = package_name.lower().strip()
        if any(f in pkg for f in self.forbidden_packages):
            return False, f"Package '{pkg}' is strictly prohibited by security policy."
        if pkg in self.allowed_packages:
            return True, f"Package '{pkg}' is on the pre-approved allowlist."
        return True, f"Package '{pkg}' permitted under developer engineering policy."


class ComputerAuditEvent(BaseModel):
    """Immutable audit record of a computer operation."""
    id: str = Field(default_factory=lambda: _new_id("audit"))
    session_id: str
    workspace_id: str
    tenant_id: str
    actor: str
    action: str  # "LAUNCH_APP", "WRITE_FILE", "EXECUTE_COMMAND", "GIT_COMMIT", etc.
    application: str | None = None
    resource: str
    result: str = "SUCCESS"
    risk_level: ComputerRiskLevel = ComputerRiskLevel.LOW
    timestamp: str = Field(default_factory=_now)


class ProcessInfo(BaseModel):
    """Running process metadata."""
    pid: int
    name: str
    cpu_pct: float = 0.0
    memory_mb: float = 0.0
    status: str = "RUNNING"


class FileEntry(BaseModel):
    """Filesystem directory entry."""
    name: str
    path: str
    is_dir: bool = False
    size_bytes: int = 0
    modified_at: str = Field(default_factory=_now)


class GitStatusInfo(BaseModel):
    """Git repository status inside the computer workspace."""
    branch: str = "main"
    is_clean: bool = True
    modified_files: list[str] = Field(default_factory=list)
    untracked_files: list[str] = Field(default_factory=list)
    ahead: int = 0
    behind: int = 0


class ServiceInfo(BaseModel):
    """Managed service running inside the computer."""
    name: str
    status: str = "RUNNING"
    port: int | None = None
    logs: list[str] = Field(default_factory=list)
