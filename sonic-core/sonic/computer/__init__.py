"""
SONIC-REDA — Autonomous Computer & Engineering Workspace (Phase 13)
=====================================================================
Unified execution body for Desktop GUI, Terminal, Filesystem,
code-server IDE, Browser, Applications, Git, and Services.
"""

from sonic.computer.benchmark import AutonomousEngineerBenchmark, ComputerBenchmarkMetrics
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
)
from sonic.computer.headless import HeadlessComputeProvider
from sonic.computer.provider import ComputerProvider, UnifiedComputerProvider

__all__ = [
    "ApplicationPolicy",
    "AutonomousEngineerBenchmark",
    "ComputerAuditEvent",
    "ComputerBenchmarkMetrics",
    "ComputerProfile",
    "ComputerProvider",
    "ComputerRiskLevel",
    "ComputerSession",
    "ComputerSessionMode",
    "ComputerState",
    "ComputerWorkspace",
    "ComputerWorkspaceStatus",
    "ComputerWorkspaceType",
    "FileEntry",
    "GitStatusInfo",
    "GUIAction",
    "GUIActionType",
    "HeadlessComputeProvider",
    "ProcessInfo",
    "ScreenObservation",
    "ServiceInfo",
    "UnifiedComputerProvider",
]

