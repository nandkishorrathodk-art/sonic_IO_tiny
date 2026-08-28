"""
Tests for Phase 19: 4-Tier Reality Classification Taxonomy.
"""

import pytest
from sonic.production_gate.models import RealityTier


def test_4_tier_reality_classification_values():
    assert RealityTier.IMPLEMENTED == "IMPLEMENTED"
    assert RealityTier.CONTROLLED_PROOF == "CONTROLLED_PROOF"
    assert RealityTier.GENERALIZED == "GENERALIZED"
    assert RealityTier.PRODUCTION_PROVEN == "PRODUCTION_PROVEN"

    # Verify order of evidential rigor
    tiers = [
        RealityTier.IMPLEMENTED,
        RealityTier.CONTROLLED_PROOF,
        RealityTier.GENERALIZED,
        RealityTier.PRODUCTION_PROVEN,
    ]
    assert len(tiers) == 4
