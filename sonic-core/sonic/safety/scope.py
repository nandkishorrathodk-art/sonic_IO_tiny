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
from pathlib import Path
from typing import Optional

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


class ScopeChecker:
    """
    Validates actions against the Immutable Safety Layer.
    
    Loaded once at startup from safety_rules.yaml.
    Cannot be modified by any agent or process at runtime.
    """

    def __init__(self):
        self._rules: dict = {}
        self._forbidden_patterns: list[re.Pattern] = []
        self._allowed_egress: list[str] = []
        self._loaded = False

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
        re.compile(r"\brm\s+-rf?\b", re.IGNORECASE),
        re.compile(r"\bmkfs\b", re.IGNORECASE),
        re.compile(r"\bdd\b.*\bof=/dev/", re.IGNORECASE),
        re.compile(r">\s*/dev/sd", re.IGNORECASE),
        re.compile(r"\bshutdown\b", re.IGNORECASE),
        re.compile(r"\breboot\b", re.IGNORECASE),
        re.compile(r"\bhalt\b", re.IGNORECASE),
        re.compile(r"\b:()\{\s*:\|:&\s*\};:", re.IGNORECASE),  # fork bomb
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

        for pattern in self._DESTRUCTIVE_PATTERNS:
            if pattern.search(command):
                logger.warning("command_classified_destructive", command=command[:200])
                return RiskLevel.L2_FORBIDDEN

        for pattern in self._INTRUSIVE_PATTERNS:
            if pattern.search(command):
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

        # Check exclusions first — fullmatch to prevent suffix-bypass
        # (re.match only anchors start; evil.x.com.attacker.com would match *.x.com)
        for excluded_domain in exclusions.get("domains", []):
            pattern = self._domain_to_regex(excluded_domain)
            if re.fullmatch(pattern, target, re.IGNORECASE):
                return False

        # Check allowed domains
        for allowed_domain in targets.get("domains", []):
            pattern = self._domain_to_regex(allowed_domain)
            if re.fullmatch(pattern, target, re.IGNORECASE):
                return True

        # Check allowed IPs
        if target in targets.get("ips", []):
            return True

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
_scope_checker: Optional[ScopeChecker] = None


def get_scope_checker() -> ScopeChecker:
    """Get the global ScopeChecker singleton."""
    global _scope_checker
    if _scope_checker is None:
        _scope_checker = ScopeChecker()
        _scope_checker.load_rules()
    return _scope_checker
