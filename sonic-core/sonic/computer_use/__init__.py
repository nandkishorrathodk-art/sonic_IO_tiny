"""
SONIC-REDA — Autonomous Computer-Use Engine (Phase 14)
======================================================
Unified exports for Phase 14 Autonomous Computer-Using Engineer.
"""

from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.benchmark import BenchmarkResult, MultiTrialBenchmarkSuite, TrialSample
from sonic.computer_use.fast_deep import FastDeepController, PreparedAction, ReasoningMode
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
from sonic.computer_use.perception_bus import (
    ActionFuture,
    PerceptionBus,
    PerceptionChange,
    PerceptionSnapshot,
    TargetMatch,
)
from sonic.computer_use.reflex_executor import ReflexExecutor
from sonic.computer_use.scratchpad import HackerScratchpad
from sonic.computer_use.skill_ledger import ComputerSkillLedger
from sonic.computer_use.wire_telemetry import WireTelemetryEngine

from .perception_adapters import (
    BrowserPerceptionAdapter,
    ComputerPerceptionAdapter,
    DockerContainerEventSource,
    StructuredPerceptionEventAdapter,
)

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
    "BenchmarkResult",
    "TrialSample",
    "MotorReflexes",
    "ActionFuture",
    "PerceptionBus",
    "PerceptionChange",
    "PerceptionSnapshot",
    "TargetMatch",
    "ComputerPerceptionAdapter",
    "BrowserPerceptionAdapter",
    "StructuredPerceptionEventAdapter",
    "DockerContainerEventSource",
    "ReflexExecutor",
    "FastDeepController",
    "PreparedAction",
    "ReasoningMode",
    "ComputerSkillLedger",
    "HackerScratchpad",
    "WireTelemetryEngine",
    "crop_toolbar_region",
    "map_crop_to_screen",
]
