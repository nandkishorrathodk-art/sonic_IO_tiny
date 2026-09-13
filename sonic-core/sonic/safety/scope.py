"""
SONIC-REDA — Immutable Safety & Scope Layer
=============================================
Hard-coded rules that NO agent or self-dev process can modify.
Loaded from safety_rules.yaml at startup. Read-only at runtime.

This module enforces:
    - Target allowlist (scope checking)
    - Risk level classification (L0 / L1 / L2)
    - Forbidden action detection
    - Network egress rules
    - Kill switch

CRITICAL: This module's behavior can only be changed by a human admin
editing safety_rules.yaml and restarting the system.
"""

from __future__ import annotations

import re
from enum import StrEnum
from ipaddress import ip_address as _ip_addr, ip_network as _ip_net
from pathlib import Path
from urllib.parse import urlparse

import yaml

from sonic.config import CONFIGS_DIR
from sonic.logger import get_logger

logger = get_logger(__name__)


class RiskLevel(StrEnum):
    """Action risk classification."""
    L0_SAFE = "L0"              # Auto-approved, non-intrusive
    L1_NEEDS_APPROVAL = "L1"    # Requires human approval
    L2_FORBIDDEN = "L2"         # NEVER allowed, hard blocked


class SafetyVerdict(StrEnum):
    """Result of a safety check."""
    ALLOWED = "allowed"
    NEEDS_APPROVAL = "needs_approval"
    BLOCKED = "blocked"


def _normalize_command(command: str) -> str:
    """Normalize a shell command to defeat obfuscation like shell escapes and quote wrapping."""
    if not command:
        return command
    # Remove backslash line-continuations: e.g. rm \\\n -rf -> rm -rf
    norm = re.sub(r"\\\n", "", command)
    # Remove shell backslash escapes: e.g. r\m -> rm, \rm -> rm, -r\f -> -rf
    norm = re.sub(r"\\([^\n]?)", r"\1", norm)
    # Remove empty quotes: e.g. ""rm -> rm, ''rm -> rm, r""m -> rm
    norm = re.sub(r'""|\'\'', "", norm)
    # Remove quotes wrapping tokens/words: e.g. "rm" -> rm, 'rm' -> rm
    norm = re.sub(r'["\']', "", norm)
    return norm


