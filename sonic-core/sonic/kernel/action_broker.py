"""
SONIC v2 — Action Broker
=========================
The mandatory mediator between Agents/Specialists and execution providers.

Architectural Rule:
No agent, specialist, or autonomous subsystem may interact directly with a
ComputeProvider or execution environment. All requests must route through
ActionBroker -> SafetyKernel -> ComputeProvider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sonic.computer_use.models import ActionExecutionStatus
from sonic.kernel.native_bridge import NativeKernelClient
from sonic.logger import get_logger
from sonic.safety.kernel import _ACTION_MAP, KernelVerdict, SafetyAuthorization, SafetyKernel

logger = get_logger(__name__)


@dataclass
class BrokerResult:
    """Standard execution result returned by ActionBroker."""
    status: ActionExecutionStatus
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    authorization: SafetyAuthorization | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    duration_ms: float = 0.0

    @property
    def is_success(self) -> bool:
        return self.status in (
            ActionExecutionStatus.SUCCEEDED,
            ActionExecutionStatus.SUCCESS,
            ActionExecutionStatus.COMPLETED,
        )


class ActionBroker:
    """Mediates and governs all execution requests across the system."""

    def __init__(
        self,
        safety_kernel: SafetyKernel | None = None,
        tenant_id: str = "default",
        native_kernel_client: NativeKernelClient | None = None,
    ):
        self.tenant_id = tenant_id
        self.safety_kernel = safety_kernel or SafetyKernel(tenant_id=tenant_id)
        self.native_kernel_client = (
            native_kernel_client
            if native_kernel_client is not None
            else NativeKernelClient()
        )
        self._history: list[BrokerResult] = []

    def _extract_target(self, action_type: str, parameters: dict[str, Any]) -> str:
        if action_type in ("TERMINAL_COMMAND", "COMMAND", "EXECUTE_COMMAND", "TERMINAL_EXEC"):
            return str(parameters.get("command") or parameters.get("cmd") or "")
        if action_type in ("FILE_WRITE", "WRITE_FILE", "FILE_READ", "READ_FILE"):
            return str(parameters.get("path") or parameters.get("file_path") or "")
        if action_type == "SECURITY_TOOL":
            req = parameters.get("request")
            if req and hasattr(req, "target"):
                return str(req.target)
            return str(parameters.get("target") or "")
        if action_type in ("BROWSER_NAVIGATE", "HTTP_REQUEST"):
            return str(parameters.get("url") or parameters.get("target") or "")
        return str(parameters.get("target") or parameters.get("command") or parameters.get("path") or parameters.get("url") or "")

    def execute(
        self,
        action_type: str,
        parameters: dict[str, Any],
        provider: Any,
        approved: bool = False,
    ) -> BrokerResult:
        """Evaluates safety envelope, then dispatches to provider if permitted.
        
        Fail-closed: Returns status=BLOCKED with exit_code=126 on any authorization failure.
        """
        import time

        start_time = time.monotonic()

        # 0. Hardware/Native-speed pre-screening via NativeKernelClient (if available)
        if self.native_kernel_client:
            target = self._extract_target(action_type, parameters)
            canonical_action = _ACTION_MAP.get(action_type, action_type)
            try:
                native_verdict = self.native_kernel_client.authorize(
                    action_type=canonical_action,
                    target=target,
                    is_isolated=True,
                )
            except Exception as exc:
                logger.debug("Native kernel pre-screening error (failing-open to Python SafetyKernel): %s", exc)
                native_verdict = None

            if native_verdict is not None:
                if not native_verdict.seal_intact:
                    logger.error(
                        "action_broker_blocked_native_seal_tampered",
                        action_type=action_type,
                        tenant_id=self.tenant_id,
                    )
                    auth = SafetyAuthorization(
                        verdict=KernelVerdict.DENY,
                        reason=f"Native safety kernel seal tampered: {native_verdict.reason}",
                        action_type=action_type,
                        seal_intact=False,
                        audit_id=native_verdict.audit_id,
                    )
                    result = BrokerResult(
                        status=ActionExecutionStatus.BLOCKED,
                        exit_code=126,
                        stderr=auth.reason,
                        authorization=auth,
                        duration_ms=(time.monotonic() - start_time) * 1000.0,
                    )
                    self._history.append(result)
                    return result

                if native_verdict.verdict == "Deny":
                    logger.warning(
                        "action_broker_blocked_by_native_kernel",
                        action_type=action_type,
                        reason=native_verdict.reason,
                        tenant_id=self.tenant_id,
                    )
                    auth = SafetyAuthorization(
                        verdict=KernelVerdict.DENY,
                        reason=f"[NativeKernel Deny] {native_verdict.reason}",
                        action_type=action_type,
                        seal_intact=native_verdict.seal_intact,
                        audit_id=native_verdict.audit_id,
                    )
                    result = BrokerResult(
                        status=ActionExecutionStatus.BLOCKED,
                        exit_code=126,
                        stderr=auth.reason,
                        authorization=auth,
                        duration_ms=(time.monotonic() - start_time) * 1000.0,
                    )
                    self._history.append(result)
                    return result

                if native_verdict.verdict == "RequireApproval" and not approved:
                    logger.warning(
                        "action_broker_approval_required_by_native_kernel",
                        action_type=action_type,
                        reason=native_verdict.reason,
                        tenant_id=self.tenant_id,
                    )
                    auth = SafetyAuthorization(
                        verdict=KernelVerdict.REQUIRE_APPROVAL,
                        reason=f"[NativeKernel ApprovalRequired] {native_verdict.reason}",
                        action_type=action_type,
                        seal_intact=native_verdict.seal_intact,
                        audit_id=native_verdict.audit_id,
                    )
                    result = BrokerResult(
                        status=ActionExecutionStatus.BLOCKED,
                        exit_code=126,
                        stderr=auth.reason,
                        authorization=auth,
                        duration_ms=(time.monotonic() - start_time) * 1000.0,
                    )
                    self._history.append(result)
                    return result

        # 1. Gate check via SafetyKernel
        auth = self.safety_kernel.authorize(
            action_type=action_type,
            parameters=parameters,
            provider=provider,
        )

        if auth.verdict == KernelVerdict.DENY:
            logger.warning(
                "action_broker_blocked_by_kernel",
                action_type=action_type,
                reason=auth.reason,
                tenant_id=self.tenant_id,
            )
            result = BrokerResult(
                status=ActionExecutionStatus.BLOCKED,
                exit_code=126,
                stderr=auth.reason,
                authorization=auth,
                duration_ms=(time.monotonic() - start_time) * 1000.0,
            )
            self._history.append(result)
            return result

        if auth.verdict == KernelVerdict.REQUIRE_APPROVAL and not approved:
            logger.warning(
                "action_broker_approval_required",
                action_type=action_type,
                reason=auth.reason,
                tenant_id=self.tenant_id,
            )
            result = BrokerResult(
                status=ActionExecutionStatus.BLOCKED,
                exit_code=126,
                stderr=auth.reason,
                authorization=auth,
                duration_ms=(time.monotonic() - start_time) * 1000.0,
            )
            self._history.append(result)
            return result

        # 2. Dispatch to execution provider
        try:
            if action_type in ("TERMINAL_COMMAND", "COMMAND", "EXECUTE_COMMAND"):
                command = parameters.get("command") or parameters.get("cmd") or ""
                timeout = parameters.get("timeout_seconds", 30)
                exec_res = provider.execute(command, timeout_seconds=timeout)
                status = ActionExecutionStatus.SUCCEEDED if exec_res.exit_code == 0 else ActionExecutionStatus.FAILED
                result = BrokerResult(
                    status=status,
                    exit_code=exec_res.exit_code,
                    stdout=getattr(exec_res, "stdout", "") or "",
                    stderr=getattr(exec_res, "stderr", "") or "",
                    authorization=auth,
                    duration_ms=(time.monotonic() - start_time) * 1000.0,
                )
            elif action_type in ("FILE_WRITE", "WRITE_FILE"):
                path = parameters.get("path") or parameters.get("file_path") or ""
                content = parameters.get("content") or ""
                provider.write_file(path, content)
                result = BrokerResult(
                    status=ActionExecutionStatus.SUCCEEDED,
                    exit_code=0,
                    stdout=f"Wrote {len(content)} bytes to {path}",
                    authorization=auth,
                    duration_ms=(time.monotonic() - start_time) * 1000.0,
                )
            elif action_type in ("FILE_READ", "READ_FILE"):
                path = parameters.get("path") or parameters.get("file_path") or ""
                content = provider.read_file(path)
                result = BrokerResult(
                    status=ActionExecutionStatus.SUCCEEDED,
                    exit_code=0,
                    stdout=content if isinstance(content, str) else str(content),
                    authorization=auth,
                    duration_ms=(time.monotonic() - start_time) * 1000.0,
                )
            elif action_type == "SECURITY_TOOL":
                tool = parameters.get("tool")
                tool_request = parameters.get("request")
                if tool and hasattr(tool, "execute"):
                    tool_res = tool.execute(tool_request)
                    tool_status = getattr(tool_res, "status", None)
                    status = ActionExecutionStatus.SUCCEEDED if str(tool_status).lower() in ("success", "succeeded") else ActionExecutionStatus.FAILED
                    result = BrokerResult(
                        status=status,
                        exit_code=0 if status == ActionExecutionStatus.SUCCEEDED else 1,
                        stdout=str(getattr(tool_res, "findings", [])) if hasattr(tool_res, "findings") else "",
                        authorization=auth,
                        duration_ms=(time.monotonic() - start_time) * 1000.0,
                    )
                else:
                    result = BrokerResult(
                        status=ActionExecutionStatus.FAILED,
                        exit_code=1,
                        stderr="SecurityTool instance missing or invalid in parameters.",
                        authorization=auth,
                        duration_ms=(time.monotonic() - start_time) * 1000.0,
                    )
            else:
                # General action execution against provider
                if hasattr(provider, "dispatch_action"):
                    res = provider.dispatch_action(action_type, parameters)
                    result = BrokerResult(
                        status=ActionExecutionStatus.SUCCEEDED,
                        exit_code=0,
                        stdout=str(res),
                        authorization=auth,
                        duration_ms=(time.monotonic() - start_time) * 1000.0,
                    )
                else:
                    result = BrokerResult(
                        status=ActionExecutionStatus.FAILED,
                        exit_code=1,
                        stderr=f"Provider {provider.__class__.__name__} cannot execute action '{action_type}'.",
                        authorization=auth,
                        duration_ms=(time.monotonic() - start_time) * 1000.0,
                    )
        except Exception as exc:
            logger.error("action_broker_dispatch_error", error=str(exc), action_type=action_type)
            result = BrokerResult(
                status=ActionExecutionStatus.FAILED,
                exit_code=1,
                stderr=str(exc),
                authorization=auth,
                duration_ms=(time.monotonic() - start_time) * 1000.0,
            )

        self._history.append(result)
        return result
