"""
Mission tool executor — security scan dispatch — done-gate tests.

Closes the PLAN.md audit item: MissionToolExecutor returned "Tool adapter is
not implemented" for nmap/nuclei/ffuf (the typed mission plane never dispatched
scanners, even though real adapters existed and were reachable only via the
separate ComputerUseAgent path). Now:

  * `target_security_scan` is a registered APPROVAL_REQUIRED tool.
  * When a SecurityToolRegistry is wired, the executor dispatches a REAL
    in-sandbox scan (via SecurityTool.execute) and surfaces parsed findings.
  * When no registry is wired, it BLOCKS with a clear "not configured" status
    (never the generic "not implemented"), so callers know scanners exist but
    are not provisioned for this executor.
  * Approval is enforced (AWAITING_APPROVAL without operator approval).
  * A scanner not in the registry BLOCKS with the available-tool list.
  * A forbidden-pattern scan target is BLOCKED by the safety policy.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from sonic.mission_engine.executor import MissionToolExecutor
from sonic.mission_engine.planner import PlannedAction
from sonic.mission_engine.tool_registry import ToolRisk
from sonic.sandbox.provider import ExecResult
from sonic.tools.base import SecurityTool, ToolRequest, ToolResult, ToolStatus


class _StubComputer:
    """Minimal computer with .terminal (no Daytona/cloud import → not skipped)."""
    async def terminal(self, workspace_id, command, timeout=120, actor="operator"):
        return ExecResult(command=command, exit_code=0, stdout="", stderr="")


class _FakeScanner(SecurityTool):
    """A real SecurityTool double that runs against a fake provider."""
    def __init__(self, provider: Any, name: str = "nmap", stdout: str = "scan ok"):
        super().__init__(provider)
        self._name = name
        self._stdout = stdout
        self.last_request: ToolRequest | None = None
    @property
    def name(self) -> str: return self._name
    @property
    def version(self) -> str: return "test-1.0"
    def build_command(self, request: ToolRequest) -> str:
        return f"{self._name} {request.target}"
    def parse_output(self, raw_stdout: str, raw_stderr: str) -> list[dict[str, Any]]:
        return [{"finding": "open", "raw": raw_stdout}]
    async def execute(self, request: ToolRequest) -> ToolResult:
        self.last_request = request
        return ToolResult(
            execution_id=request.execution_id,
            tenant_id=request.tenant_id,
            engagement_id=request.engagement_id,
            workspace_id=request.workspace_id,
            agent_id=request.agent_id,
            tool_name=self._name,
            tool_version=self.version,
            status=ToolStatus.COMPLETED,
            start_time=datetime.now(timezone.utc).isoformat(),
            end_time=datetime.now(timezone.utc).isoformat(),
            exit_code=0,
            raw_stdout=self._stdout,
            raw_stderr="",
            parsed_data=self.parse_output(self._stdout, ""),
        )


class _FakeRegistry:
    """Stand-in for SecurityToolRegistry with a name->tool map."""
    def __init__(self, tools: dict[str, SecurityTool]):
        self._tools = tools
    def get(self, name: str): return self._tools.get(name)
    def names(self) -> list[str]: return list(self._tools.keys())
    def as_dict(self) -> dict[str, SecurityTool]: return dict(self._tools)
    def __contains__(self, name: str) -> bool: return name in self._tools


def _make_executor(security_tools=None):
    return MissionToolExecutor(_StubComputer(), security_tools=security_tools)


def test_security_scan_dispatches_real_scanner_when_wired():
    scanner = _FakeScanner(computer := object(), name="nmap", stdout="PORT STATE\n22/open")
    reg = _FakeRegistry({"nmap": scanner})
    exe = _make_executor(security_tools=reg)
    action = PlannedAction(tool="target_security_scan", risk=ToolRisk.APPROVAL_REQUIRED, input={
        "tool": "nmap", "target": "scanme.example.org",
    })
    res = asyncio.run(exe.execute(action, target_workspace_id="ws-1", approved=True))
    assert res.status == "SUCCESS"
    assert res.evidence["tool"] == "nmap"
    assert res.evidence["target"] == "scanme.example.org"
    # The scanner was actually invoked (not stubbed by the executor).
    assert scanner.last_request is not None
    assert scanner.last_request.target == "scanme.example.org"
    # Parsed findings surfaced in evidence.
    assert res.evidence["parsed_findings"]


def test_security_scan_blocks_when_registry_not_configured():
    exe = _make_executor(security_tools=None)
    action = PlannedAction(tool="target_security_scan", risk=ToolRisk.APPROVAL_REQUIRED, input={
        "tool": "nmap", "target": "scanme.example.org",
    })
    res = asyncio.run(exe.execute(action, target_workspace_id="ws-1", approved=True))
    assert res.status == "BLOCKED"
    # Clear "not configured" message, NOT the generic "not implemented".
    assert "not configured" in res.output
    assert "not implemented" not in res.output


def test_security_scan_requires_approval():
    scanner = _FakeScanner(object(), name="nmap")
    reg = _FakeRegistry({"nmap": scanner})
    exe = _make_executor(security_tools=reg)
    action = PlannedAction(tool="target_security_scan", risk=ToolRisk.APPROVAL_REQUIRED, input={
        "tool": "nmap", "target": "scanme.example.org",
    })
    res = asyncio.run(exe.execute(action, target_workspace_id="ws-1", approved=False))
    assert res.status == "AWAITING_APPROVAL"
    # Scanner never runs without approval.
    assert scanner.last_request is None


def test_unregistered_scanner_blocks_with_available_list():
    scanner = _FakeScanner(object(), name="nmap")
    reg = _FakeRegistry({"nmap": scanner})
    exe = _make_executor(security_tools=reg)
    action = PlannedAction(tool="target_security_scan", risk=ToolRisk.APPROVAL_REQUIRED, input={
        "tool": "ffuf", "target": "scanme.example.org",
    })
    res = asyncio.run(exe.execute(action, target_workspace_id="ws-1", approved=True))
    assert res.status == "BLOCKED"
    assert "ffuf" in res.output
    assert "nmap" in res.output  # available list surfaced


def test_target_security_scan_is_registered_approval_required():
    from sonic.mission_engine.tool_registry import MissionToolRegistry, ToolRisk
    spec = MissionToolRegistry.get("target_security_scan")
    assert spec.risk == ToolRisk.APPROVAL_REQUIRED
