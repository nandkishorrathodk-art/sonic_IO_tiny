"""
SONIC-REDA — Graph Memory Node & Edge Schemas
=================================================
Defines all node types and relationship types for the
Agent-to-Agent Graph Memory (Neo4j).

Node Types:
    - Engagement: A security testing engagement
    - Asset: Domain, IP, URL, endpoint, technology
    - Finding: A security vulnerability/issue discovered
    - Hypothesis: A theory about a potential vulnerability
    - EvidenceNode: Proof attached to a finding
    - Technique: Attack technique or methodology used
    - AgentNode: Record of an agent's participation

Relationships:
    - TARGETS: Engagement → Asset
    - DISCOVERED_ON: Finding → Asset
    - VALIDATED_BY: Finding → AgentNode
    - HAS_EVIDENCE: Finding → EvidenceNode
    - RELATED_TO: Finding ↔ Finding
    - CAUSED_BY: Finding → Technique
    - TESTED_WITH: Hypothesis → Technique
    - FOUND_BY: Finding → AgentNode
    - SPAWNED: AgentNode → AgentNode
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ============================================
# Enums
# ============================================

class AssetType(StrEnum):
    DOMAIN = "domain"
    SUBDOMAIN = "subdomain"
    IP = "ip"
    URL = "url"
    ENDPOINT = "endpoint"
    TECHNOLOGY = "technology"
    REPOSITORY = "repository"
    PORT = "port"
    PARAMETER = "parameter"


class FindingSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FindingStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_VERIFICATION = "needs_verification"
    VERIFIED = "verified"
    FALSE_POSITIVE = "false_positive"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class HypothesisStatus(StrEnum):
    PROPOSED = "proposed"
    TESTING = "testing"
    CONFIRMED = "confirmed"
    DISPROVED = "disproved"
    ABANDONED = "abandoned"


class EngagementStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================
# Node Schemas
# ============================================

def _new_id() -> str:
    return uuid.uuid4().hex[:16]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EngagementNode(BaseModel):
    """An engagement / security testing project."""
    uid: str = Field(default_factory=_new_id)
    tenant_id: str = "default"
    name: str
    description: str = ""
    target_summary: str = ""
    status: EngagementStatus = EngagementStatus.CREATED
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    created_by: str = ""  # User email
    scope_config: str = ""  # JSON serialized scope

    @property
    def neo4j_label(self) -> str:
        return "Engagement"


class AssetNode(BaseModel):
    """A discovered asset (domain, IP, URL, tech, etc.)."""
    uid: str = Field(default_factory=_new_id)
    tenant_id: str = "default"
    asset_type: AssetType
    value: str  # e.g., "example.com", "192.168.1.1", "/api/v1/users"
    name: str = ""
    metadata: str = ""  # JSON blob for extra info (headers, tech stack, etc.)
    discovered_at: str = Field(default_factory=_now)
    discovered_by: str = ""  # Agent ID
    engagement_id: str = ""

    @property
    def neo4j_label(self) -> str:
        return "Asset"


class FindingNode(BaseModel):
    """A security finding / vulnerability."""
    uid: str = Field(default_factory=_new_id)
    tenant_id: str = "default"
    title: str
    description: str
    vulnerability_class: str  # "XSS", "SQLi", "IDOR", "SSRF", etc.
    severity: FindingSeverity = FindingSeverity.MEDIUM
    status: FindingStatus = FindingStatus.DRAFT
    confidence_score: int = 0  # 0-100
    poc: str = ""  # Proof of concept
    impact: str = ""
    remediation: str = ""
    raw_request: str = ""
    raw_response: str = ""
    found_by: str = ""  # Agent ID
    verified_by: str = ""  # Verifier agent ID
    engagement_id: str = ""
    target_asset: str = ""  # Asset UID
    created_at: str = Field(default_factory=_now)
    verified_at: str = ""

    @property
    def neo4j_label(self) -> str:
        return "Finding"


class HypothesisNode(BaseModel):
    """A hypothesis about a potential vulnerability."""
    uid: str = Field(default_factory=_new_id)
    tenant_id: str = "default"
    title: str
    description: str
    vulnerability_class: str
    rationale: str = ""  # Why this might be vulnerable
    test_plan: str = ""  # How to test it
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    priority: int = 5  # 1-10
    proposed_by: str = ""  # Agent ID
    engagement_id: str = ""
    created_at: str = Field(default_factory=_now)

    @property
    def neo4j_label(self) -> str:
        return "Hypothesis"


class EvidenceNode(BaseModel):
    """A piece of evidence attached to a finding."""
    uid: str = Field(default_factory=_new_id)
    tenant_id: str = "default"
    evidence_type: str  # "request", "response", "screenshot", "log", "har", "code"
    content: str
    description: str = ""
    finding_id: str = ""
    created_by: str = ""
    created_at: str = Field(default_factory=_now)

    @property
    def neo4j_label(self) -> str:
        return "Evidence"


class TechniqueNode(BaseModel):
    """An attack technique or methodology."""
    uid: str = Field(default_factory=_new_id)
    tenant_id: str = "default"
    name: str  # e.g., "Reflected XSS via URL parameter"
    category: str = ""  # "injection", "auth_bypass", "info_disclosure"
    description: str = ""
    tools_used: str = ""  # Comma-separated: "nuclei,ffuf"
    success_rate: float = 0.0  # Historical success rate
    created_at: str = Field(default_factory=_now)

    @property
    def neo4j_label(self) -> str:
        return "Technique"


class AgentNode(BaseModel):
    """Record of an agent's participation in the graph."""
    uid: str = Field(default_factory=_new_id)
    tenant_id: str = "default"
    agent_id: str
    agent_type: str  # "recon", "static", "dynamic", "verifier", "orchestrator"
    name: str
    status: str = "active"
    engagement_id: str = ""
    started_at: str = Field(default_factory=_now)
    completed_at: str = ""
    findings_count: int = 0
    actions_count: int = 0

    @property
    def neo4j_label(self) -> str:
        return "Agent"



