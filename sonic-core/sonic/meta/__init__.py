"""
SONIC-REDA — Meta / Self-Development Module
=============================================
Autonomous experiment management, benchmark testing, and safe evolution.
"""

from sonic.meta.benchmark import BenchmarkLab, BenchmarkResult, ChallengeFixture
from sonic.meta.canary import CanaryPipeline
from sonic.meta.changelog import EvolutionChangelog
from sonic.meta.evaluator import Decision, EvaluationReport, SelfEvaluationEngine
from sonic.meta.experiment import (
    ExperimentManager,
    ExperimentProposal,
    ExperimentStatus,
    ExperimentType,
)

__all__ = [
    "ExperimentManager",
    "ExperimentProposal",
    "ExperimentStatus",
    "ExperimentType",
    "BenchmarkLab",
    "BenchmarkResult",
    "ChallengeFixture",
    "SelfEvaluationEngine",
    "Decision",
    "EvaluationReport",
    "CanaryPipeline",
    "EvolutionChangelog",
]
