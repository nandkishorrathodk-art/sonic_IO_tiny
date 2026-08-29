"""Typed mission tools and immutable execution-plane metadata.

The registry is deliberately small: a mission can only invoke tools exposed
here, and each tool declares which sandbox plane it may touch. Adding a tool
requires code review; the planner cannot invent arbitrary adapters at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ToolPlane(StrEnum):
    TARGET_SANDBOX = "TARGET_SANDBOX"
    AGENT_DESKTOP = "AGENT_DESKTOP"


class ToolRisk(StrEnum):
    READ_ONLY = "READ_ONLY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    plane: ToolPlane
    risk: ToolRisk
    description: str


class MissionToolRegistry:
    """Allowlisted tools available to the mission executor."""

    _TOOLS = {
        "target_shell_readonly": ToolSpec(
            "target_shell_readonly", ToolPlane.TARGET_SANDBOX, ToolRisk.READ_ONLY,
            "Run an explicitly allowlisted read-only command in the target sandbox.",
        ),
        "target_shell_approved": ToolSpec(
            "target_shell_approved", ToolPlane.TARGET_SANDBOX, ToolRisk.APPROVAL_REQUIRED,
            "Run an operator-approved security command in the target sandbox.",
        ),
        "desktop_terminal": ToolSpec(
            "desktop_terminal", ToolPlane.AGENT_DESKTOP, ToolRisk.READ_ONLY,
            "Run a diagnostic command in the persistent agent desktop.",
        ),
        "desktop_screenshot": ToolSpec(
            "desktop_screenshot", ToolPlane.AGENT_DESKTOP, ToolRisk.READ_ONLY,
            "Capture a real screenshot from the agent desktop.",
        ),
        "desktop_browser_open": ToolSpec(
            "desktop_browser_open", ToolPlane.AGENT_DESKTOP, ToolRisk.APPROVAL_REQUIRED,
            "Open an explicitly scoped URL in the real desktop browser.",
        ),
        "target_file_read": ToolSpec(
            "target_file_read", ToolPlane.TARGET_SANDBOX, ToolRisk.READ_ONLY,
            "Read a file from the target sandbox filesystem.",
        ),
    }

    @classmethod
    def get(cls, name: str) -> ToolSpec:
        try:
            return cls._TOOLS[name]
        except KeyError as exc:
            raise ValueError(f"Mission tool is not allowlisted: {name}") from exc

    @classmethod
    def list_tools(cls) -> list[ToolSpec]:
        return list(cls._TOOLS.values())