# ============================================
# Relationship Types
# ============================================

class RelationshipType(StrEnum):
    """Standard relationship types in the graph."""
    # Engagement relationships
    TARGETS = "TARGETS"                  # Engagement → Asset
    PART_OF = "PART_OF"                  # Asset/Finding → Engagement

    # Discovery relationships
    DISCOVERED_ON = "DISCOVERED_ON"      # Finding → Asset
    FOUND_BY = "FOUND_BY"               # Finding → Agent
    DISCOVERED_BY = "DISCOVERED_BY"      # Asset → Agent

    # Validation relationships
    VALIDATED_BY = "VALIDATED_BY"        # Finding → Agent
    HAS_EVIDENCE = "HAS_EVIDENCE"       # Finding → Evidence
    TESTED_WITH = "TESTED_WITH"         # Finding/Hypothesis → Technique

    # Knowledge relationships
    RELATED_TO = "RELATED_TO"           # Finding ↔ Finding
    CAUSED_BY = "CAUSED_BY"             # Finding → root cause
    LEADS_TO = "LEADS_TO"              # Hypothesis → Finding
    CHILD_OF = "CHILD_OF"              # Asset → parent Asset (subdomain → domain)

    # Agent relationships
    SPAWNED = "SPAWNED"                 # Agent → Agent
    ASSIGNED_TO = "ASSIGNED_TO"         # Hypothesis → Agent

    # Phase 6 Research & Critical Thinking relationships
    INVESTIGATED_BY = "INVESTIGATED_BY" # Unknown → Experiment / Task
    TESTED_BY = "TESTED_BY"             # Hypothesis → Experiment / Task
    PRODUCED = "PRODUCED"               # Experiment → Observation / Evidence
    SUPPORTS = "SUPPORTS"               # Observation / Evidence → Hypothesis
    CONTRADICTS = "CONTRADICTS"         # Observation / Evidence → Hypothesis
    SELECTED_ACTION = "SELECTED_ACTION" # Decision → Task

    # Phase 7 Trust & Independent Verification relationships
    VERIFIED_BY = "VERIFIED_BY"         # Finding → Verifier Agent / Sandbox
    CHALLENGED_BY = "CHALLENGED_BY"     # Finding → Adversarial Review
    HAS_REPRODUCTION = "HAS_REPRODUCTION" # Finding → Reproduction Plan

    # Phase 8 Autonomous Self-Evolution relationships
    IDENTIFIED_FROM = "IDENTIFIED_FROM" # FailurePattern → Execution
    PROPOSES = "PROPOSES"               # FailurePattern → ImprovementHypothesis
    DERIVED_FROM = "DERIVED_FROM"       # EvolutionCandidate → ImprovementHypothesis
    TESTED_IN = "TESTED_IN"             # EvolutionCandidate → EvolutionLab
    EVALUATED_BY = "EVALUATED_BY"       # EvolutionCandidate → Benchmark
    OUTPERFORMED = "OUTPERFORMED"       # EvolutionCandidate → BaselineVersion
    REJECTED_BY = "REJECTED_BY"         # EvolutionCandidate → Gate
    PROMOTED_TO = "PROMOTED_TO"         # EvolutionCandidate → ProductionVersion
    ROLLED_BACK_TO = "ROLLED_BACK_TO"   # EvolutionCandidate → BaselineVersion


# ============================================
# Schema Initialization Queries
# ============================================

SCHEMA_INIT_QUERIES = [
    # Unique constraints
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Engagement) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Asset) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Finding) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Hypothesis) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Evidence) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Technique) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Agent) REQUIRE n.uid IS UNIQUE",

    # Indexes for fast lookups
    "CREATE INDEX IF NOT EXISTS FOR (n:Asset) ON (n.asset_type)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Asset) ON (n.value)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Finding) ON (n.severity)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Finding) ON (n.status)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Finding) ON (n.vulnerability_class)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Finding) ON (n.engagement_id)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Hypothesis) ON (n.status)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Agent) ON (n.agent_id)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Engagement) ON (n.status)",

    # Full-text indexes for search
    "CREATE FULLTEXT INDEX findingSearch IF NOT EXISTS FOR (n:Finding) ON EACH [n.title, n.description, n.vulnerability_class]",
    "CREATE FULLTEXT INDEX assetSearch IF NOT EXISTS FOR (n:Asset) ON EACH [n.value, n.name]",
]
