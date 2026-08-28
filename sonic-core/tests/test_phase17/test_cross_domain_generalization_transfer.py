"""
Tests for Phase 17: Cross-Domain Generalization & Quantitative Transfer Metrics.
"""

import pytest
from sonic.open_world.metrics import OpenWorldMetrics


def test_cross_domain_generalization_metrics():
    metrics = OpenWorldMetrics(
        tasks_attempted=10,
        tasks_succeeded=9,
        zero_shot_accuracy=0.80,
        transfer_accuracy=0.90,
        transfer_gain=0.10,
        epistemic_humility_score=1.0,
        self_dev_cycles_completed=3,
        self_dev_velocity_seconds=42.5,
        security_regressions=0,
        is_generalization_certified=True,
    )

    assert metrics.tasks_succeeded == 9
    assert metrics.security_regressions == 0
    assert metrics.transfer_gain > 0.0
    assert metrics.epistemic_humility_score == 1.0
    assert metrics.is_generalization_certified is True
