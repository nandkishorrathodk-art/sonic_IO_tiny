"""
Tests for Phase 16: Cryptographically Isolated Holdout Set (Test 5).
"""

import pytest
from sonic.autonomy.cryptographic_holdout import CryptographicHoldoutManager, HoldoutTask


def test_cryptographic_holdout_suite_integrity():
    suite = CryptographicHoldoutManager.get_sealed_holdout_suite()

    assert len(suite) == 2
    for task in suite:
        assert isinstance(task, HoldoutTask)
        assert task.is_sealed is True
        # Verify HMAC integrity
        assert CryptographicHoldoutManager.verify_holdout_integrity(task) is True

        # Tampering with fixture data must break signature
        tampered_task = task.model_copy()
        tampered_task.target_fixture_data = "tampered_code_snippet_123"
        assert CryptographicHoldoutManager.verify_holdout_integrity(tampered_task) is False
