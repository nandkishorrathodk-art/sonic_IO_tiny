"""
SONIC — Capability Router (Dual Execution Architecture)
========================================================
Implements the clean architectural separation between:
    1. THE COMPUTER WORKSTATION (Application Environment):
       Where APPLICATIONS run: web browsers, GUI tools, target software, desktop windows.
       Routed to `ExecutionSubstrate.COMPUTER` (Daytona / Docker Workstation).
    2. SONIC OPERATOR TOOLKIT (External Headless Execution):
       Where COMMANDS and SECURITY SCANS run externally against targets without polluting
       or cluttering the computer desktop.
       Routed to `ExecutionSubstrate.HEADLESS` (Fast, container-free terminal commands, file I/O,
       security scanning, direct HTTP probing).

Also provides automatic fallback from unavailable or failing container providers
(e.g., Docker daemon down, missing Daytona API key, exit code 125) to HeadlessComputeProvider.
"""

from __future__ import annotations

import shutil
import subprocess
from enum import StrEnum
from typing import Any

from sonic.computer.headless import HeadlessComputeProvider
from sonic.computer_use.models import ComputerActionType
from sonic.logger import get_logger
from sonic.sandbox.provider import ComputeProvider, ExecResult

logger = get_logger(__name__)


class ExecutionSubstrate(StrEnum):
    HEADLESS = "HEADLESS"
    COMPUTER = "COMPUTER"


