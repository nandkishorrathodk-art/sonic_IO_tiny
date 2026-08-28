"""
SONIC-REDA — Autonomous Computer-Use Engine (Phase 14)
======================================================
Unified exports for Phase 14 Autonomous Computer-Using Engineer.
"""

from sonic.computer_use.models import (
    ComputerWorldObservation,
    ComputerActionPlan,
    ComputerDecisionTrace,
    ComputerAutonomyLevel,
    EngineeringMissionMode,
    ComputerActionType,
    ComputerUseMetrics,
)
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.benchmark import MultiTrialBenchmarkSuite, MultiTrialResult

__all__ = [
    "ComputerWorldObservation",
    "ComputerActionPlan",
    "ComputerDecisionTrace",
    "ComputerAutonomyLevel",
    "EngineeringMissionMode",
    "ComputerActionType",
    "ComputerUseMetrics",
    "ComputerUseAgent",
    "MultiTrialBenchmarkSuite",
    "MultiTrialResult",
]
