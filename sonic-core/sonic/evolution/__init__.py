"""SONIC v2 — Self-Evolution & Method Lab Engine."""

from sonic.evolution.codebase_evolver import CodebaseEvolver, EvolutionSummaryReport
from sonic.evolution.evolution_journal import EvolutionJournal, JournalEntry
from sonic.evolution.goal_director import (
    EvolutionGoal,
    EvolutionGoalDirector,
    GoalCategory,
    GoalStatus,
)
from sonic.evolution.pipeline import EvolutionPipeline, EvolutionStage, ImprovementProposal
from sonic.evolution.version_tracker import VersionRecord, VersionTracker

__all__ = [
    "CodebaseEvolver",
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
    "VersionRecord",
    "VersionTracker",
]
