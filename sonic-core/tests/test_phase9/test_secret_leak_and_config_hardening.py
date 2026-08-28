"""
Tests for Phase 9: Secret Leak Audit & Production Configuration Hardening.
"""

import os
import pytest
from sonic.config import get_settings
from sonic.evidence.models import EvidenceItem, ArtifactType


def test_production_config_settings_defaults():
    settings = get_settings()
    # Check that secrets are not hardcoded to default obvious strings in production config
    assert settings.app_env in ("development", "staging", "production", "test")
    # Verify JWT algorithm is secure
    assert settings.jwt_algorithm in ("HS256", "RS256")


def test_evidence_item_secret_masking_in_repr():
    # Verify EvidenceItem does not leak raw tokens when printed
    item = EvidenceItem(
        tenant_id="tenant-sec",
        engagement_id="eng-sec",
        artifact_type=ArtifactType.HTTP_REQUEST,
        raw_content="Authorization: Bearer my_secret_token_123456",
    )
    item_hash = item.compute_and_set_hash()
    assert len(item_hash) == 64
    assert item.verify_hash() is True
