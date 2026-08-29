"""Execute planner actions against the correct real computer plane."""

from __future__ import annotations

import shlex
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from sonic.computer.daytona_computer import DaytonaComputerProvider
from sonic.mission_engine.planner import PlannedAction
from sonic.mission_engine.tool_registry import MissionToolRegistry, ToolPlane, ToolRisk
from sonic.safety.scope import RiskLevel, SafetyVerdict, get_scope_checker


class ActionExecutionResult(BaseModel):
    action_id: str
    tool: str
    status: str
    exit_code: int | None = None
    output: str = ""
    workspace_id: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class MissionToolExecutor:
    """Fail-closed executor for the typed mission tool registry."""

    _READONLY_COMMANDS = ("pwd", "git status", "find ", "ls", "whoami", "uname")

    def __init__(self, computer: DaytonaComputerProvider):
        self.computer = computer

    async def execute(
        self,
        action: PlannedAction,
        target_workspace_id: str,
        desktop_workspace_id: str = "",
        actor: str = "agent",
        approved: bool = False,
    ) -> ActionExecutionResult:
        spec = MissionToolRegistry.get(action.tool)
        workspace_id = target_workspace_id if spec.plane == ToolPlane.TARGET_SANDBOX else desktop_workspace_id
        if not workspace_id:
            return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="BLOCKED", workspace_id="", output="Required workspace is not provisioned")

        if spec.risk == ToolRisk.APPROVAL_REQUIRED and not approved:
            return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="AWAITING_APPROVAL", workspace_id=workspace_id, output="Operator approval is required before this action can run")

        try:
            if action.tool in {"target_shell_readonly", "target_shell_approved", "desktop_terminal"}:
                command = str(action.input.get("command", "")).strip()
                if not command:
                    return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="BLOCKED", workspace_id=workspace_id, output="Command is empty")
                if action.tool == "target_shell_readonly" and not command.startswith(self._READONLY_COMMANDS):
                    return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="BLOCKED", workspace_id=workspace_id, output="Command is not in the read-only allowlist")
                verdict = get_scope_checker().check_action(command, RiskLevel.L0_SAFE)
                if verdict != SafetyVerdict.ALLOWED:
                    return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="BLOCKED", workspace_id=workspace_id, output=f"Safety policy verdict: {verdict.value}")
                result = await self.computer.terminal(workspace_id, command, timeout=120, actor=actor)
                output = (result.stdout + ("\n" + result.stderr if result.stderr else "")).strip()
                return ActionExecutionResult(
                    action_id=action.action_id,
                    tool=action.tool,
                    status="SUCCESS" if result.exit_code == 0 else "FAILED",
                    exit_code=result.exit_code,
                    output=output[:8000],
                    workspace_id=workspace_id,
                    evidence={"command": command, "stdout": result.stdout[:8000], "stderr": result.stderr[:8000]},
                )

            if action.tool == "target_file_read":
                path = str(action.input.get("path", ""))
                if not path or ".." in path:
                    return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="BLOCKED", workspace_id=workspace_id, output="Invalid target file path")
                content = await self.computer.read_file(workspace_id, path)
                return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="SUCCESS", output=content[:12000], workspace_id=workspace_id, evidence={"path": path, "bytes": len(content)})

            if action.tool == "desktop_screenshot":
                observation = await self.computer.screenshot(workspace_id)
                return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="SUCCESS", output="Real desktop observation captured", workspace_id=workspace_id, evidence=observation.model_dump())

            if action.tool == "desktop_browser_open":
                url = str(action.input.get("url", "")).strip()
                allowed_target = str(action.input.get("allowed_target", "")).strip().lower()
                host = (urlparse(url).hostname or "").lower()
                if urlparse(url).scheme not in {"http", "https"} or not host or not allowed_target:
                    return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="BLOCKED", workspace_id=workspace_id, output="Browser URL and explicit allowed target are required")
                if host != allowed_target and not host.endswith("." + allowed_target):
                    return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="BLOCKED", workspace_id=workspace_id, output="Browser URL is outside the authorized target")
                command = f"DISPLAY=:99 chromium --new-window {shlex.quote(url)} >/tmp/sonic-browser.log 2>&1 &"
                result = await self.computer.terminal(workspace_id, command, timeout=30, actor=actor)
                output = (result.stdout + ("\n" + result.stderr if result.stderr else "")).strip()
                return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="SUCCESS" if result.exit_code == 0 else "FAILED", exit_code=result.exit_code, output=output[:4000], workspace_id=workspace_id, evidence={"url": url, "allowed_target": allowed_target})

            return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="BLOCKED", workspace_id=workspace_id, output="Tool adapter is not implemented")
        except Exception as exc:
            return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="FAILED", workspace_id=workspace_id, output=str(exc))
