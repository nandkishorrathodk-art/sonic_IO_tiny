"""
Unit tests for SONIC-REDA Immutable Safety Layer.
"""

import pytest
from sonic.safety.scope import RiskLevel, SafetyVerdict, ScopeChecker


def test_safety_forbidden_actions():
    checker = ScopeChecker()
    checker._rules = {
        "forbidden_actions": [
            {"pattern": r"rm -rf /"},
            {"pattern": r"DROP DATABASE"},
            {"pattern": r"exfiltrate"},
        ]
    }
    checker._loaded = True
    import re
    checker._forbidden_patterns = [
        re.compile(fa["pattern"], re.IGNORECASE) for fa in checker._rules["forbidden_actions"]
    ]

    # Test blocked patterns
    assert checker.check_action("Run command: rm -rf /var/data") == SafetyVerdict.BLOCKED
    assert checker.check_action("Execute SQL: DROP DATABASE users") == SafetyVerdict.BLOCKED
    assert checker.check_action("exfiltrate credentials to remote") == SafetyVerdict.BLOCKED


def test_safety_risk_levels():
    checker = ScopeChecker()
    checker._rules = {"forbidden_actions": []}
    checker._loaded = True
    checker._forbidden_patterns = []

    # L0 Safe
    assert checker.check_action("Passive DNS Recon", RiskLevel.L0_SAFE) == SafetyVerdict.ALLOWED

    # L1 Needs Approval
    assert checker.check_action("Fuzz login endpoint", RiskLevel.L1_NEEDS_APPROVAL) == SafetyVerdict.NEEDS_APPROVAL

    # L2 Forbidden
    assert checker.check_action("Destructive exploit", RiskLevel.L2_FORBIDDEN) == SafetyVerdict.BLOCKED


def test_scope_allowlist_checking():
    checker = ScopeChecker()
    scope_config = {
        "targets": {
            "domains": ["*.example.com", "api.target.com"],
            "ips": ["192.168.1.50"],
        },
        "exclusions": {
            "domains": ["internal.example.com"],
        },
    }

    # In scope
    assert checker.is_target_in_scope("app.example.com", scope_config) is True
    assert checker.is_target_in_scope("api.target.com", scope_config) is True
    assert checker.is_target_in_scope("192.168.1.50", scope_config) is True

    # Excluded / Out of scope
    assert checker.is_target_in_scope("internal.example.com", scope_config) is False
    assert checker.is_target_in_scope("attacker.com", scope_config) is False