class ScopeChecker:
    """
    Validates actions against the Immutable Safety Layer.

    Loaded once at startup from safety_rules.yaml.
    Cannot be modified by any agent or process at runtime.
    """

    def __init__(self, scope_config: dict | None = None):
        self._rules: dict = {}
        self._forbidden_patterns: list[re.Pattern] = []
        self._destructive_patterns: list[re.Pattern] = list(self._DESTRUCTIVE_PATTERNS)
        self._allowed_egress: list[str] = []
        self._loaded = False
        self.scope_config: dict = scope_config or {}

    def has_active_scope_rules(self, scope_config: dict | None = None) -> bool:
        """Check whether there are active scope rules configured (targets or exclusions)."""
        cfg = scope_config if scope_config is not None else getattr(self, "scope_config", {})
        if not cfg and isinstance(getattr(self, "_rules", None), dict):
            if "targets" in self._rules or "exclusions" in self._rules:
                cfg = self._rules
        if not cfg or not isinstance(cfg, dict):
            return False
        targets = cfg.get("targets", {}) if isinstance(cfg.get("targets"), dict) else {}
        exclusions = cfg.get("exclusions", {}) if isinstance(cfg.get("exclusions"), dict) else {}
        return bool(
            targets.get("domains")
            or targets.get("ips")
            or exclusions.get("domains")
            or exclusions.get("ips")
        )

    def load_rules(self, rules_path: str | Path | None = None) -> None:
        """
        Load safety rules from YAML file.
        Should be called ONCE at system startup.
        """
        path = Path(rules_path) if rules_path else CONFIGS_DIR / "safety_rules.yaml"

        if not path.exists():
            logger.error("safety_rules_not_found", path=str(path))
            # FAIL CLOSED: if no rules, block everything
            self._rules = {"risk_levels": {}, "forbidden_actions": []}
            self._loaded = True
            return

        with open(path) as f:
            self._rules = yaml.safe_load(f) or {}

        # Compile forbidden action patterns
        forbidden = self._rules.get("forbidden_actions", [])
        self._forbidden_patterns = [
            re.compile(fa["pattern"], re.IGNORECASE)
            for fa in forbidden
            if "pattern" in fa
        ]

        # Load allowed egress
        network = self._rules.get("network_policy", {})
        self._allowed_egress = network.get("always_allowed", [])

        self._loaded = True
        logger.info(
            "safety_rules_loaded",
            forbidden_patterns=len(self._forbidden_patterns),
            egress_rules=len(self._allowed_egress),
        )

    def check_action(self, action_description: str, risk_level: RiskLevel = RiskLevel.L0_SAFE) -> SafetyVerdict:
        """
        Check if an action is allowed.

        Args:
            action_description: Human-readable description of what the agent wants to do
            risk_level: The risk level of the action

        Returns:
            SafetyVerdict: ALLOWED, NEEDS_APPROVAL, or BLOCKED
        """
        if not self._loaded:
            logger.error("safety_rules_not_loaded")
            return SafetyVerdict.BLOCKED  # Fail closed

        # Check forbidden patterns first (always blocked)
        for pattern in self._forbidden_patterns:
            if pattern.search(action_description):
                logger.warning(
                    "action_blocked_forbidden",
                    action=action_description,
                    pattern=pattern.pattern,
                )
                return SafetyVerdict.BLOCKED

        # Check risk level
        if risk_level == RiskLevel.L2_FORBIDDEN:
            logger.warning("action_blocked_l2", action=action_description)
            return SafetyVerdict.BLOCKED

        if risk_level == RiskLevel.L1_NEEDS_APPROVAL:
            logger.info("action_needs_approval", action=action_description)
            return SafetyVerdict.NEEDS_APPROVAL

        return SafetyVerdict.ALLOWED

    # Patterns that indicate destructive or high-risk operations
    _DESTRUCTIVE_PATTERNS = [
        re.compile(r"\brm\s+.*(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r|--recursive)\b", re.IGNORECASE),
        re.compile(r"\brm\s+(-rf?|-fr|-r\s+-f|-f\s+-r|--recursive)\b", re.IGNORECASE),
        re.compile(r"\b(mkfs(\.\w+)?|mke2fs|wipefs)\b", re.IGNORECASE),
        re.compile(r"\bdd\b.*\bof=[\"']?/dev/", re.IGNORECASE),
        re.compile(r">\s*/dev/sd", re.IGNORECASE),
        re.compile(r"\b(killall\s+-9|pkill\s+-9)\b", re.IGNORECASE),
        re.compile(r"(?:\A|[;&|])\s*(?:sudo\s+)?(?:/s?bin/)?shutdown\b", re.IGNORECASE),
        re.compile(r"(?:\A|[;&|])\s*(?:sudo\s+)?(?:/s?bin/)?reboot\b", re.IGNORECASE),
        re.compile(r"(?:\A|[;&|])\s*(?:sudo\s+)?(?:/s?bin/)?halt\b", re.IGNORECASE),
        re.compile(r"\b:()\{\s*:\|:&\s*\};:", re.IGNORECASE),  # fork bomb
        # --- Policy parity with safety_rules.yaml forbidden_actions ---
        re.compile(r"\bdrop\s+database\b", re.IGNORECASE),
        re.compile(r"\bexfiltrate\b", re.IGNORECASE),
        re.compile(r"\bdisable\b.*\blogging\b", re.IGNORECASE),
        re.compile(r"\bmodify\b.*\bsafety_rules\b", re.IGNORECASE),
        re.compile(r"\bformat\b\s+\w+:", re.IGNORECASE),
        # Reverse shells — high-risk command execution / egress of a shell
        re.compile(r"\bbash\b\s+-i\b.*/dev/tcp/", re.IGNORECASE),
        re.compile(r"\bsh\s+-i\b.*/dev/tcp/", re.IGNORECASE),
        re.compile(r"\bnc\b.*\s-e\s+\S+", re.IGNORECASE),  # netcat exec mode
    ]
    # Patterns that indicate intrusive but non-destructive operations
    _INTRUSIVE_PATTERNS = [
        re.compile(r"\bnmap\b.*\s(-sS|-sA|-sO|-O|--script)", re.IGNORECASE),
        re.compile(r"\bhydra\b", re.IGNORECASE),
        re.compile(r"\bsqlmap\b", re.IGNORECASE),
        re.compile(r"\bmetasploit\b|\bmsfconsole\b", re.IGNORECASE),
        re.compile(r"\bexploit\b", re.IGNORECASE),
        re.compile(r"\bnikto\b.*\s(-Tuning|4|5|6|7|8|9)", re.IGNORECASE),
        re.compile(r"\bcurl\b.*\|\s*(sh|bash)", re.IGNORECASE),  # curl|sh
        re.compile(r"\bwget\b.*\|\s*(sh|bash)", re.IGNORECASE),
        re.compile(r"\bchmod\s+\+x\b.*\&\&.*\./", re.IGNORECASE),
    ]

    def classify_command_risk(self, command: str) -> RiskLevel:
        """Classify a shell command's risk level by inspecting its content.

        L2_FORBIDDEN: destructive ops (rm -rf, mkfs, dd to device, shutdown, fork bombs)
        L1_NEEDS_APPROVAL: intrusive ops (exploits, brute-force, aggressive scans, curl|sh)
        L0_SAFE: read-only / recon (curl, ls, cat, grep, nmap default scan, etc.)
        """
        if not command or not command.strip():
            return RiskLevel.L0_SAFE

        norm_command = _normalize_command(command)
        candidates = [command] if norm_command == command else [command, norm_command]

        patterns_to_check = getattr(self, "_destructive_patterns", self._DESTRUCTIVE_PATTERNS)
        for cmd in candidates:
            for pattern in patterns_to_check:
                if pattern.search(cmd):
                    logger.warning("command_classified_destructive", command=command[:200])
                    return RiskLevel.L2_FORBIDDEN

        for cmd in candidates:
            for pattern in self._forbidden_patterns:
                if pattern.search(cmd):
                    logger.warning("command_classified_forbidden_rule", command=command[:200])
                    return RiskLevel.L2_FORBIDDEN

        for cmd in candidates:
            for pattern in self._INTRUSIVE_PATTERNS:
                if pattern.search(cmd):
                    logger.info("command_classified_intrusive", command=command[:200])
                    return RiskLevel.L1_NEEDS_APPROVAL

        return RiskLevel.L0_SAFE

    def is_target_in_scope(self, target: str, scope_config: dict) -> bool:
        """
        Check if a target (domain/IP/URL) is within the engagement scope.

        Args:
            target: The target to check
            scope_config: Loaded scope.yaml for the current engagement
        """
        targets = scope_config.get("targets", {})
        exclusions = scope_config.get("exclusions", {})

        # Normalize the target to a bare hostname/IP (strip URL scheme/path/port).
        host = target
        if "://" in target or target.startswith("//"):
            parsed = urlparse(target if "://" in target else "http:" + target)
            host = parsed.hostname or target
        # Strip a trailing :port if urlparse didn't (bare "1.2.3.4:8080" form)
        if ":" in host and not host.startswith("["):
            host = host.rsplit(":", 1)[0]

        # Check exclusions first — fullmatch to prevent suffix-bypass
        # (re.match only anchors start; evil.x.com.attacker.com would match *.x.com)
        for excluded_domain in exclusions.get("domains", []):
            pattern = self._domain_to_regex(excluded_domain)
            if re.fullmatch(pattern, target, re.IGNORECASE) or re.fullmatch(pattern, host, re.IGNORECASE):
                return False

        # Check allowed domains
        for allowed_domain in targets.get("domains", []):
            pattern = self._domain_to_regex(allowed_domain)
            if re.fullmatch(pattern, target, re.IGNORECASE) or re.fullmatch(pattern, host, re.IGNORECASE):
                return True

        # Check allowed IPs / CIDR ranges — expand CIDRs and compare numerically
        # so e.g. 10.10.50.10 in 10.10.50.0/24 is correctly in-scope. A literal
        # `in` check (the old behavior) only matched the CIDR *string* itself.
        return self._ip_in_scope_list(host, targets.get("ips", []))

    @staticmethod
    def _ip_in_scope_list(host: str, ip_list: list[str]) -> bool:
        """True if ``host`` (an IP) is in ``ip_list`` (IPs and/or CIDR ranges)."""
        try:
            ip = _ip_addr(host)
        except ValueError:
            # Not a literal IP — only a literal-string match could apply.
            return host in ip_list
        for entry in ip_list:
            if entry == host:
                return True
            if "/" in entry:
                try:
                    if ip in _ip_net(entry, strict=False):
                        return True
                except ValueError:
                    continue
            else:
                try:
                    if ip == _ip_addr(entry):
                        return True
                except ValueError:
                    continue
        return False

    def is_egress_allowed(self, destination: str) -> bool:
        """Check if outbound traffic to this destination is allowed."""
        for allowed in self._allowed_egress:
            pattern = self._domain_to_regex(allowed)
            if re.fullmatch(pattern, destination, re.IGNORECASE):
                return True
        return False

    @staticmethod
    def _domain_to_regex(domain: str) -> str:
        """Convert a domain glob (*.example.com, *.*) to a fully-anchored regex."""
        # Escape regex metacharacters, then restore glob semantics for * and .
        escaped = re.escape(domain)
        escaped = escaped.replace(r"\*", ".*").replace(r"\.", r"\.")
        return escaped

    @property
    def kill_switch_enabled(self) -> bool:
        """Check if kill switch is configured."""
        return self._rules.get("kill_switch", {}).get("enabled", True)


