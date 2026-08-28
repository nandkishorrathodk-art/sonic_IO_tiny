"""
SONIC-REDA — Evidence Models & Finding Lifecycle (Phase 7)
============================================================
Data models defining immutable evidence items, finding lifecycle states,
evidence quality scoring, cryptographic provenance, and verification history.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


def _new_id(prefix: str = "ev") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================
# 1. Lifecycle States & Enums
# ============================================

class FindingLifecycleState(StrEnum):
    """
    Explicit, auditable finding verification lifecycle.
    Direct transition from HYPOTHESIS to VERIFIED is strictly forbidden.
    """
    HYPOTHESIS = "hypothesis"
    CANDIDATE = "candidate"
    VALIDATING = "validating"
    EVIDENCE_COLLECTING = "evidence_collecting"
    INDEPENDENTLY_VERIFIED = "independently_verified"
    ADVERSARIAL_REVIEW = "adversarial_review"
    VERIFIED = "verified"
    REJECTED = "rejected"
    HUMAN_REVIEW = "human_review"


class ArtifactType(StrEnum):
    """All supported raw evidence artifact types."""
    HTTP_REQUEST = "http_request"
    HTTP_RESPONSE = "http_response"
    SCREENSHOT = "screenshot"
    DOM = "dom"
    CONSOLE_LOG = "console_log"
    TOOL_OUTPUT = "tool_output"
    SOURCE_CODE = "source_code"
    STACK_TRACE = "stack_trace"
    BINARY_OUTPUT = "binary_output"
    TIMELINE_EVENT = "timeline_event"
    CONFIGURATION = "configuration"


class FindingSeverity(StrEnum):
    """Finding severity (Impact/Risk). Strictly separated from Confidence."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ConfidenceBand(StrEnum):
    """Calibrated confidence bands."""
    LOW = "low"             # 0.00 - 0.39
    MODERATE = "moderate"   # 0.40 - 0.69
    HIGH = "high"           # 0.70 - 0.89
    VERY_HIGH = "very_high" # 0.90 - 1.00

    @classmethod
    def from_score(cls, score: float) -> ConfidenceBand:
        if score >= 0.90:
            return cls.VERY_HIGH
        if score >= 0.70:
            return cls.HIGH
        if score >= 0.40:
            return cls.MODERATE
        return cls.LOW


# ============================================
# 2. Immutable Evidence Item Model
# ============================================

class EvidenceItem(BaseModel):
    """
    An immutable, provenanced evidence artifact.
    Answers: WHO, WHAT, WHEN, WHERE, UNDER WHICH SANDBOX, USING WHICH TOOL.
    """
    id: str = Field(default_factory=lambda: _new_id("evi"))
    tenant_id: str                          # Mandatory multi-tenant isolation
    engagement_id: str                      # Mandatory engagement scope
    finding_id: str = ""
    
    # Provenance
    source_type: str = "tool"               # "tool", "browser", "verifier_agent", "discovery_agent"
    source_agent: str = ""                  # Agent ID that produced this
    tool_name: str = ""                     # Tool used (e.g. "nmap", "ffuf", "chromium")
    tool_version: str = "1.0.0"
    execution_id: str = ""                  # Task / Execution ID
    sandbox_id: str = ""                    # Sandbox container/VM ID
    
    # Artifact Data & Immutability
    artifact_type: ArtifactType
    artifact_reference: str = ""            # S3 / file path storage key
    raw_content: str = ""                   # Inlined text or truncated payload
    content_hash: str = ""                  # SHA-256 of raw artifact
    
    # Quality & Reliability Attributes
    reliability: float = 0.9                # 0.0-1.0: Reliability of source
    directness: float = 1.0                 # 1.0=direct measurement, 0.5=indirect
    independence: float = 1.0               # 1.0=independently generated
    confidence: float = 0.8                 # Individual item confidence
    
    # Versioning & Audit
    version: int = 1
    parent_evidence_id: Optional[str] = None
    created_at: str = Field(default_factory=_now)

    def compute_and_set_hash(self) -> str:
        """Compute SHA-256 of content and set content_hash."""
        content_bytes = self.raw_content.encode("utf-8") if self.raw_content else self.artifact_reference.encode("utf-8")
        h = hashlib.sha256(content_bytes).hexdigest()
        self.content_hash = h
        return h

    def verify_hash(self) -> bool:
        """Verify that current content matches the recorded SHA-256 hash."""
        if not self.content_hash:
            return False
        content_bytes = self.raw_content.encode("utf-8") if self.raw_content else self.artifact_reference.encode("utf-8")
        return hashlib.sha256(content_bytes).hexdigest() == self.content_hash


# ============================================
# 3. Evidence Quality Scoring
# ============================================

