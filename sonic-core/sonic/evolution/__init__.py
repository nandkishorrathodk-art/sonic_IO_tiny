"""SONIC v2 — Self-Evolution & Method Lab Engine."""

from sonic.evolution.codebase_evolver import CodebaseEvolver, EvolutionSummaryReport
from sonic.evolution.engine import EvolutionEngine
from sonic.evolution.evolution_journal import EvolutionJournal, JournalEntry
from sonic.evolution.goal_director import (
    EvolutionGoal,
    EvolutionGoalDirector,
    GoalCategory,
    GoalStatus,
)
from sonic.evolution.pipeline import EvolutionPipeline, EvolutionStage, ImprovementProposal
from sonic.evolution.strategy import (
    DynamicStrategyEngine,
    StrategicPosture,
    StrategyAdaptationPlan,
    TargetFeedbackSignal,
)
from sonic.evolution.version_tracker import VersionRecord, VersionTracker

__all__ = [
    "CodebaseEvolver",
    "EvolutionEngine",
    "EvolutionGoal",
    "EvolutionGoalDirector",
    "EvolutionJournal",
    "EvolutionPipeline",
    "EvolutionStage",
    "EvolutionSummaryReport",
    "GoalCategory",
    "GoalStatus",
    "ImprovementProposal",
    "JournalEntry",
    "DynamicStrategyEngine",
    "StrategicPosture",
    "StrategyAdaptationPlan",
    "TargetFeedbackSignal",
    "VersionRecord",
    "VersionTracker",
]