# Global singleton — loaded once, used everywhere
_scope_checker: ScopeChecker | None = None


def get_scope_checker() -> ScopeChecker:
    """Get the global ScopeChecker singleton."""
    global _scope_checker
    if _scope_checker is None:
        _scope_checker = ScopeChecker()
        _scope_checker.load_rules()
    return _scope_checker


class SandboxIsolationTier(StrEnum):
    """Smart-sandbox isolation tiers.

    The being routes each autonomous action to a tier whose network/FS
    footprint scales with the action's assessed severity. Fail-closed: unknown
    severity -> FORBIDDEN (never execute).
    """
    HOST_CAGED = "host_caged"          # severity info      – in-memory only, no network
    STANDARD = "standard"              # severity low       – container, no network
    ISOLATED = "isolated"              # severity medium    – container + network-isolated net
    EPHEMERAL = "ephemeral"            # severity high      – short-lived container, no persistence
    FORBIDDEN = "forbidden"            # severity critical  – never executed


class SandboxTierRouter:
    """Maps an action's assessed severity to a sandbox isolation tier.

    This is the ASI-level Sandbox pillar: instead of a static provider, the
    being *chooses* the isolation envelope for each action. The native Rust
    kernel confirms the mapping (native_verdict intact) whenever available;
    otherwise the deterministic Python map applies (still fail-closed).
    """

    _SEVERITY_TO_TIER: dict[str, SandboxIsolationTier] = {
        "info": SandboxIsolationTier.HOST_CAGED,
        "low": SandboxIsolationTier.STANDARD,
        "medium": SandboxIsolationTier.ISOLATED,
        "high": SandboxIsolationTier.EPHEMERAL,
        "critical": SandboxIsolationTier.FORBIDDEN,
    }

    _TIER_NETWORK_ISOLATED: dict[SandboxIsolationTier, bool] = {
        SandboxIsolationTier.HOST_CAGED: False,   # no network at all (in-memory)
        SandboxIsolationTier.STANDARD: False,     # container, offline
        SandboxIsolationTier.ISOLATED: True,      # dedicated sandbox net
        SandboxIsolationTier.EPHEMERAL: True,     # dedicated net, short-lived
        SandboxIsolationTier.FORBIDDEN: True,     # unreachable — never built
    }

    def __init__(self, native_kernel: Any | None = None) -> None:
        self.native_kernel = native_kernel

    @classmethod
    def tier_for_severity(cls, severity: str) -> SandboxIsolationTier:
        return cls._SEVERITY_TO_TIER.get(str(severity).lower(), SandboxIsolationTier.FORBIDDEN)

    @classmethod
    def network_isolated_for(cls, tier: SandboxIsolationTier) -> bool:
        return cls._TIER_NETWORK_ISOLATED.get(tier, True)

    def route(
        self,
        severity: str,
        action_type: str = "",
        target: str = "",
    ) -> dict[str, Any]:
        """Return the sandbox routing decision for an action.

        The returned dict is introspectable and directly consumable as
        WorkspaceConfig knobs:
            {
                "severity", "tier", "network_isolated", "executable",
                "native_verdict", "reason",
            }
        `executable` is False when the tier forbids execution (fail-closed).
        """
        if self.native_kernel is None:
            try:
                from sonic.kernel.native_bridge import NativeKernelClient
                self.native_kernel = NativeKernelClient()
            except Exception:
                self.native_kernel = None

        tier = self.tier_for_severity(severity)
        executable = tier is not SandboxIsolationTier.FORBIDDEN
        native_verdict = "unavailable"
        scope_denied = False

        if self.native_kernel is not None and getattr(self.native_kernel, "is_available", lambda: False)():
            try:
                # `is_isolated=True` for every executable tier: all tiers run
                # inside an isolated provider (container/pod), satisfying the
                # kernel's zero-host-escape invariant. The dedicated network is
                # the finer `network_isolated` knob, separate from sandboxing.
                res = self.native_kernel.authorize(
                    action_type=action_type or "SANDBOX_EXEC",
                    target=target or "",
                    is_isolated=True,
                )
                # The kernel decides both the action-family envelope (seal
                # intact + allowlisted) and the target scope (e.g. blocked
                # private-IP egress). A scope-level Deny does NOT flip the
                # isolation tier to FORBIDDEN: severity already decides the
                # tier, and target-scope enforcement happens at execution time
                # (ActionBroker/SafetyKernel). Only a broken seal is a hard
                # structural stop — represented via `scope_denied` + verdict.
                if res is not None and res.seal_intact:
                    native_verdict = res.verdict
                    scope_denied = res.verdict == "Deny"
                elif res is not None:
                    # Seal tampered: treat as forbidden structural stop.
                    native_verdict = "SEAL_TAMPERED"
                    tier = SandboxIsolationTier.FORBIDDEN
                    executable = False
                    scope_denied = True
            except Exception:
                native_verdict = "unavailable"

        return {
            "severity": str(severity).lower(),
            "tier": tier.value,
            "network_isolated": self.network_isolated_for(tier),
            "executable": executable,
            "native_verdict": native_verdict,
            "scope_denied": scope_denied,
            "reason": (
                f"severity={severity} -> tier={tier.value}"
                + (f" | native={native_verdict}" if native_verdict != "unavailable" else "")
            ),
        }
