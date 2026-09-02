"""
SONIC-REDA — Autonomous Researcher Engine (Phase 12)
======================================================
Deep reasoning, hypothesis portfolios, parallel tracks, anomaly detection,
dead-end avoidance, and long-horizon research management.
"""

from sonic.researcher.anomaly_engine import AnomalyDetector, DeadEndDetector, NoveltyEngine
from sonic.researcher.benchmark import BenchmarkMetrics, ResearcherBenchmarkSuite
from sonic.researcher.manager import ResearchManager
from sonic.researcher.memory import PlaybookEntry, PrivateTenantMemory, ResearchMemoryStore
from sonic.researcher.models import (
    AnomalyRecord,
    AnomalyType,
    HypothesisPortfolio,
    InvestigationTrack,
    ResearcherHypothesis,
    ResearcherHypothesisStatus,
    ResearchLead,
    ResearchLeadStatus,
    ResearchMode,
    ResearchQuestion,
    ResearchQuestionStatus,
    ResearchReport,
    StopReason,
    StrategySwitchRecord,
    TrackStatus,
)
from sonic.researcher.strategy_switcher import InvestigationMethod, StrategySwitcher
from sonic.researcher.track_manager import InvestigationTrackManager, TrackPrioritizer

__all__ = [
    "ResearchQuestion",
    "ResearchQuestionStatus",
    "ResearcherHypothesis",
    "ResearcherHypothesisStatus",
    "HypothesisPortfolio",
    "InvestigationTrack",
    "TrackStatus",
    "ResearchLead",
    "ResearchLeadStatus",
    "AnomalyRecord",
    "AnomalyType",
    "StrategySwitchRecord",
    "ResearchReport",
    "StopReason",
    "ResearchMode",
    "TrackPrioritizer",
    "InvestigationTrackManager",
    "AnomalyDetector",
    "NoveltyEngine",
    "DeadEndDetector",
    "InvestigationMethod",
    "StrategySwitcher",
    "ResearchMemoryStore",
    "PrivateTenantMemory",
    "PlaybookEntry",
    "ResearchManager",
    "ResearcherBenchmarkSuite",
    "BenchmarkMetrics",
]
