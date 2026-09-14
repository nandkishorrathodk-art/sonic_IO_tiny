"""
SONIC-REDA ??? Action Policy / Self-Host Safety Envelope (PLAN Phase 6)
=====================================================================

A fail-closed gate the autonomous computer-use loop consults BEFORE executing
ANY action ??? operator-issued OR self-directed (curiosity). It is the safety
envelope required when SONIC runs as a long-lived process on a self-hosted
VPS: the agent may act autonomously, but every action must pass the policy.

The policy composes existing primitives instead of reinventing them:
    * path confinement ??? FILE_READ/FILE_WRITE confined to the workspace root
    * egress filter ??? reuses sonic.sandbox.egress.is_target_allowed for
      SECURITY_TOOL targets and BROWSER_NAVIGATE urls (blocks private/metadata)
    * destructive-op gating ??? reuses sonic.safety.scope.classify_command_risk
      for TERMINAL_EXEC (L2 forbidden -> block; L1 -> needs approval)
    * action-type allowlist ??? unknown action types are DENIED by default
    * rate limit ??? a per-agent max-actions-per-minute cap

It is fail-closed: an unknown action type, an escaped path, a private target,
or a destructive command is DENIED and never reaches the provider. The gate
applies identically to goal-driven missions and the curiosity loop, so a
self-directed exploration cannot escape the envelope.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sonic.logger import get_logger
from sonic.safety.scope import RiskLevel, ScopeChecker
from sonic.safety.runtime_stop import get_runtime_stop_state
from sonic.sandbox import egress

logger = get_logger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _risk_db_path() -> str:
    from sonic.memory.sqlite_graph import _default_db_path as _g
    return os.environ.get("SONIC_RISK_DB_PATH") or os.environ.get("SONIC_MEMORY_DB_PATH") or _g()


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
        # GUI desktop interaction (in-sandbox only, no host execution risk)
        "GUI_CLICK", "GUI_DOUBLE_CLICK", "GUI_RIGHT_CLICK", "GUI_TYPE", "GUI_KEYPRESS",
        "GUI_MOVE", "GUI_SCROLL", "GUI_SCREENSHOT", "GUI_DRAG", "GUI_WAIT",
        "FILE_READ", "FILE_WRITE", "TERMINAL_EXEC", "GIT_COMMIT",
        "APP_LAUNCH", "APP_CLOSE", "APP_FOCUS", "APP_INSTALL", "SERVICE_ACTION",
        "BROWSER_NAVIGATE", "BROWSER_CLICK", "BROWSER_TYPE", "BROWSER_SCREENSHOT",
        "BROWSER_WAIT", "BROWSER_DOWNLOAD",
        "SECURITY_TOOL",
        # Toolsmith (Phase A, AIOSR): authoring writes source under the
        # workspace toolsmith dir (path-confined like FILE_WRITE); running
        # executes it in-sandbox (command-gated like TERMINAL_EXEC).
        "TOOL_AUTHOR", "TOOL_RUN",
        # Method-invention (Phase B, AIOSR): synthesizes a novel technique and
        # runs its probe in-sandbox (same structural confinement as TOOL_RUN).
        "METHOD_INVENT",
    })

    def __init__(
        self,
        workspace_root: str = "/home/sonic/workspace",
        allowed_action_types: set[str] | None = None,
        allow_security_tool_targets: set[str] | None = None,
        max_actions_per_minute: int = 60,
        require_approval_for_intrusive: bool = True,
        scope_checker: ScopeChecker | None = None,
        scope_config: dict | None = None,
        allow_private_networks: bool = False,
        tenant_id: str = "default",
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.allowed_types = frozenset(allowed_action_types or self.DEFAULT_ALLOWED_TYPES)
        # When non-empty, SECURITY_TOOL may only target hosts in this allowlist;
        # empty means "rely on egress filter only" (no extra target restriction).
        self.security_tool_targets = set(allow_security_tool_targets or [])
        self.max_actions_per_minute = max_actions_per_minute
        self.require_approval_for_intrusive = require_approval_for_intrusive
        self.scope_checker = scope_checker or ScopeChecker()
        self.scope_config = scope_config
        self.allow_private_networks = allow_private_networks
        self.tenant_id = tenant_id
        # The scope checker's check_action is fail-closed only when rules are
        # loaded; for the command-risk classifier we don't need rules loaded.
        self._rate = _RateWindow()

    def clone_for_agent(self, agent_id: str = "") -> ActionPolicy:
        """Clone policy with an independent rate window for a concurrent subagent."""
        return ActionPolicy(
            workspace_root=str(self.workspace_root),
            allowed_action_types=set(self.allowed_types),
            allow_security_tool_targets=set(self.security_tool_targets),
            max_actions_per_minute=self.max_actions_per_minute,
            require_approval_for_intrusive=self.require_approval_for_intrusive,
            scope_checker=self.scope_checker,
            scope_config=self.scope_config,
            allow_private_networks=self.allow_private_networks,
            tenant_id=self.tenant_id,
        )

    # ------------------------------------------------------------------
    def evaluate(self, action_type_name: str, target: str, payload: dict[str, Any]) -> PolicyVerdict:
        """Evaluate one action. Returns a fail-closed PolicyVerdict.

        Never raises for policy reasons ??? a verdict is always returned so the
        caller can record it as a blocked trace instead of crashing the loop.
        """
        now = time.time()
        if not self.scope_checker.kill_switch_enabled:
            return PolicyVerdict(False, "configured kill switch is disabled")
        stop_state = get_runtime_stop_state()
        if stop_state.is_stopped(self.tenant_id):
            return PolicyVerdict(False, f"runtime kill switch asserted: {stop_state.reason(self.tenant_id)}")
        if not self._rate.consume(now, self.max_actions_per_minute):
            return PolicyVerdict(False, f"rate limit exceeded ({self.max_actions_per_minute}/min)")

        # 1. Action-type allowlist (fail-closed for unknown types).
        if action_type_name not in self.allowed_types:
            return PolicyVerdict(False, f"action type not allowed: {action_type_name}")

        # 2. Path confinement for file operations. TOOL_AUTHOR writes its
        # source under a hardcoded workspace-subdir (toolsmith hardcodes
        # /home/sonic/workspace/toolsmith/<name>.py), so confinement is
        # structural ??? it does not need a payload path to validate.
        if action_type_name in ("FILE_READ", "FILE_WRITE"):
            path = payload.get("path") or target
            verdict = self._check_path(path, action_type_name)
            if not verdict.allowed:
                return verdict

        # 3. Destructive-command gating for terminal execution + tool runs.
        #    TOOL_RUN executes a hardcoded `python <workspace-toolsmith-path>`,
        #    so the command is structural; we only gate user-supplied commands.
        if action_type_name == "TERMINAL_EXEC":
            command = payload.get("command") or payload.get("cmd") or target or ""
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
            parsed = urlparse(str(url).strip())
            if parsed.scheme.lower() not in {"http", "https"}:
                return PolicyVerdict(False, "browser navigation only permits http/https URLs")
            if parsed.username or parsed.password:
                return PolicyVerdict(False, "browser navigation forbids embedded URL credentials")
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

    _CLOUD_METADATA_RE = re.compile(
        r"169\.254\.169\.254"
        r"|instance-data(?:\.ec2\.internal)?\b"
        r"|metadata\.google\.internal\b"
        r"|metadata\.azure\.com\b",
        re.IGNORECASE,
    )

    def _check_command(self, command: str) -> PolicyVerdict:
        # TERMINAL_EXEC bypasses the URL-egress filter (it runs shell howeverthe
        # operator/being chooses). Close the metadata hole explicitly: a shell
        # command must never reach the cloud metadata endpoint ??? on the host Or
        # inside an egress-unrestricted container???
        if self._CLOUD_METADATA_RE.search(command or ""):
            return PolicyVerdict(False, "cloud metadata access blocked in terminal command")
        # Shell commands are another egress surface (curl, wget, python
        # requests, etc.). When an engagement target allowlist is active,
        # validate every explicit URL before the command reaches the provider.
        # This keeps verification probes and model-authored commands bound to
        # the same target as browser/security-tool actions.
        for candidate in re.findall(r"https?://[^\s'\"`;&|)]+", command or "", re.IGNORECASE):
            verdict = self._check_egress(candidate, "terminal")
            if not verdict.allowed:
                return verdict
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

    def _check_target_and_scope(self, target: str, label: str) -> PolicyVerdict | None:
        host = self._host_of(target)
        # Extra target allowlist (if configured) takes precedence.
        if self.security_tool_targets:
            if not host or (host not in self.security_tool_targets and target not in self.security_tool_targets):
                return PolicyVerdict(False, f"{label} target not in allowlist: {host or target}")

        # Scope enforcement if scope_checker has active scope rules configured
        scope_cfg = self._get_active_scope_config()
        if scope_cfg is not None and getattr(self, "scope_checker", None):
            target_to_check = host or target
            if not self.scope_checker.is_target_in_scope(target_to_check, scope_cfg):
                return PolicyVerdict(False, f"{label} target out of engagement scope: {target_to_check}")

        return None

    def _get_active_scope_config(self) -> dict | None:
        checker = getattr(self, "scope_checker", None)
        cfg = getattr(self, "scope_config", None) or (getattr(checker, "scope_config", None) if checker else None)
        if not cfg and checker and hasattr(checker, "_rules") and isinstance(checker._rules, dict):
            if "targets" in checker._rules or "exclusions" in checker._rules:
                cfg = checker._rules

        if not cfg or not isinstance(cfg, dict):
            return None

        targets = cfg.get("targets", {}) if isinstance(cfg.get("targets"), dict) else {}
        exclusions = cfg.get("exclusions", {}) if isinstance(cfg.get("exclusions"), dict) else {}
        has_rules = bool(
            targets.get("domains")
            or targets.get("ips")
            or exclusions.get("domains")
            or exclusions.get("ips")
        )
        return cfg if has_rules else None

    def _check_egress(self, target: str, label: str) -> PolicyVerdict:
        verdict = self._check_target_and_scope(target, label)
        if verdict is not None:
            return verdict
        allow_private = False
        host = self._host_of(target)
        if (
            getattr(self, "allow_private_networks", False)
            or (self.security_tool_targets and (host in self.security_tool_targets or target in self.security_tool_targets))
        ):
            allow_private = True
        try:
            ok, reason = egress.is_target_allowed(target, allow_private_for_tests=allow_private)
        except Exception as e:
            return PolicyVerdict(False, f"egress check failed: {e}")
        if not ok:
            return PolicyVerdict(False, f"{label} egress denied: {reason}")
        return PolicyVerdict(True, "egress allowed")

    @staticmethod
    def _host_of(target: str) -> str:
        # Strip scheme/path for url-like targets; leave bare hosts as-is.
        t = target.strip()
        if "://" in t:
            t = t.split("://", 1)[1]
        t = t.split("/", 1)[0]
        t = t.split("@")[-1]
        if t.startswith("[") and "]" in t:
            return t[1:t.index("]")]
        return t.split(":")[0]


# A minimal in-process verdict the agent can short-circuit on.
def denied(verdict: PolicyVerdict) -> bool:
    return not verdict.allowed

# ---------------------------------------------------------------------------
# NEXUS L9 -- Risk Portfolio Governor
# ---------------------------------------------------------------------------

@dataclass
class RiskBudgetDecision:
    """The governor's verdict on a proposed offensive action portfolio."""
    request_id: str
    action: str
    severity: str                    # info | low | medium | high | critical
    remaining_budget: float          # 0.0..1.0 before this draw
    allowed: bool
    remaining_after: float
    reason: str
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action": self.action,
            "severity": self.severity,
            "remaining_budget": self.remaining_budget,
            "allowed": self.allowed,
            "remaining_after": self.remaining_after,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


