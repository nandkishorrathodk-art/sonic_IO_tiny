"""
SONIC-REDA — Autonomous Self-Evolution Engine (Phase 8)
=========================================================
Controlled self-evolution: failure mining, improvement hypotheses, isolated lab sandbox,
baseline comparison, strict promotion gates, canary deployment, automatic rollback, and evolution memory.
"""

from sonic.evolution.models import (
    CandidateMetrics,
    EvolutionCandidate,
    EvolutionMemoryItem,
    EvolutionPolicy,
    EvolutionState,
    FailureCategory,
    FailurePattern,
    ImprovementHypothesis,
)
from sonic.evolution.failure_miner import FailureMiner
from sonic.evolution.candidate_generator import CandidateGenerator
from sonic.evolution.lab import EvolutionLab, TestPipelineResult
from sonic.evolution.comparator import BaselineComparator, ComparisonReport
from sonic.evolution.promotion import PromotionEngine, CanaryManager, RollbackManager
from sonic.evolution.memory import EvolutionMemoryStore
from sonic.evolution.domain_skills import DomainSkill, DomainSkillManager, ModelRoutingPolicy
from sonic.evolution.benchmark import (
    GenerationSnapshot,
    MultiGenerationEvolutionRunner,
    MultiGenerationReport,
)

__all__ = [
    "EvolutionState",
    "FailureCategory",
    "EvolutionPolicy",
    "FailurePattern",
    "ImprovementHypothesis",
    "EvolutionCandidate",
    "CandidateMetrics",
    "EvolutionMemoryItem",
    "FailureMiner",
    "CandidateGenerator",
    "EvolutionLab",
    "TestPipelineResult",
    "BaselineComparator",
    "ComparisonReport",
    "PromotionEngine",
    "CanaryManager",
    "RollbackManager",
    "EvolutionMemoryStore",
    "DomainSkill",
    "DomainSkillManager",
    "ModelRoutingPolicy",
    "GenerationSnapshot",
    "MultiGenerationEvolutionRunner",
    "MultiGenerationReport",
]
