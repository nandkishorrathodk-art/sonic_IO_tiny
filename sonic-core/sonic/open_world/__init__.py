"""
SONIC-REDA — Open-World Generalization & Continuous Self-Development Package (Phase 17)
=======================================================================================
Unified exports for Phase 17 Open-World Generalization.
"""

from sonic.open_world.metrics import OpenWorldMetrics
from sonic.open_world.novelty_generator import ProceduralNoveltyGenerator, ProceduralRepoTask
from sonic.open_world.limitation_discovery import LimitationDiscoveryEngine, LimitationDiscoveryResult
from sonic.open_world.self_development_orchestrator import SelfDevelopmentOrchestrator, SelfDevelopmentPR

__all__ = [
    "OpenWorldMetrics",
    "ProceduralNoveltyGenerator",
    "ProceduralRepoTask",
    "LimitationDiscoveryEngine",
    "LimitationDiscoveryResult",
    "SelfDevelopmentOrchestrator",
    "SelfDevelopmentPR",
]