class RiskPortfolioGovernor:
    """A mission-level risk budget layered ABOVE the per-action ActionPolicy.

    The ActionPolicy gates every single action (fail-closed). The RiskGovernor
    additionally enforces that a *portfolio* of offensive actions does not
    exceed a cumulative risk budget ??? preventing a campaign of individually
    legal actions from compounding into an unsafe overreach abroad.

    Budget model: 1.0 initial. Each action draws `severity` weight
    (info->0.1, low->0.25, medium->0.5, high->0.85, critical->1.3).
    Crossing the ceiling sinks the request. Budget slowly replenishes over time
    (the risk "bleeds back") so a mission can continue after cooling down.
    """

    _SEVERITY_WEIGHT = {
        "info": 0.1,
        "low": 0.25,
        "medium": 0.5,
        "high": 0.85,
        "critical": 1.3,
    }
    _REPLENISH_PER_SECOND = 0.02

    def __init__(self, ceiling: float = 1.0, db_path: str | None = None) -> None:
        self.ceiling = ceiling
        self.db_path = db_path or _risk_db_path()
        self._budget = 1.0
        self._last_update = time.time()
        self._decisions: list[RiskBudgetDecision] = []
        self._total_drawn = 0.0
        self._init_db()

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS risk_budget_decisions (
                    request_id TEXT PRIMARY KEY,
                    action TEXT,
                    severity TEXT,
                    remaining_budget REAL,
                    allowed INTEGER,
                    remaining_after REAL,
                    reason TEXT,
                    timestamp TEXT
                )
                """
            )

    def _persist(self, d: RiskBudgetDecision) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO risk_budget_decisions VALUES (?,?,?,?,?,?,?,?)",
                    (
                        d.request_id, d.action, d.severity,
                        d.remaining_budget, int(d.allowed), d.remaining_after,
                        d.reason, d.timestamp,
                    ),
                )
        except sqlite3.Error as e:
            logger.warning("risk_gov_persist_failed", error=str(e))

    def _replenish(self) -> None:
        """Slowly restore budget over time so a cooled-down mission can continue."""
        now = time.time()
        elapsed = now - self._last_update
        self._last_update = now
        self._budget = min(1.0, self._budget + elapsed * self._REPLENISH_PER_SECOND)

    def assess(self, action: str, severity: str) -> RiskBudgetDecision:
        """Evaluate one more offensive action against the remaining budget."""
        self._replenish()
        sev = severity if severity in self._SEVERITY_WEIGHT else "medium"
        draw = self._SEVERITY_WEIGHT[sev]
        remaining_before = self._budget
        allowed = remaining_before - draw >= -0.001
        if allowed:
            self._budget = max(0.0, self._budget - draw)
            self._total_drawn += draw
            reason = f"Draw {draw:.2f} ({sev}) from remaining budget {remaining_before:.2f}."
        else:
            reason = (f"Denied: draw {draw:.2f} ({sev}) exceeds remaining "
                      f"budget {remaining_before:.2f}. Mission must cool down or reduce "
                      f"portfolio excess.")
        decision = RiskBudgetDecision(
            request_id=f"risk-{uuid.uuid4().hex[:10]}",
            action=action, severity=sev,
            remaining_budget=remaining_before,
            allowed=allowed, remaining_after=self._budget, reason=reason,
        )
        self._decisions.append(decision)
        self._persist(decision)
        return decision

    def remaining(self) -> float:
        self._replenish()
        return round(self._budget, 4)

    def total_drawn(self) -> float:
        return round(self._total_drawn, 4)

    def decisions(self, limit: int = 100) -> list[RiskBudgetDecision]:
        return list(self._decisions[-limit:])
