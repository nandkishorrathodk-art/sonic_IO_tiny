"""
SONIC-REDA — Compute Provider Abstraction (Compute Plane)
===========================================================
Defines the generic ComputeProvider contract for provisioning,
executing, file handling, snapshotting, and destroying isolated Linux workspaces.

Supports:
    - DockerProvider (Local container runtime)
    - DaytonaProvider (Remote cloud workspace daemon)
    - E2BProvider (Ephemeral cloud MicroVMs)
    - LocalDevProvider (Strictly for offline unit tests with safety lock)

FAIL-CLOSED INVARIANT:
    If a compute provider fails or is unreachable, the system FAILS CLOSED.
    It NEVER falls back to host OS shell execution.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum

from sonic.logger import get_logger

logger = get_logger(__name__)


class WorkspaceState(StrEnum):
    CREATING = "creating"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    DESTROYED = "destroyed"
    ERROR = "error"


class WorkspaceType(StrEnum):
    MISSION_COMPUTER = "mission_computer"  # Persistent long-term environment
    RESEARCH_LAB = "research_lab"          # Disposable single-task sandbox
    TARGET_SANDBOX = "target_sandbox"      # Disposable authorized target environment


@dataclass
class WorkspaceConfig:
    """Configuration for provisioning a compute workspace."""
    workspace_id: str
    tenant_id: str
    workspace_type: WorkspaceType = WorkspaceType.RESEARCH_LAB
    image: str = "debian:12-slim"
    cpu_limit: str = "2.0"
    memory_limit: str = "2048M"
    timeout_seconds: int = 300
    env_vars: dict[str, str] = field(default_factory=dict)
    network_isolated: bool = True


@dataclass
class ExecResult:
    """Result of command execution inside an isolated workspace."""
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float = 0.0
    timed_out: bool = False
    sandbox_id: str = ""


class ComputeProvider(ABC):
    """
    Abstract interface for all SONIC-REDA compute and sandbox backends.
    """

    @abstractmethod
    async def create_workspace(self, config: WorkspaceConfig) -> bool:
        """Provision and initialize an isolated compute workspace."""
        pass

    @abstractmethod
    async def execute(
        self,
        workspace_id: str,
        command: str | list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 120,
    ) -> ExecResult:
        """Execute a command strictly inside the isolated workspace."""
        pass

    @abstractmethod
    async def read_file(self, workspace_id: str, path: str) -> bytes:
        """Read a file from the workspace filesystem."""
        pass

    @abstractmethod
    async def write_file(self, workspace_id: str, path: str, data: bytes | str) -> bool:
        """Write a file to the workspace filesystem."""
        pass

    @abstractmethod
    async def destroy_workspace(self, workspace_id: str) -> bool:
        """Terminate and clean up workspace resources."""
        pass

    @abstractmethod
    async def get_state(self, workspace_id: str) -> WorkspaceState:
        """Check current runtime state of the workspace."""
        pass
