"""Neutral research primitives for ordinary computer-use tasks.

Security-specialist orchestration is intentionally outside the foundation
surface. This package exposes only uncertainty, planning, and observation
helpers that can support general research work.
"""

from sonic.research.decision_trace import DecisionTrace
from sonic.research.epistemic import CompetingHypothesis, Prediction, Unknown
from sonic.research.failure_budget import FailureBudgetTracker
from sonic.research.failure_classifier import classify_failure
from sonic.research.information_gain import ActionCandidate

__all__ = [
    "ActionCandidate",
    "CompetingHypothesis",
    "DecisionTrace",
    "FailureBudgetTracker",
    "Prediction",
    "Unknown",
    "classify_failure",
]
