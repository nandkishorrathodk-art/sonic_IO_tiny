"""
SONIC-REDA — Autonomous Researcher Engine (Phase 12)
======================================================
Deep reasoning, hypothesis portfolios, parallel tracks, anomaly detection,
dead-end avoidance, and long-horizon research management.
"""

from sonic.researcher.models import (
    ResearchQuestion,
    ResearchQuestionStatus,
    ResearcherHypothesis,
    ResearcherHypothesisStatus,
    HypothesisPortfolio,
    InvestigationTrack,
    TrackStatus,
    ResearchLead,
    ResearchLeadStatus,
    AnomalyRecord,
    AnomalyType,
    StrategySwitchRecord,
    ResearchReport,
    StopReason,
    ResearchMode,
)
from sonic.researcher.track_manager import TrackPrioritizer, InvestigationTrackManager
from sonic.researcher.anomaly_engine import AnomalyDetector, NoveltyEngine, DeadEndDetector
from sonic.researcher.strategy_switcher import InvestigationMethod, StrategySwitcher
from sonic.researcher.memory import ResearchMemoryStore, PrivateTenantMemory, PlaybookEntry
from sonic.researcher.manager import ResearchManager
from sonic.researcher.benchmark import ResearcherBenchmarkSuite, BenchmarkMetrics

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
