"""
SONIC-REDA — Evidence, Independent Adversarial Verification & Trust Engine (Phase 7)
"""

from sonic.evidence.benchmark import TrustBenchmarkMetrics, TrustBenchmarkRunner
from sonic.evidence.confidence_engine import FindingConfidenceEngine, FindingConfidenceResult
from sonic.evidence.consistency import EvidenceConsistencyEngine
from sonic.evidence.custody import CustodyChain
from sonic.evidence.dedup import FalsePositiveFilter, FindingFingerprinter
from sonic.evidence.independent_verifier import AdversarialReviewer, IndependentVerifier
from sonic.evidence.models import (
    ArtifactType,
    ConfidenceBand,
    EvidenceItem,
    EvidenceQualityScore,
    FindingLifecycleState,
    FindingSeverity,
    ProvenancedFinding,
    ReproductionPlan,
    VerificationResult,
)
from sonic.evidence.package import EvidencePackageManager
from sonic.evidence.reproduction_engine import ReproductionEngine

__all__ = [
    "ArtifactType",
    "ConfidenceBand",
    "EvidenceItem",
    "EvidenceQualityScore",
    "FindingLifecycleState",
    "FindingSeverity",
    "ProvenancedFinding",
    "ReproductionPlan",
    "VerificationResult",
    "CustodyChain",
    "IndependentVerifier",
    "AdversarialReviewer",
    "ReproductionEngine",
    "EvidenceConsistencyEngine",
    "FindingConfidenceEngine",
    "FindingConfidenceResult",
    "FindingFingerprinter",
    "FalsePositiveFilter",
    "EvidencePackageManager",
    "TrustBenchmarkRunner",
    "TrustBenchmarkMetrics",
    "VerificationGate",
    "GateDecision",
    "GateStatus",
]
from sonic.evidence.gate import GateDecision, GateStatus, VerificationGate
