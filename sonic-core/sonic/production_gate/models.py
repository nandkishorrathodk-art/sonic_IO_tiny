"""
SONIC-REDA — Production Autonomy & Reality Taxonomy Data Models (Phase 19)
============================================================================
Defines the permanent 4-Tier Reality Classification taxonomy,
independent evaluation manifests, and multi-domain scenario structures.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class RealityTier(str, Enum):
    """Permanent 4-Tier Reality Taxonomy."""
    IMPLEMENTED = "IMPLEMENTED"                 # Source code exists in repository
    CONTROLLED_PROOF = "CONTROLLED_PROOF"       # Verified in controlled / local environment
    GENERALIZED = "GENERALIZED"                 # Proven across unseen task distributions
    PRODUCTION_PROVEN = "PRODUCTION_PROVEN"     # Independently reproduced in live environments


class ScenarioDomain(str, Enum):
    """The 8 Architectural Scenario Domains."""
    CONCURRENCY_RACE = "CONCURRENCY_RACE"
    ASYNC_MEMORY_LEAK = "ASYNC_MEMORY_LEAK"
    CRYPTOGRAPHIC_REPLAY = "CRYPTOGRAPHIC_REPLAY"
    CONNECTION_POOLING = "CONNECTION_POOLING"
    AST_PARSER_RECURSION = "AST_PARSER_RECURSION"
    RATE_LIMITER_OFF_BY_ONE = "RATE_LIMITER_OFF_BY_ONE"
    DISTRIBUTED_DEADLOCK = "DISTRIBUTED_DEADLOCK"
    PROTOCOL_FRAMING = "PROTOCOL_FRAMING"


class ScenarioExecutionResult(BaseModel):
    """Result of an autonomous scenario investigation and remediation."""
    scenario_id: str
    domain: ScenarioDomain
    problem_description: str
    initial_failure_verified: bool
    autonomous_fix_verified: bool
    performance_delta_pct: float
    git_commit_hash: str
    reality_tier: RealityTier = RealityTier.CONTROLLED_PROOF
    success: bool


class TemporalHoldoutEvaluation(BaseModel):
    """Evaluation of post-hoc blind holdout (Task Set A -> Evolve -> Task Set B)."""
    v1_task_set_a_id: str
    v1_failure_mined: str
    v2_promoted_version: str
    v2_task_set_b_id: str
    task_b_generated_post_hoc: bool
    v1_baseline_f1: float
    v2_holdout_f1: float
    empirical_generalization_gain: float
    reality_tier: RealityTier = RealityTier.GENERALIZED
    success: bool


class IndependentEvaluationManifest(BaseModel):
    """Independent third-party reproduction evaluation manifest."""
    manifest_id: str = Field(default_factory=lambda: f"eval-{uuid.uuid4().hex[:8]}")
    evaluator_name: str = "IndependentAutomatedHarness"
    scenarios_evaluated: int
    scenarios_passed: int
    pass_rate_pct: float
    temporal_holdout_passed: bool
    overall_reality_tier: RealityTier
    is_reproducible: bool
