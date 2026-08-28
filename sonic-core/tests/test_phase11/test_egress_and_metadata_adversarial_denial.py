"""
Tests for Phase 11: Egress & Metadata Adversarial Denial Verification.
"""

import pytest
from sonic.sandbox.egress import is_target_allowed


def test_adversarial_ssrf_and_metadata_denial():
    adversarial_targets = [
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.169.254/computeMetadata/v1/",
        "http://127.0.0.1:8000/api",
        "http://localhost:5432",
        "http://10.0.0.1/admin",
        "http://172.16.0.1/secret",
        "http://192.168.1.1/router",
        "http://[::1]:8080",
    ]

    for target in adversarial_targets:
        allowed, reason = is_target_allowed(target)
        assert allowed is False, f"Target '{target}' should have been DENIED by egress filter!"
        assert "blocked" in reason.lower()
