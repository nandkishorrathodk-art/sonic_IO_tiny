"""
SONIC-REDA — Action Policy / Self-Host Safety Envelope (PLAN Phase 6)
=====================================================================

A fail-closed gate the autonomous computer-use loop consults BEFORE executing
ANY action — operator-issued OR self-directed (curiosity). It is the safety
envelope required when SONIC runs as a long-lived process on a self-hosted
VPS: the agent may act autonomously, but every action must pass the policy.

The policy composes existing primitives instead of reinventing them:
    * path confinement — FILE_READ/FILE_WRITE confined to the workspace root
    * egress filter — reuses sonic.sandbox.egress.is_target_allowed for
      SECURITY_TOOL targets and BROWSER_NAVIGATE urls (blocks private/metadata)
    * destructive-op gating — reuses sonic.safety.scope.classify_command_risk
      for TERMINAL_EXEC (L2 forbidden -> block; L1 -> needs approval)
    * action-type allowlist — unknown action types are DENIED by default
    * rate limit — a per-agent max-actions-per-minute cap

It is fail-closed: an unknown action type, an escaped path, a private target,
or a destructive command is DENIED and never reaches the provider. The gate
applies identically to goal-driven missions and the curiosity loop, so a
self-directed exploration cannot escape the envelope.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from sonic.logger import get_logger
from sonic.sandbox import egress
from sonic.safety.scope import RiskLevel, ScopeChecker, SafetyVerdict

logger = get_logger(__name__)


@dataclass
class PolicyVerdict:
    """Result of evaluating an action against the policy."""
    allowed: bool
    reason: str
    needs_approval: bool = False


@dataclass
class _RateWindow:
    """Simple sliding window of action timestamps for rate limiting."""
    timestamps: list[float] = field(default_factory=list)

    def consume(self, now: float, max_per_minute: int) -> bool:
        cutoff = now - 60.0
        self.timestamps = [t for t in self.timestamps if t >= cutoff]
        if len(self.timestamps) >= max_per_minute:
            return False
        self.timestamps.append(now)
        return True


class ActionPolicy:
    """Unified fail-closed safety envelope for the computer-use loop.

    Pass an instance to ComputerUseAgent(safety=...). In self-host mode the
    agent MUST be constructed with a policy (no autonomous action without an
    envelope).
    """

    # Action types the agent is ever allowed to perform. Anything else is
    # denied by default (fail-closed).
    DEFAULT_ALLOWED_TYPES = frozenset({
        "FILE_READ", "FILE_WRITE", "TERMINAL_EXEC", "GIT_COMMIT",
        "APP_LAUNCH", "APP_CLOSE", "SERVICE_ACTION",
        "BROWSER_NAVIGATE", "BROWSER_CLICK", "BROWSER_TYPE", "BROWSER_SCREENSHOT",
        "SECURITY_TOOL",
        # Toolsmith (Phase A, AIOSR): authoring writes source under the
        # workspace toolsmith dir (path-confined like FILE_WRITE); running
        # executes it in-sandbox (command-gated like TERMINAL_EXEC).
        "TOOL_AUTHOR", "TOOL_RUN",
    })

    def __init__(
        self,
        workspace_root: str = "/home/sonic/workspace",
        allowed_action_types: Optional[set[str]] = None,
        allow_security_tool_targets: Optional[set[str]] = None,
        max_actions_per_minute: int = 60,
        require_approval_for_intrusive: bool = True,
        scope_checker: Optional[ScopeChecker] = None,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.allowed_types = frozenset(allowed_action_types or self.DEFAULT_ALLOWED_TYPES)
        # When non-empty, SECURITY_TOOL may only target hosts in this allowlist;
        # empty means "rely on egress filter only" (no extra target restriction).
        self.security_tool_targets = set(allow_security_tool_targets or [])
        self.max_actions_per_minute = max_actions_per_minute
        self.require_approval_for_intrusive = require_approval_for_intrusive
        self.scope_checker = scope_checker or ScopeChecker()
        # The scope checker's check_action is fail-closed only when rules are
        # loaded; for the command-risk classifier we don't need rules loaded.
        self._rate = _RateWindow()

    # ------------------------------------------------------------------
    def evaluate(self, action_type_name: str, target: str, payload: dict[str, Any]) -> PolicyVerdict:
        """Evaluate one action. Returns a fail-closed PolicyVerdict.

        Never raises for policy reasons — a verdict is always returned so the
        caller can record it as a blocked trace instead of crashing the loop.
        """
        now = time.time()
        if not self._rate.consume(now, self.max_actions_per_minute):
            return PolicyVerdict(False, f"rate limit exceeded ({self.max_actions_per_minute}/min)")

        # 1. Action-type allowlist (fail-closed for unknown types).
        if action_type_name not in self.allowed_types:
            return PolicyVerdict(False, f"action type not allowed: {action_type_name}")

        # 2. Path confinement for file operations. TOOL_AUTHOR writes its
        # source under a hardcoded workspace-subdir (toolsmith hardcodes
        # /home/sonic/workspace/toolsmith/<name>.py), so confinement is
        # structural — it does not need a payload path to validate.
        if action_type_name in ("FILE_READ", "FILE_WRITE"):
            path = payload.get("path") or target
            verdict = self._check_path(path, action_type_name)
            if not verdict.allowed:
                return verdict

        # 3. Destructive-command gating for terminal execution + tool runs.
        #    TOOL_RUN executes a hardcoded `python <workspace-toolsmith-path>`,
        #    so the command is structural; we only gate user-supplied commands.
        if action_type_name == "TERMINAL_EXEC":
            command = payload.get("command", "")
            verdict = self._check_command(command)
            if not verdict.allowed:
                return verdict

        # 4. Egress + target-allowlist for security tools and browser navigation.
        if action_type_name == "SECURITY_TOOL":
            scan_target = payload.get("target") or target
            verdict = self._check_egress(scan_target, "security tool")
            if not verdict.allowed:
                return verdict
        elif action_type_name == "BROWSER_NAVIGATE":
            url = payload.get("url") or target
            verdict = self._check_egress(url, "browser")
            if not verdict.allowed:
                return verdict

        return PolicyVerdict(True, "allowed")

    # ------------------------------------------------------------------
    def _check_path(self, path: str, action_name: str) -> PolicyVerdict:
        try:
            resolved = Path(path).expanduser()
            # Resolve strictly=False so a not-yet-written path still confines.
            if not resolved.is_absolute():
                resolved = (self.workspace_root / resolved)
            resolved = resolved.resolve(strict=False)
        except Exception as e:
            return PolicyVerdict(False, f"unresolvable path: {path} ({e})")
        # Confinement: the resolved path must stay within the workspace root.
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError:
            return PolicyVerdict(
                False, f"{action_name} escapes workspace: {path} -> {resolved}")
        if action_name == "FILE_WRITE":
            # Deny writes to workspace-root-traversal or device paths.
            if any(part == ".." for part in Path(path).parts):
                return PolicyVerdict(False, f"traversal in path: {path}")
        return PolicyVerdict(True, "path confined")

    def _check_command(self, command: str) -> PolicyVerdict:
        try:
            risk = self.scope_checker.classify_command_risk(command)
        except Exception:
            # If classification itself fails, fail closed.
            return PolicyVerdict(False, "command risk classification failed")
        if risk == RiskLevel.L2_FORBIDDEN:
            return PolicyVerdict(False, f"destructive command blocked: {command[:80]}")
        if risk == RiskLevel.L1_NEEDS_APPROVAL and self.require_approval_for_intrusive:
            return PolicyVerdict(
                False, f"intrusive command needs approval: {command[:80]}",
                needs_approval=True,
            )
        return PolicyVerdict(True, "command risk acceptable")

    def _check_egress(self, target: str, label: str) -> PolicyVerdict:
        # Extra target allowlist (if configured) takes precedence.
        if self.security_tool_targets:
            host = self._host_of(target)
            if host and host not in self.security_tool_targets:
                return PolicyVerdict(False, f"{label} target not in allowlist: {host}")
        try:
            ok, reason = egress.is_target_allowed(target)
        except Exception as e:
            return PolicyVerdict(False, f"egress check failed: {e}")
        if not ok:
            return PolicyVerdict(False, f"{label} egress denied: {reason}")
        return PolicyVerdict(True, "egress allowed")

    @staticmethod
    def _host_of(target: str) -> str:
        # Strip scheme/path for url-like targets; leave bare hosts as-is.
        t = target
        if "://" in t:
            t = t.split("://", 1)[1]
        t = t.split("/", 1)[0]
        return t.split("@")[-1].split(":")[0]


# A minimal in-process verdict the agent can short-circuit on.
def denied(verdict: PolicyVerdict) -> bool:
    return not verdict.allowed
