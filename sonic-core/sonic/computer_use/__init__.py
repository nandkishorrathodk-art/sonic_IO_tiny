"""
SONIC-REDA — Autonomous Computer-Use Engine (Phase 14)
======================================================
Unified exports for Phase 14 Autonomous Computer-Using Engineer.
"""

from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.benchmark import MultiTrialBenchmarkSuite, MultiTrialResult
from sonic.computer_use.grounding import crop_toolbar_region, map_crop_to_screen
from sonic.computer_use.models import (
    ActionExecutionStatus,
    ComputerActionPlan,
    ComputerActionType,
    ComputerAutonomyLevel,
    ComputerDecisionTrace,
    ComputerUseMetrics,
    ComputerWorldObservation,
    EngineeringMissionMode,
)
from sonic.computer_use.motor import MotorReflexes
from sonic.computer_use.scratchpad import HackerScratchpad
from sonic.computer_use.wire_telemetry import WireTelemetryEngine

__all__ = [
    "ActionExecutionStatus",
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
    "MotorReflexes",
    "HackerScratchpad",
    "WireTelemetryEngine",
    "crop_toolbar_region",
    "map_crop_to_screen",
]

