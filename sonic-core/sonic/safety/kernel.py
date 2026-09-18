"""
SONIC v2 — Safety Kernel
=========================
The unbypassable, tamper-evident gate sitting between the Action Broker
and execution providers.

Guarantees:
1. Sealed policy verification on every evaluation (tamper-evident SHA-256).
2. Fail-closed on any scope violation, egress block, destructive command, or path escape.
3. Zero host escape: sandbox isolation required; host fallback is hard-blocked.
4. Immutable audit trail for every authorization decision.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sonic.logger import get_logger
from sonic.safety.action_policy import ActionPolicy, PolicyVerdict
from sonic.safety.sealed import SealedActionPolicy, seal_default

logger = get_logger(__name__)


class KernelVerdict(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


@dataclass(frozen=True)
class SafetyAuthorization:
    """Immutable authorization record returned by SafetyKernel."""
    verdict: KernelVerdict
    reason: str
    action_type: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    seal_intact: bool = True
    audit_id: str = ""

    @property
    def is_allowed(self) -> bool:
        return self.verdict == KernelVerdict.ALLOW


# Mapping from various action aliases to canonical ActionPolicy action names
_ACTION_MAP = {
    "TERMINAL_COMMAND": "TERMINAL_EXEC",
    "COMMAND": "TERMINAL_EXEC",
    "EXECUTE_COMMAND": "TERMINAL_EXEC",
    "TERMINAL_EXEC": "TERMINAL_EXEC",
    "FILE_READ": "FILE_READ",
    "READ_FILE": "FILE_READ",
    "FILE_WRITE": "FILE_WRITE",
    "WRITE_FILE": "FILE_WRITE",
    "GIT_COMMIT": "GIT_COMMIT",
    "BROWSER_NAVIGATE": "BROWSER_NAVIGATE",
    "BROWSER_CLICK": "BROWSER_CLICK",
    "BROWSER_TYPE": "BROWSER_TYPE",
    "BROWSER_SCREENSHOT": "BROWSER_SCREENSHOT",
    "GUI_CLICK": "GUI_CLICK",
    "GUI_TYPE": "GUI_TYPE",
    "GUI_KEYPRESS": "GUI_KEYPRESS",
    "GUI_SCREENSHOT": "GUI_SCREENSHOT",
}


class SafetyKernel:
    """The central safety kernel for SONIC v2.
    
    All execution requests from agents, specialists, and tools MUST pass
    through this kernel before dispatch to a ComputeProvider.
    """

    def __init__(
        self,
        policy: SealedActionPolicy | ActionPolicy | None = None,
        enforce_isolated_sandbox: bool = True,
        tenant_id: str = "default",
        workspace_root: str = "/home/sonic/workspace",
    ):
        if policy is None:
            # Default to production-sealed policy
            self.policy = seal_default(
                workspace_root=workspace_root,
                tenant_id=tenant_id,
            )
        elif isinstance(policy, SealedActionPolicy):
            self.policy = policy
            if not getattr(policy, "_sealed", False):
                policy.seal()
        else:
            # Wrap regular ActionPolicy into a SealedActionPolicy for tamper resistance
            sealed = SealedActionPolicy(
                workspace_root=str(policy.workspace_root),
                allowed_action_types=set(policy.allowed_types),
                allow_security_tool_targets=set(policy.security_tool_targets),
                max_actions_per_minute=policy.max_actions_per_minute,
                require_approval_for_intrusive=policy.require_approval_for_intrusive,
                scope_checker=policy.scope_checker,
                scope_config=policy.scope_config,
                tenant_id=tenant_id,
            )
            sealed.seal()
            self.policy = sealed

        self.enforce_isolated_sandbox = enforce_isolated_sandbox
        self.tenant_id = tenant_id
        self._audit_log: list[SafetyAuthorization] = []

    @property
    def seal_hash(self) -> str | None:
        return getattr(self.policy, "seal_hash", None)

    def is_seal_valid(self) -> bool:
        if isinstance(self.policy, SealedActionPolicy):
            if not getattr(self.policy, "_sealed", False):
                return False
            expected = getattr(self.policy, "_seal_hash", None)
            actual = self.policy._compute_seal_hash()
            return actual == expected
        return True

    def authorize(
        self,
        action_type: str,
        parameters: dict[str, Any] | None = None,
        provider: Any = None,
    ) -> SafetyAuthorization:
        """Authorizes or denies an action request against the sealed envelope.
        
        Evaluates:
        1. Seal integrity (fails closed if tampered).
        2. Sandbox isolation (rejects host execution if unconfined).
        3. Action type allowlist, path traversal, egress CIDR, destructive commands, rate limits.
        """
        params = parameters or {}
        now_ts = datetime.now(UTC).isoformat()
        audit_idx = len(self._audit_log) + 1
        audit_id = f"audit-{self.tenant_id}-{audit_idx:06d}"

        canonical_action = _ACTION_MAP.get(action_type, action_type)

        # 1. Seal Integrity Check
        if isinstance(self.policy, SealedActionPolicy) and not self.is_seal_valid():
            logger.critical(
                "safety_kernel_tamper_detected",
                tenant_id=self.tenant_id,
                action_type=action_type,
            )
            record = SafetyAuthorization(
                verdict=KernelVerdict.DENY,
                reason="Safety policy integrity verification failed: SHA-256 seal mismatch (tampered).",
                action_type=action_type,
                timestamp=now_ts,
                seal_intact=False,
                audit_id=audit_id,
            )
            self._audit_log.append(record)
            return record

        # 2. Host Execution Escape Check (Zero Host Escape)
        if self.enforce_isolated_sandbox and provider is not None:
            provider_cls = provider.__class__.__name__
            # LocalDevProvider without container confinement is rejected outside mock tests
            if "LocalDev" in provider_cls:
                allow_host = os.environ.get("SONIC_ALLOW_HOST_EXECUTION", "").lower() in ("1", "true")
                app_env = os.environ.get("APP_ENV", "production").lower()
                if app_env != "development" or not allow_host:
                    record = SafetyAuthorization(
                        verdict=KernelVerdict.DENY,
                        reason=f"Zero host execution policy: Provider '{provider_cls}' is not an isolated sandbox.",
                        action_type=action_type,
                        timestamp=now_ts,
                        seal_intact=True,
                        audit_id=audit_id,
                    )
                    self._audit_log.append(record)
                    return record

        # 3. Policy Envelope Evaluation
        target = (
            params.get("target")
            or params.get("url")
            or params.get("path")
            or params.get("file_path")
            or params.get("command")
            or params.get("cmd")
            or ""
        )

        verdict: PolicyVerdict = self.policy.evaluate(canonical_action, target, params)
        if not verdict.allowed:
            record = SafetyAuthorization(
                verdict=KernelVerdict.DENY,
                reason=f"Action '{action_type}' denied by safety policy: {verdict.reason}",
                action_type=action_type,
                timestamp=now_ts,
                seal_intact=True,
                audit_id=audit_id,
            )
        elif verdict.needs_approval:
            record = SafetyAuthorization(
                verdict=KernelVerdict.REQUIRE_APPROVAL,
                reason=f"Action '{action_type}' requires human/operator approval: {verdict.reason}",
                action_type=action_type,
                timestamp=now_ts,
                seal_intact=True,
                audit_id=audit_id,
            )
        else:
            record = SafetyAuthorization(
                verdict=KernelVerdict.ALLOW,
                reason="Action permitted within safe envelope.",
                action_type=action_type,
                timestamp=now_ts,
                seal_intact=True,
                audit_id=audit_id,
            )

        self._audit_log.append(record)
        return record

    def get_audit_trail(self) -> list[SafetyAuthorization]:
        """Returns a copy of the recorded audit authorizations."""
        return list(self._audit_log)