class EvidenceQualityScore(BaseModel):
    """Multidimensional evaluation of evidence quality."""
    directness: float = 0.0           # 0.0-1.0
    reliability: float = 0.0          # 0.0-1.0
    independence: float = 0.0         # 0.0-1.0
    reproducibility: float = 0.0      # 0.0-1.0
    completeness: float = 0.0         # 0.0-1.0
    freshness: float = 0.0            # 0.0-1.0
    composite_score: float = 0.0      # 0.0-1.0

    @classmethod
    def evaluate(cls, items: list[EvidenceItem], is_reproduced: bool = False) -> EvidenceQualityScore:
        if not items:
            return cls()

        dir_score = sum(it.directness for it in items) / len(items)
        rel_score = sum(it.reliability for it in items) / len(items)
        ind_score = sum(it.independence for it in items) / len(items)
        reprod_score = 1.0 if is_reproduced else 0.5
        comp_score = min(1.0, len(items) / 3.0)  # Complete if at least 3 distinct evidence items
        fresh_score = 1.0

        composite = round((
            dir_score * 0.25 +
            rel_score * 0.25 +
            ind_score * 0.20 +
            reprod_score * 0.20 +
            comp_score * 0.10
        ), 3)

        return cls(
            directness=round(dir_score, 3),
            reliability=round(rel_score, 3),
            independence=round(ind_score, 3),
            reproducibility=round(reprod_score, 3),
            completeness=round(comp_score, 3),
            freshness=round(fresh_score, 3),
            composite_score=composite,
        )


# ============================================
# 4. Reproduction & Verification Lineage
# ============================================

class ReproductionPlan(BaseModel):
    """Structured plan for isolated sandbox reproduction."""
    finding_id: str
    target: str
    prerequisites: list[str] = Field(default_factory=list)
    environment: dict[str, Any] = Field(default_factory=dict)  # sandbox image, browser version, tool version
    steps: list[str] = Field(default_factory=list)             # Step-by-step reproduction instructions
    poc_command: str = ""                                      # Exact curl / python / script PoC
    expected_result: str = ""                                  # Expected status code or payload
    success_conditions: dict[str, Any] = Field(default_factory=dict)
    failure_conditions: dict[str, Any] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    """Record of an independent or adversarial verification pass."""
    verifier_id: str                        # Verifier Agent / Sandbox ID
    verifier_type: str = "independent"      # "independent", "adversarial", "automated_reproduction"
    status: str = "verified"                # "verified", "rejected", "conflict"
    reproducible: bool = True
    contradictions_found: list[str] = Field(default_factory=list)
    notes: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=_now)


# ============================================
# 5. Provenanced Finding Model
# ============================================

class ProvenancedFinding(BaseModel):
    """
    A trustworthy security finding with complete cryptographic evidence,
    separated severity and confidence, and full verification lineage.
    """
    id: str = Field(default_factory=lambda: _new_id("find"))
    tenant_id: str                          # Multi-tenant boundary
    engagement_id: str                      # Engagement scope
    
    # Finding Core Information
    title: str
    description: str
    vulnerability_class: str                # "Auth Bypass", "SQLi", "IDOR", "RCE", etc.
    target: str
    endpoint: str = ""
    
    # Strict Separation: Severity vs Confidence
    severity: FindingSeverity               # Impact/Hazard level
    confidence_score: float = 0.0           # 0.0-1.0 calibrated confidence
    confidence_band: ConfidenceBand = ConfidenceBand.LOW
    exploitability_score: float = 0.8
    impact_description: str = ""
    remediation: str = ""

    # Lifecycle & Lineage
    lifecycle_state: FindingLifecycleState = FindingLifecycleState.CANDIDATE
    fingerprint: str = ""                   # Deduplication hash
    
    # Evidence & Verification Attachments
    poc: str = ""                           # Reproducible PoC
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    reproduction_plan: Optional[ReproductionPlan] = None
    verification_history: list[VerificationResult] = Field(default_factory=list)
    quality_score: Optional[EvidenceQualityScore] = None
    
    # Agents
    created_by_agent: str = ""              # Discovery Agent ID
    verified_by_agents: list[str] = Field(default_factory=list)
    
    # Timestamps & Reportability
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    verified_at: Optional[str] = None
    is_reportable: bool = False

    def add_evidence(self, item: EvidenceItem) -> None:
        """Attach an immutable, hashed evidence item."""
        if not item.content_hash:
            item.compute_and_set_hash()
        item.finding_id = self.id
        item.tenant_id = self.tenant_id
        item.engagement_id = self.engagement_id
        self.evidence_items.append(item)
        self.updated_at = _now()

    def transition_to(self, new_state: FindingLifecycleState, agent_id: str = "", reason: str = "") -> None:
        """Auditable state transition."""
        self.lifecycle_state = new_state
        self.updated_at = _now()
        if new_state == FindingLifecycleState.VERIFIED:
            self.verified_at = _now()
            self.is_reportable = True
        elif new_state == FindingLifecycleState.REJECTED:
            self.is_reportable = False
