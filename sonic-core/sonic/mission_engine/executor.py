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
from sonic.tools.base import ToolRequest
from sonic.tools.registry import SecurityToolRegistry


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

    _READONLY_COMMANDS = ("pwd", "git status", "git log", "find ", "ls", "whoami", "uname")

    def __init__(self, computer: DaytonaComputerProvider, security_tools: SecurityToolRegistry | None = None):
        self.computer = computer
        # Optional registry of real security scanners (nmap/nuclei/ffuf/http).
        # When wired, `target_security_scan` dispatches a real in-sandbox scan;
        # when None, it BLOCKS with a clear "not configured" status (never the
        # generic "not implemented" — so callers know scanners exist but aren't
        # provisioned for this executor).
        self.security_tools = security_tools

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

            if action.tool == "target_security_scan":
                tool_name = str(action.input.get("tool", "")).strip()
                target = str(action.input.get("target", "")).strip()
                if not tool_name or not target:
                    return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="BLOCKED", workspace_id=workspace_id, output="Security scan requires a 'tool' (nmap/nuclei/ffuf/http_client) and a 'target'")
                if self.security_tools is None:
                    return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="BLOCKED", workspace_id=workspace_id, output="Security tool registry is not configured for this executor — scanners exist but are not provisioned")
                scanner = self.security_tools.get(tool_name)
                if scanner is None:
                    return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="BLOCKED", workspace_id=workspace_id, output=f"Scanner '{tool_name}' is not registered (available: {self.security_tools.names()})")
                verdict = get_scope_checker().check_action(f"{tool_name} {target}", RiskLevel.L0_SAFE)
                if verdict != SafetyVerdict.ALLOWED:
                    return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="BLOCKED", workspace_id=workspace_id, output=f"Safety policy verdict: {verdict.value}")
                req = ToolRequest(
                    tenant_id=str(action.input.get("tenant_id", "mission")),
                    engagement_id=str(action.input.get("engagement_id", action.action_id)),
                    workspace_id=workspace_id,
                    agent_id=actor,
                    tool_name=tool_name,
                    target=target,
                    options=dict(action.input.get("options", {})),
                    timeout_seconds=int(action.input.get("timeout_seconds", 120)),
                )
                result = await scanner.execute(req)
                return ActionExecutionResult(
                    action_id=action.action_id,
                    tool=action.tool,
                    status="SUCCESS" if result.exit_code == 0 else "FAILED",
                    exit_code=result.exit_code,
                    output=(result.raw_stdout + ("\n" + result.raw_stderr if result.raw_stderr else ""))[:8000],
                    workspace_id=workspace_id,
                    evidence={
                        "tool": tool_name, "target": target, "status": result.status.value,
                        "parsed_findings": result.parsed_data[:50],
                        "error": result.error_message,
                    },
                )

            return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="BLOCKED", workspace_id=workspace_id, output="Tool adapter is not implemented")
        except Exception as exc:
            return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="FAILED", workspace_id=workspace_id, output=str(exc))
