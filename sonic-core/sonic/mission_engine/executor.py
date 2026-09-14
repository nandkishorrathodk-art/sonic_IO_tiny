"""Execute planner actions against the correct real computer plane."""

from __future__ import annotations

import ipaddress
import shlex
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

import uuid
from dataclasses import dataclass, field

from sonic.computer.daytona_computer import DaytonaComputerProvider
from sonic.mission_engine.planner import PlannedAction
from sonic.mission_engine.tool_registry import MissionToolRegistry, ToolPlane, ToolRisk
from sonic.safety.scope import RiskLevel, SafetyVerdict, get_scope_checker
from sonic.safety.runtime_stop import get_runtime_stop_state


@dataclass
class ToolRequest:
    """Parameters passed to initiate tool execution."""
    tenant_id: str
    engagement_id: str
    workspace_id: str
    agent_id: str
    tool_name: str
    target: str
    options: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 120
    execution_id: str = field(default_factory=lambda: f"exec-{uuid.uuid4().hex[:12]}")


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

    _READONLY_COMMANDS = (
        "pwd",
        "git status",
        "git log",
        "find ",
        "ls",
        "whoami",
        "uname",
        "grep",
        "cat ",
        "head ",
        "tail ",
        "echo ",
    )

    def __init__(
        self,
        computer: DaytonaComputerProvider,
        security_tools: Any | None = None,
        scoped_target: str | None = None,
        tenant_id: str = "default",
    ):
        self.computer = computer
        self.tenant_id = tenant_id
        # Optional registry of real security scanners (nmap/nuclei/ffuf/http).
        # When wired, `target_security_scan` dispatches a real in-sandbox scan;
        # when None, it BLOCKS with a clear "not configured" status (never the
        # generic "not implemented" — so callers know scanners exist but aren't
        # provisioned for this executor).
        self.security_tools = security_tools
        # Optional engagement-scoped target host/URL. When set, every security
        # probe is required to stay within this scope — defending against a
        # mis-generated or tampered probe targeting an out-of-scope asset.
        self.scoped_target = str(scoped_target or "").strip()

    async def execute(
        self,
        action: PlannedAction,
        target_workspace_id: str,
        desktop_workspace_id: str = "",
        actor: str = "agent",
        approved: bool = False,
    ) -> ActionExecutionResult:
        spec = MissionToolRegistry.get(action.tool)
        tenant_id = str(action.input.get("tenant_id") or self.tenant_id or actor)
        stop_state = get_runtime_stop_state()
        if stop_state.is_stopped(tenant_id):
            return ActionExecutionResult(
                action_id=action.action_id,
                tool=action.tool,
                status="BLOCKED",
                workspace_id="",
                output=f"Runtime kill switch asserted: {stop_state.reason(tenant_id)}",
            )
        workspace_id = target_workspace_id if spec.plane == ToolPlane.TARGET_SANDBOX else desktop_workspace_id
        if not workspace_id:
            return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="BLOCKED", workspace_id="", output="Required workspace is not provisioned")

        if spec.risk == ToolRisk.APPROVAL_REQUIRED and not approved:
            return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="AWAITING_APPROVAL", workspace_id=workspace_id, output="Operator approval is required before this action can run")

        if stop_state.is_stopped(tenant_id):
            return ActionExecutionResult(
                action_id=action.action_id,
                tool=action.tool,
                status="BLOCKED",
                workspace_id=workspace_id,
                output=f"Runtime kill switch asserted: {stop_state.reason(tenant_id)}",
            )

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
                if not self._probe_in_scope(target):
                    return ActionExecutionResult(
                        action_id=action.action_id,
                        tool=action.tool,
                        status="BLOCKED",
                        workspace_id=workspace_id,
                        output=f"Security probe target {target!r} is outside the engagement scope {self.scoped_target!r}",
                    )
                if self.security_tools is None:
                    return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="BLOCKED", workspace_id=workspace_id, output="Security tool registry is not configured for this executor — scanners exist but are not provisioned")
                scanner = self.security_tools.get(tool_name) if hasattr(self.security_tools, "get") else None
                if scanner is None:
                    available = self.security_tools.names() if hasattr(self.security_tools, "names") else (list(self.security_tools.keys()) if hasattr(self.security_tools, "keys") else [])
                    return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="BLOCKED", workspace_id=workspace_id, output=f"Scanner '{tool_name}' is not registered (available: {available})")
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
                        "tool": tool_name, "target": target,
                        "status": result.status.value if hasattr(result.status, "value") else str(result.status),
                        "parsed_findings": getattr(result, "parsed_data", [])[:50],
                        "error": getattr(result, "error_message", None),
                    },
                )

            return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="BLOCKED", workspace_id=workspace_id, output="Tool adapter is not implemented")
        except Exception as exc:
            return ActionExecutionResult(action_id=action.action_id, tool=action.tool, status="FAILED", workspace_id=workspace_id, output=str(exc))

    def _probe_in_scope(self, target: str) -> bool:
        """True when the probe target stays within the engaged scoped target.

        When no scoped target was configured for this executor the gate is
        skipped (True) — legacy callers rely on the planner-only construction
        guarantee, which already scopes every probe to the mission target. When
        a scope IS configured (the workstation mission preflight always does),
        the gate is strict and suffix-safe: ``api.target.com`` is inside scope
        ``target.com``, but ``target.com.evil.net`` is not.
        """
        if not self.scoped_target:
            return True

        def host_of(value: str) -> str:
            value = value.strip().strip("/")
            if "://" in value:
                return urlparse(value).hostname or ""
            return value.split("/")[0].split(":")[0].strip()

        probe_host = host_of(target)
        scope_host = host_of(self.scoped_target)
        if not probe_host or not scope_host:
            return False
        probe_host = probe_host.lower()
        scope_host = scope_host.lower()
        try:
            scope_ip = ipaddress.ip_address(scope_host)
            probe_ip = ipaddress.ip_address(probe_host)
            return probe_ip == scope_ip
        except ValueError:
            return probe_host == scope_host or probe_host.endswith(f".{scope_host}")
