"""
Tests for Phase 16: Static Anti-Scripting & Integrity Audit (Test 7).
"""

import pytest
from sonic.autonomy.anti_scripting_verifier import AntiScriptingVerifier


def test_anti_scripting_static_code_audit():
    result = AntiScriptingVerifier.audit_directory("sonic")

    assert result.files_audited >= 30
    assert result.is_autonomous_and_unscripted is True
    assert len(result.hardcoded_task_lookups) == 0
    assert len(result.bypass_flags_found) == 0
