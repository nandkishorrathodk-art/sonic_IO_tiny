"""
SONIC-REDA — Structured Security Tool Execution Abstraction (Tool Plane)
==========================================================================
Defines the unified SecurityTool contract, ToolRequest, ToolExecution,
ToolResult, ToolEvidence, and ToolMetrics.

SECURITY INVARIANT:
    All tools MUST execute through a ComputeProvider workspace.
    Zero direct host OS subprocess execution.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

from sonic.logger import get_logger
from sonic.sandbox.provider import ComputeProvider, ExecResult

logger = get_logger(__name__)


class ToolStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    BLOCKED = "blocked"


@dataclass
class ToolMetrics:
    """Metrics collected during tool execution."""
    duration_seconds: float = 0.0
    bytes_sent: int = 0
    bytes_received: int = 0
    requests_made: int = 0
    exit_code: int = 0


@dataclass
class ToolEvidence:
    """Raw evidence captured from tool execution."""
    evidence_type: str  # "stdout", "raw_http", "ndjson", "xml", "har"
    content: str
    sha256_hash: str = ""
    description: str = ""


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


@dataclass
class ToolResult:
    """Structured result returned by a security tool adapter."""
    execution_id: str
    tenant_id: str
    engagement_id: str
    workspace_id: str
    agent_id: str
    tool_name: str
    tool_version: str
    status: ToolStatus
    start_time: str
    end_time: str
    exit_code: int
    raw_stdout: str
    raw_stderr: str
    parsed_data: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[ToolEvidence] = field(default_factory=list)
    metrics: ToolMetrics = field(default_factory=ToolMetrics)
    error_message: Optional[str] = None


class SecurityTool(ABC):
    """
    Abstract Base Class for all security tool execution adapters.
    """

    def __init__(self, provider: ComputeProvider):
        self.provider = provider

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the tool (e.g. 'nmap', 'nuclei', 'ffuf')."""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Version of the tool."""
        pass

    @abstractmethod
    def build_command(self, request: ToolRequest) -> str:
        """Construct the CLI command string to run inside the sandbox."""
        pass

    @abstractmethod
    def parse_output(self, raw_stdout: str, raw_stderr: str) -> list[dict[str, Any]]:
        """Parse raw tool output into structured vulnerability/asset objects."""
        pass

    async def execute(self, request: ToolRequest) -> ToolResult:
        """
        Execute tool strictly inside the ComputeProvider workspace.
        Fails closed if the workspace is unavailable.
        """
        start_dt = datetime.now(timezone.utc)
        cmd = self.build_command(request)

        logger.info(
            "tool_execution_started",
            tool=self.name,
            execution_id=request.execution_id,
            tenant_id=request.tenant_id,
            workspace_id=request.workspace_id,
        )

        exec_res: ExecResult = await self.provider.execute(
            workspace_id=request.workspace_id,
            command=cmd,
            timeout=request.timeout_seconds,
        )

        end_dt = datetime.now(timezone.utc)
        duration = (end_dt - start_dt).total_seconds()

        # Handle timeout or execution errors
        if exec_res.timed_out:
            status = ToolStatus.TIMED_OUT
            err = f"Tool execution timed out after {request.timeout_seconds}s"
        elif exec_res.exit_code == 126:
            status = ToolStatus.BLOCKED
            err = exec_res.stderr or "Execution blocked by fail-closed security engine"
        elif exec_res.exit_code != 0 and not exec_res.stdout:
            status = ToolStatus.FAILED
            err = exec_res.stderr or f"Tool exited with code {exec_res.exit_code}"
        else:
            status = ToolStatus.COMPLETED
            err = None

        # Parse output
        parsed_data = []
        if exec_res.stdout:
            try:
                parsed_data = self.parse_output(exec_res.stdout, exec_res.stderr)
            except Exception as e:
                logger.error("tool_output_parsing_failed", tool=self.name, error=str(e))
                err = f"Output parsing error: {str(e)}"

        # Build evidence
        evidence_items = []
        if exec_res.stdout:
            evidence_items.append(ToolEvidence(
                evidence_type="stdout",
                content=exec_res.stdout,
                description=f"Raw {self.name} stdout output",
            ))

        metrics = ToolMetrics(
            duration_seconds=round(duration, 2),
            exit_code=exec_res.exit_code,
            bytes_received=len(exec_res.stdout.encode("utf-8")),
        )

        return ToolResult(
            execution_id=request.execution_id,
            tenant_id=request.tenant_id,
            engagement_id=request.engagement_id,
            workspace_id=request.workspace_id,
            agent_id=request.agent_id,
            tool_name=self.name,
            tool_version=self.version,
            status=status,
            start_time=start_dt.isoformat(),
            end_time=end_dt.isoformat(),
            exit_code=exec_res.exit_code,
            raw_stdout=exec_res.stdout,
            raw_stderr=exec_res.stderr,
            parsed_data=parsed_data,
            evidence=evidence_items,
            metrics=metrics,
            error_message=err,
        )
