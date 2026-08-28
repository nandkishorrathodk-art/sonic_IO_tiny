"""
SONIC-REDA — Open-World Generalization & Self-Development Metrics (Phase 17)
=============================================================================
Defines quantitative evaluation metrics for procedural open-world tasks,
epistemic humility discovery, and autonomous self-development velocity.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OpenWorldMetrics(BaseModel):
    """Quantitative metrics for open-world tasks and continuous self-development."""
    tasks_attempted: int = 0
    tasks_succeeded: int = 0
    zero_shot_accuracy: float = 0.0
    transfer_accuracy: float = 0.0
    transfer_gain: float = 0.0
    epistemic_humility_score: float = 1.0       # Correctly recognizes "I don't know"
    self_dev_cycles_completed: int = 0
    self_dev_velocity_seconds: float = 0.0
    security_regressions: int = 0               # Mandatory 0
    is_generalization_certified: bool = True
