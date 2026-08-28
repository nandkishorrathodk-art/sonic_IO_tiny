"""
Tests for Phase 19: Post-Hoc Temporal Holdout Anti-Leakage Protocol.
"""

import pytest
from sonic.production_gate.models import RealityTier, TemporalHoldoutEvaluation
from sonic.production_gate.temporal_holdout_generator import TemporalHoldoutGenerator


def test_temporal_post_hoc_holdout_protocol():
    eval_res = TemporalHoldoutGenerator.evaluate_temporal_holdout_transfer()

    assert isinstance(eval_res, TemporalHoldoutEvaluation)
    assert eval_res.success is True
    assert eval_res.task_b_generated_post_hoc is True
    assert eval_res.v2_holdout_f1 > eval_res.v1_baseline_f1
    assert eval_res.empirical_generalization_gain >= 0.30
    assert eval_res.reality_tier == RealityTier.GENERALIZED
    assert eval_res.v2_promoted_version == "v2.0.0"