class CapabilityRouter:
    """
    Substrate router and provider fallback resolver for SONIC A-SEA execution plane.

    Enforces the architectural boundary:
      - Workstation Application Plane: Interactive desktop/browser/app actions -> COMPUTER
      - Operator Toolkit Plane: Headless CLI commands, scanners, and scripts -> HEADLESS
    """

    def __init__(self, headless_provider: HeadlessComputeProvider | None = None):
        self._headless_provider = headless_provider

    @staticmethod
    def _safe_headless() -> HeadlessComputeProvider:
        """Headless fallback must ALWAYS be host-execution-DISABLED (fail-closed).

        If no sandbox provider is available, the agent fails closed (exit 126)
        instead of silently running directly on the host OS machine.”
        """
        return HeadlessComputeProvider()

    @property
    def headless_provider(self) -> HeadlessComputeProvider:
        if self._headless_provider is None:
            self._headless_provider = self._safe_headless()
        return self._headless_provider

    # -------------------------------------------------------------
    # 1. Action Routing
    # -------------------------------------------------------------
    @classmethod
    def route_action(
        cls,
        action_type: ComputerActionType | str,
        payload: dict[str, Any] | None = None,
    ) -> ExecutionSubstrate:
        """
        Classifies an action into either COMPUTER (Workstation) or HEADLESS (Operator Toolkit) substrate.

        Architectural Separation:
            1. THE COMPUTER WORKSTATION (Target & Application Environment):
               Where applications run (web browsers, GUI software, target applications).
               - Application and UI interactions (GUI_*, APP_*, interactive BROWSER_*)
                 are cleanly dispatched to ExecutionSubstrate.COMPUTER.
            2. SONIC OPERATOR TOOLKIT (External Headless Execution):
               Where commands and security scans run externally against targets, NOT tied to
               or cluttering the computer desktop.
               - External shell commands and scanning tools (SECURITY_TOOL, TERMINAL_EXEC, FILE_*)
                 are cleanly dispatched to ExecutionSubstrate.HEADLESS.

        Routing Rules:
            - Application & UI actions:
                * GUI_* (clicks, typing, shortcuts, mouse movements) -> COMPUTER
                * APP_* (launch, focus, close, install) -> COMPUTER
                * BROWSER_* (click, type, screenshot, wait, download) -> COMPUTER
            - Operator Toolkit actions:
                * SECURITY_TOOL (nmap, nuclei, ffuf, http_client) -> HEADLESS
                * TERMINAL_EXEC (shell commands) -> HEADLESS
                * FILE_* (file read/write) -> HEADLESS
                * TOOL_AUTHOR, TOOL_RUN, METHOD_INVENT, GIT_* -> HEADLESS
            - BROWSER_NAVIGATE:
                * HEADLESS if static/fetch-only (cURL/HTTP probe)
                * COMPUTER if interactive/GUI requested (rendering DOM/JS for user interaction)
        """
        val = action_type.value if hasattr(action_type, "value") else str(action_type)
        payload = payload or {}

        # Graphical desktop actions
        if val.startswith("GUI_"):
            return ExecutionSubstrate.COMPUTER

        # Application window / desktop lifecycle actions
        if val.startswith("APP_"):
            return ExecutionSubstrate.COMPUTER

        # Interactive browser interactions requiring a real DOM / display
        if val in ("BROWSER_CLICK", "BROWSER_TYPE", "BROWSER_SCREENSHOT", "BROWSER_WAIT", "BROWSER_DOWNLOAD"):
            return ExecutionSubstrate.COMPUTER

        # Navigation: headless fetch suffices unless full GUI/interactive is explicitly requested
        if val == "BROWSER_NAVIGATE":
            if payload.get("interactive") or payload.get("requires_gui") or payload.get("render_js") or payload.get("browser"):
                return ExecutionSubstrate.COMPUTER
            return ExecutionSubstrate.HEADLESS

        # Terminal commands, file operations, security scanning, tool synthesis, etc.
        if (
            val == "TERMINAL_EXEC"
            or val.startswith("FILE_")
            or val == "SECURITY_TOOL"
            or val in ("TOOL_AUTHOR", "TOOL_RUN", "METHOD_INVENT", "GIT_BRANCH", "GIT_COMMIT", "SERVICE_ACTION")
        ):
            return ExecutionSubstrate.HEADLESS

        # Default fallback
        return ExecutionSubstrate.HEADLESS

    # -------------------------------------------------------------
    # 2. Provider Availability Checks
    # -------------------------------------------------------------
    @staticmethod
    def is_docker_available(provider: Any = None) -> bool:
        """Check if Docker CLI and daemon are operational."""
        if not shutil.which("docker"):
            return False
        if provider is not None and hasattr(provider, "_daemon_checked") and provider._daemon_checked is False:
            return False
        try:
            probe = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=1.5,
            )
            return probe.returncode == 0
        except Exception:
            return False

    @staticmethod
    def is_daytona_available(provider: Any = None) -> bool:
        """Check if Daytona client is configured and initialized."""
        if provider is None:
            return False
        api_key = getattr(provider, "api_key", None)
        if not api_key:
            return False
        if hasattr(provider, "_get_client"):
            try:
                client = provider._get_client()
                return client is not None
            except Exception:
                return False
        return getattr(provider, "_client", None) is not None

    @classmethod
    def is_provider_available(cls, provider: Any) -> bool:
        """Determine if a preferred provider is operational."""
        if provider is None:
            return False
        if isinstance(provider, HeadlessComputeProvider):
            return True

        p_name = provider.__class__.__name__.lower()
        if "docker" in p_name:
            return cls.is_docker_available(provider)
        if "daytona" in p_name:
            return cls.is_daytona_available(provider)

        return True

    # -------------------------------------------------------------
    # 3. Provider Resolution & Fallback
    # -------------------------------------------------------------
    @classmethod
    def resolve_provider(
        cls,
        preferred_provider: Any = None,
        task_type: str = "",
    ) -> Any:
        """
        Resolve the execution provider. If the preferred provider (Docker/Daytona)
        is unavailable or misconfigured, automatically falls back to HeadlessComputeProvider.
        """
        # Explicit headless task requests
        if task_type and task_type.upper() in {
            "HEADLESS",
            "TERMINAL_ONLY",
            "PORT_SCAN",
            "HTTP_PROBE",
            "RECON",
        }:
            return CapabilityRouter._safe_headless()

        if preferred_provider is None:
            return CapabilityRouter._safe_headless()

        if isinstance(preferred_provider, HeadlessComputeProvider):
            return preferred_provider

        # Check provider availability
        if not cls.is_provider_available(preferred_provider):
            logger.warning(
                "provider_unavailable_falling_back_to_headless",
                preferred=preferred_provider.__class__.__name__,
                task_type=task_type,
            )
            return CapabilityRouter._safe_headless()

        return preferred_provider

    @staticmethod
    def should_fallback_on_exit(exit_code: int) -> bool:
        """Exit code 125 indicates container runtime failure (Docker/container down)."""
        return exit_code == 125

    async def execute_with_fallback(
        self,
        provider: Any,
        workspace_id: str,
        command: str | list[str],
        timeout: int = 60,
        actor: str = "operator",
    ) -> ExecResult:
        """
        Execute command on resolved provider. If the container provider returns exit code 125
        (container not running / docker unreachable), automatically fallback to HeadlessComputeProvider.
        """
        resolved = self.resolve_provider(provider)

        # Primary execution attempt
        if hasattr(resolved, "terminal"):
            res = await resolved.terminal(workspace_id, command, timeout=timeout, actor=actor)
        elif hasattr(resolved, "execute"):
            res = await resolved.execute(workspace_id, command, timeout=timeout)
        else:
            raise TypeError(f"Provider {resolved} does not support command execution")

        # Container exit 125 fallback
        if self.should_fallback_on_exit(res.exit_code) and not isinstance(resolved, HeadlessComputeProvider):
            logger.warning(
                "provider_returned_exit_125_falling_back_to_headless",
                failing_provider=resolved.__class__.__name__,
                command=str(command)[:60],
            )
            fallback = self.headless_provider
            if hasattr(fallback, "terminal"):
                return await fallback.terminal(workspace_id, command, timeout=timeout, actor=actor)
            return await fallback.execute(workspace_id, command, timeout=timeout)

        return res
