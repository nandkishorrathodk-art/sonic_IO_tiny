"""
SONIC-REDA — Research & Critical Thinking Engine (Phase 6)
============================================================
Scientific investigation substrate for autonomous security research:
    - Epistemic uncertainty & competing hypotheses
    - Prediction-before-action & prediction error tracking
    - Information gain & deterministic action selection
    - Contradiction detection & discriminating experiments
    - Adversarial self-challenge & independent verification
    - Structured "Why this action?" decision traces
    - Transparent evidence weighting & multi-factor confidence model
    - Asynchronous multi-agent specialist architecture & parallel orchestration
"""

from sonic.research.event_bus import (
    AnomalyDetectedEvent,
    EndpointDiscoveredEvent,
    HypothesisFalsifiedEvent,
    HypothesisProposedEvent,
    ResearchEvent,
    ResearchEventBus,
    ResearchStateChangedEvent,
    TargetDiscoveredEvent,
    VulnerabilityVerifiedEvent,
)
from sonic.research.orchestrator import (
    AsyncResearchOrchestrator,
    ConflictRecord,
    DecompositionRule,
    ObservationClaim,
    ResearchBlackboard,
    ResearchResult,
)
from sonic.research.attack_graph import (
    AttackEdge,
    AttackGraph,
    AttackNode,
    AttackNodeType,
    AttackPath,
)
from sonic.research.specialist import (
    ApiSpecialist,
    AuthSpecialist,
    BudgetExhaustedError,
    BusinessLogicSpecialist,
    CloudSpecialist,
    FalsificationSpecialist,
    NetworkSpecialist,
    SpecialistAgent,
    SpecialistBlockedError,
    SpecialistBudget,
    SpecialistState,
    SpecialistTimeoutError,
    WebSpecialist,
    classify_specialist_failure,
)
from sonic.research.failure_classifier import classify_failure
from sonic.research.failure_budget import FailureBudgetTracker


__all__ = [
    # Event Bus & Typed Events
    "ResearchEvent",
    "TargetDiscoveredEvent",
    "EndpointDiscoveredEvent",
    "AnomalyDetectedEvent",
    "HypothesisProposedEvent",
    "HypothesisFalsifiedEvent",
    "VulnerabilityVerifiedEvent",
    "ResearchStateChangedEvent",
    "ResearchEventBus",
    # Specialists (The 6 Core Researchers + Falsification)
    "SpecialistAgent",
    "SpecialistState",
    "SpecialistBudget",
    "BudgetExhaustedError",
    "SpecialistBlockedError",
    "SpecialistTimeoutError",
    "classify_specialist_failure",
    "WebSpecialist",
    "ApiSpecialist",
    "AuthSpecialist",
    "NetworkSpecialist",
    "BusinessLogicSpecialist",
    "CloudSpecialist",
    "FalsificationSpecialist",
    # Orchestration & Blackboard
    "AsyncResearchOrchestrator",
    "ResearchBlackboard",
    "DecompositionRule",
    "ResearchResult",
    "ObservationClaim",
    "ConflictRecord",
    # Attack Graph
    "AttackNodeType",
    "AttackNode",
    "AttackEdge",
    "AttackPath",
    "AttackGraph",
    # Failure Engine & Classification
    "classify_failure",
    "FailureBudgetTracker",
]
