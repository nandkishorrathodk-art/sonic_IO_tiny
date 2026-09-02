"""
SONIC-REDA — Cognitive State Machine
=========================================
The engagement-level "mind" of the SONIC system.

Maintains a structured world model with clear epistemic distinctions:
    - OBSERVATION: Raw data from tool/agent output (source-tagged)
    - FACT: Verified observation with evidence (append-only, never deleted)
    - ASSUMPTION: Believed-true without full verification
    - HYPOTHESIS: Testable theory about a vulnerability
    - INFERENCE: Derived conclusion (explicitly distinguished from fact)
    - UNKNOWN: First-class uncertainty that drives action selection

All state mutations are append-only with full audit log.
Nothing is silently overwritten — corrections create new events.

Authoritative store: Neo4j (knowledge graph) + Redis (transient coordination).
PostgreSQL owns identity/tenant/audit. This module produces events for all stores.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ============================================
# Epistemic Types (World Model)
# ============================================

class EpistemicType(StrEnum):
    """Clear distinction between knowledge categories."""
    OBSERVATION = "observation"   # Raw data from tool/agent output
    FACT = "fact"                 # Verified observation with evidence
    ASSUMPTION = "assumption"     # Believed-true without full verification
    HYPOTHESIS = "hypothesis"     # Testable theory
    INFERENCE = "inference"       # Derived conclusion (NOT a verified fact)
    UNKNOWN = "unknown"           # First-class uncertainty


class ConfidenceLevel(StrEnum):
    """Qualitative confidence levels."""
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"
    VERIFIED = "verified"


class HypothesisLifecycle(StrEnum):
    """Hypothesis state machine — evidence-driven transitions."""
    PROPOSED = "proposed"
    CANDIDATE = "candidate"
    VALIDATING = "validating"
    EVIDENCE_COLLECTED = "evidence_collected"
    VERIFIED = "verified"
    DISPROVED = "disproved"
    ABANDONED = "abandoned"


# ============================================
# Helper functions
# ============================================

def _new_id() -> str:
    return uuid.uuid4().hex[:16]


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ============================================
# Provenance — source tracking for observations
# ============================================

class Provenance(BaseModel):
    """Tracks the origin of any piece of knowledge."""
    source_type: str = ""        # "tool", "agent", "llm", "user", "system"
    source_agent: str = ""       # Agent ID that produced this
    tool: str = ""               # Tool name (nmap, nuclei, etc.)
    execution_id: str = ""       # Job/execution ID
    sandbox_id: str = ""         # Sandbox that produced the data
    timestamp: str = Field(default_factory=_now)
    confidence: float = 0.5      # 0.0-1.0
    evidence_refs: list[str] = Field(default_factory=list)


# ============================================
# Core Knowledge Objects
# ============================================

class Observation(BaseModel):
    """Raw data from tool/agent output. NOT a fact until verified."""
    id: str = Field(default_factory=_new_id)
    description: str
    raw_data: str = ""           # Raw output (truncated if large)
    epistemic_type: EpistemicType = EpistemicType.OBSERVATION
    provenance: Provenance = Field(default_factory=Provenance)
    engagement_id: str = ""
    tenant_id: str = ""
    created_at: str = Field(default_factory=_now)


class Fact(BaseModel):
    """Verified truth with evidence link. Append-only — never deleted."""
    id: str = Field(default_factory=_new_id)
    description: str
    epistemic_type: EpistemicType = EpistemicType.FACT
    provenance: Provenance = Field(default_factory=Provenance)
    evidence_ids: list[str] = Field(default_factory=list)
    derived_from: list[str] = Field(default_factory=list)  # Observation/Inference IDs
    engagement_id: str = ""
    tenant_id: str = ""
    created_at: str = Field(default_factory=_now)
    superseded_by: str = ""     # If corrected, points to the correcting Fact


class Assumption(BaseModel):
    """Believed-true without full verification. May be invalidated."""
    id: str = Field(default_factory=_new_id)
    description: str
    epistemic_type: EpistemicType = EpistemicType.ASSUMPTION
    rationale: str = ""         # Why we believe this
    provenance: Provenance = Field(default_factory=Provenance)
    is_valid: bool = True
    invalidated_by: str = ""    # Evidence/Fact ID that invalidated it
    engagement_id: str = ""
    tenant_id: str = ""
    created_at: str = Field(default_factory=_now)


class CognitiveHypothesis(BaseModel):
    """Testable theory about a potential vulnerability."""
    id: str = Field(default_factory=_new_id)
    title: str
    description: str
    vulnerability_class: str = ""
    epistemic_type: EpistemicType = EpistemicType.HYPOTHESIS
    lifecycle: HypothesisLifecycle = HypothesisLifecycle.PROPOSED
    rationale: str = ""
    test_plan: str = ""
    expected_observation: str = ""  # What we expect to see if true
    actual_observation: str = ""    # What we actually observed
    priority: int = 5               # 1=critical, 10=low
    provenance: Provenance = Field(default_factory=Provenance)
    evidence_ids: list[str] = Field(default_factory=list)
    engagement_id: str = ""
    tenant_id: str = ""
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class Inference(BaseModel):
    """Derived conclusion. Explicitly NOT a verified fact."""
    id: str = Field(default_factory=_new_id)
    description: str
    epistemic_type: EpistemicType = EpistemicType.INFERENCE
    derived_from: list[str] = Field(default_factory=list)  # Source IDs
    reasoning: str = ""         # How this was derived
    confidence: float = 0.5
    provenance: Provenance = Field(default_factory=Provenance)
    promoted_to_fact: str = ""  # If verified, points to the Fact ID
    engagement_id: str = ""
    tenant_id: str = ""
    created_at: str = Field(default_factory=_now)


class Unknown(BaseModel):
    """First-class uncertainty that drives action selection."""
    id: str = Field(default_factory=_new_id)
    question: str               # "Does endpoint X share auth policy with Y?"
    category: str = ""          # "authorization", "input_validation", etc.
    possible_actions: list[str] = Field(default_factory=list)
    estimated_importance: float = 0.5  # 0.0-1.0, how much this affects outcomes
    resolved: bool = False
    resolved_by: str = ""       # Fact/Observation ID that resolved it
    resolution: str = ""        # Answer to the question
    engagement_id: str = ""
    tenant_id: str = ""
    created_at: str = Field(default_factory=_now)
    resolved_at: str = ""


class Attempt(BaseModel):
    """Record of an attempted action (successful or failed)."""
    id: str = Field(default_factory=_new_id)
    method: str                 # What was tried
    assumption: str = ""        # What assumption was being tested
    hypothesis_id: str = ""     # Related hypothesis
    task_id: str = ""           # Task that executed this
    agent_id: str = ""
    result_summary: str = ""
    success: bool = False
    failure_reason: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    lesson: str = ""            # What was learned from this attempt
    engagement_id: str = ""
    tenant_id: str = ""
    created_at: str = Field(default_factory=_now)


class EvidenceRef(BaseModel):
    """Lightweight reference to an evidence artifact."""
    id: str = Field(default_factory=_new_id)
    evidence_type: str          # "request", "response", "screenshot", "log", "har", "code"
    description: str = ""
    content_hash: str = ""      # SHA256 of content for integrity
    storage_key: str = ""       # Where the full content is stored
    finding_id: str = ""
    engagement_id: str = ""
    tenant_id: str = ""
    created_at: str = Field(default_factory=_now)


# ============================================
# Cognitive State Event Log (Append-Only)
# ============================================

class CognitiveEventType(StrEnum):
    """All possible state mutation event types."""
    STATE_CREATED = "state_created"
    OBSERVATION_ADDED = "observation_added"
    FACT_CREATED = "fact_created"
    FACT_CORRECTED = "fact_corrected"
    ASSUMPTION_CREATED = "assumption_created"
    ASSUMPTION_INVALIDATED = "assumption_invalidated"
    HYPOTHESIS_CREATED = "hypothesis_created"
    HYPOTHESIS_UPDATED = "hypothesis_updated"
    HYPOTHESIS_VERIFIED = "hypothesis_verified"
    HYPOTHESIS_DISPROVED = "hypothesis_disproved"
    INFERENCE_CREATED = "inference_created"
    INFERENCE_PROMOTED = "inference_promoted"
    UNKNOWN_CREATED = "unknown_created"
    UNKNOWN_RESOLVED = "unknown_resolved"
    EVIDENCE_ADDED = "evidence_added"
    ATTEMPT_RECORDED = "attempt_recorded"
    CONFIDENCE_CHANGED = "confidence_changed"
    NEXT_ACTION_UPDATED = "next_action_updated"
    REPLAN_OCCURRED = "replan_occurred"
    GOAL_UPDATED = "goal_updated"
    PREDICTION_MADE = "prediction_made"
    PREDICTION_EVALUATED = "prediction_evaluated"
    CONTRADICTION_DETECTED = "contradiction_detected"
    CONTRADICTION_RESOLVED = "contradiction_resolved"
    DECISION_RECORDED = "decision_recorded"
    STOP_CONDITION_EVALUATED = "stop_condition_evaluated"


class CognitiveEvent(BaseModel):
    """Immutable audit record of a state mutation."""
    event_id: str = Field(default_factory=_new_id)
    tenant_id: str
    engagement_id: str
    event_type: CognitiveEventType
    object_id: str = ""         # ID of the created/modified object
    object_type: str = ""       # "fact", "hypothesis", "unknown", etc.
    agent_id: str = ""
    description: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=_now)


# ============================================
# Next-Best-Action Engine Types
# ============================================

class CandidateAction(BaseModel):
    """A possible next action with structured reasoning."""
    id: str = Field(default_factory=_new_id)
    action: str                          # What to do
    agent_type: str = ""                 # Which agent type would execute
    target: str = ""                     # Target/endpoint
    expected_information_gain: float = 0.0  # 0.0-1.0
    cost: float = 0.0                    # Relative cost (LLM calls, time, compute)
    risk: float = 0.0                    # Risk level 0.0-1.0
    dependencies: list[str] = Field(default_factory=list)  # Task IDs
    confidence: float = 0.5             # How confident are we this will succeed
    resolves_unknowns: list[str] = Field(default_factory=list)  # Unknown IDs


class NextBestActionDecision(BaseModel):
    """Structured decision for what to do next."""
    candidate_actions: list[CandidateAction] = Field(default_factory=list)
    selected_action: CandidateAction | None = None
    reason: str = ""
    engagement_id: str = ""
    tenant_id: str = ""
    decided_at: str = Field(default_factory=_now)


# ============================================
# Resource Budget
# ============================================

class EngagementBudget(BaseModel):
    """Configurable resource limits per engagement."""
    max_agents_per_engagement: int = 8
    max_spawn_depth: int = 3
    max_total_tasks: int = 50
    max_execution_time_seconds: int = 3600  # 1 hour
    max_compute_budget_seconds: int = 1800  # 30 min sandbox time
    max_llm_calls: int = 200
    max_replans: int = 5
    max_parallel: int = 4


# ============================================
# Cognitive State (The "Mind")
# ============================================

class CognitiveState(BaseModel):
    """
    The agent system's 'mind' for a single engagement.

    All mutations go through methods that emit CognitiveEvent records.
    The event_log is append-only — nothing is ever deleted.

    Authoritative for: engagement-level reasoning state.
    Persisted to: Redis (transient), Neo4j (knowledge graph).
    """
    engagement_id: str
    tenant_id: str               # NEVER "default" in production

    # Mission
    goal: str = ""
    budget: EngagementBudget = Field(default_factory=EngagementBudget)

    # World Model
    observations: list[Observation] = Field(default_factory=list)
    known_facts: list[Fact] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    hypotheses: list[CognitiveHypothesis] = Field(default_factory=list)
    inferences: list[Inference] = Field(default_factory=list)
    unknowns: list[Unknown] = Field(default_factory=list)

    # Evidence
    evidence: list[EvidenceRef] = Field(default_factory=list)

    # Attempts
    failed_attempts: list[Attempt] = Field(default_factory=list)
    successful_attempts: list[Attempt] = Field(default_factory=list)

    # Reasoning & Decisions
    confidence: float = 0.0      # 0.0-1.0 overall engagement confidence
    confidence_breakdown: dict[str, Any] | None = None
    next_best_action: str = ""
    last_decision: NextBestActionDecision | None = None
    decision_traces: list[Any] = Field(default_factory=list)

    # Research & Epistemic Objects (Phase 6)
    competing_hypotheses: list[Any] = Field(default_factory=list)
    predictions: list[Any] = Field(default_factory=list)
    prediction_comparisons: list[Any] = Field(default_factory=list)
    contradictions: list[Any] = Field(default_factory=list)

    # Stop & Review State
    stop_condition: str = "none"
    stop_reason: str = ""

    # Replanning
    replan_count: int = 0

    # Metrics
    llm_calls_used: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    agents_spawned: int = 0

    # Audit
    event_log: list[CognitiveEvent] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)

    # ============================================
    # State Mutation Methods (all emit events)
    # ============================================

    def _emit(
        self,
        event_type: CognitiveEventType,
        object_id: str = "",
        object_type: str = "",
        agent_id: str = "",
        description: str = "",
        payload: dict[str, Any] | None = None,
    ) -> CognitiveEvent:
        """Append an immutable event to the audit log."""
        event = CognitiveEvent(
            tenant_id=self.tenant_id,
            engagement_id=self.engagement_id,
            event_type=event_type,
            object_id=object_id,
            object_type=object_type,
            agent_id=agent_id,
            description=description,
            payload=payload or {},
        )
        self.event_log.append(event)
        self.updated_at = _now()
        return event

    def add_observation(self, obs: Observation, agent_id: str = "") -> CognitiveEvent:
        """Record a raw observation from a tool/agent."""
        obs.engagement_id = self.engagement_id
        obs.tenant_id = self.tenant_id
        self.observations.append(obs)
        return self._emit(
            CognitiveEventType.OBSERVATION_ADDED,
            object_id=obs.id,
            object_type="observation",
            agent_id=agent_id,
            description=obs.description[:200],
        )

    def add_fact(self, fact: Fact, agent_id: str = "") -> CognitiveEvent:
        """Record a verified fact. Append-only — facts are never deleted."""
        fact.engagement_id = self.engagement_id
        fact.tenant_id = self.tenant_id
        self.known_facts.append(fact)
        return self._emit(
            CognitiveEventType.FACT_CREATED,
            object_id=fact.id,
            object_type="fact",
            agent_id=agent_id,
            description=fact.description[:200],
        )

    def correct_fact(
        self, old_fact_id: str, new_fact: Fact, agent_id: str = ""
    ) -> CognitiveEvent:
        """Correct a fact — old fact is superseded, never deleted."""
        for f in self.known_facts:
            if f.id == old_fact_id:
                f.superseded_by = new_fact.id
                break
        new_fact.engagement_id = self.engagement_id
        new_fact.tenant_id = self.tenant_id
        new_fact.derived_from.append(old_fact_id)
        self.known_facts.append(new_fact)
        return self._emit(
            CognitiveEventType.FACT_CORRECTED,
            object_id=new_fact.id,
            object_type="fact",
            agent_id=agent_id,
            description=f"Corrected {old_fact_id}: {new_fact.description[:150]}",
            payload={"supersedes": old_fact_id},
        )

    def add_assumption(self, assumption: Assumption, agent_id: str = "") -> CognitiveEvent:
        """Record an assumption."""
        assumption.engagement_id = self.engagement_id
        assumption.tenant_id = self.tenant_id
        self.assumptions.append(assumption)
        return self._emit(
            CognitiveEventType.ASSUMPTION_CREATED,
            object_id=assumption.id,
            object_type="assumption",
            agent_id=agent_id,
            description=assumption.description[:200],
        )

    def invalidate_assumption(
        self, assumption_id: str, evidence_id: str, agent_id: str = ""
    ) -> CognitiveEvent:
        """Invalidate an assumption — never deleted, marked invalid."""
        for a in self.assumptions:
            if a.id == assumption_id:
                a.is_valid = False
                a.invalidated_by = evidence_id
                break
        return self._emit(
            CognitiveEventType.ASSUMPTION_INVALIDATED,
            object_id=assumption_id,
            object_type="assumption",
            agent_id=agent_id,
            description=f"Assumption {assumption_id} invalidated by {evidence_id}",
            payload={"evidence_id": evidence_id},
        )

    def add_hypothesis(
        self, hypothesis: CognitiveHypothesis, agent_id: str = ""
    ) -> CognitiveEvent:
        """Record a new hypothesis."""
        hypothesis.engagement_id = self.engagement_id
        hypothesis.tenant_id = self.tenant_id
        self.hypotheses.append(hypothesis)
        return self._emit(
            CognitiveEventType.HYPOTHESIS_CREATED,
            object_id=hypothesis.id,
            object_type="hypothesis",
            agent_id=agent_id,
            description=hypothesis.title[:200],
        )

    def update_hypothesis(
        self,
        hypothesis_id: str,
        new_lifecycle: HypothesisLifecycle,
        actual_observation: str = "",
        evidence_ids: list[str] | None = None,
        agent_id: str = "",
    ) -> CognitiveEvent:
        """Transition a hypothesis through its lifecycle."""
        for h in self.hypotheses:
            if h.id == hypothesis_id:
                h.lifecycle = new_lifecycle
                h.updated_at = _now()
                if actual_observation:
                    h.actual_observation = actual_observation
                if evidence_ids:
                    h.evidence_ids.extend(evidence_ids)
                break

        event_type = CognitiveEventType.HYPOTHESIS_UPDATED
        if new_lifecycle == HypothesisLifecycle.VERIFIED:
            event_type = CognitiveEventType.HYPOTHESIS_VERIFIED
        elif new_lifecycle == HypothesisLifecycle.DISPROVED:
            event_type = CognitiveEventType.HYPOTHESIS_DISPROVED

        return self._emit(
            event_type,
            object_id=hypothesis_id,
            object_type="hypothesis",
            agent_id=agent_id,
            description=f"Hypothesis {hypothesis_id} → {new_lifecycle.value}",
            payload={"new_lifecycle": new_lifecycle.value, "actual_observation": actual_observation},
        )

    def add_inference(self, inference: Inference, agent_id: str = "") -> CognitiveEvent:
        """Record a derived conclusion. Explicitly NOT a fact."""
        inference.engagement_id = self.engagement_id
        inference.tenant_id = self.tenant_id
        self.inferences.append(inference)
        return self._emit(
            CognitiveEventType.INFERENCE_CREATED,
            object_id=inference.id,
            object_type="inference",
            agent_id=agent_id,
            description=inference.description[:200],
        )

    def promote_inference_to_fact(
        self, inference_id: str, fact: Fact, agent_id: str = ""
    ) -> CognitiveEvent:
        """Promote an inference to a verified fact with evidence."""
        for inf in self.inferences:
            if inf.id == inference_id:
                inf.promoted_to_fact = fact.id
                break
        fact.derived_from.append(inference_id)
        self.add_fact(fact, agent_id=agent_id)
        return self._emit(
            CognitiveEventType.INFERENCE_PROMOTED,
            object_id=inference_id,
            object_type="inference",
            agent_id=agent_id,
            description=f"Inference {inference_id} promoted to fact {fact.id}",
            payload={"fact_id": fact.id},
        )

    def add_unknown(self, unknown: Unknown, agent_id: str = "") -> CognitiveEvent:
        """Register a first-class uncertainty."""
        unknown.engagement_id = self.engagement_id
        unknown.tenant_id = self.tenant_id
        self.unknowns.append(unknown)
        return self._emit(
            CognitiveEventType.UNKNOWN_CREATED,
            object_id=unknown.id,
            object_type="unknown",
            agent_id=agent_id,
            description=unknown.question[:200],
        )

    def resolve_unknown(
        self, unknown_id: str, resolved_by: str, resolution: str, agent_id: str = ""
    ) -> CognitiveEvent:
        """Resolve an uncertainty."""
        for u in self.unknowns:
            if u.id == unknown_id:
                u.resolved = True
                u.resolved_by = resolved_by
                u.resolution = resolution
                u.resolved_at = _now()
                break
        return self._emit(
            CognitiveEventType.UNKNOWN_RESOLVED,
            object_id=unknown_id,
            object_type="unknown",
            agent_id=agent_id,
            description=f"Unknown {unknown_id} resolved: {resolution[:150]}",
            payload={"resolved_by": resolved_by, "resolution": resolution[:500]},
        )

    def add_evidence(self, ref: EvidenceRef, agent_id: str = "") -> CognitiveEvent:
        """Record an evidence artifact reference."""
        ref.engagement_id = self.engagement_id
        ref.tenant_id = self.tenant_id
        self.evidence.append(ref)
        return self._emit(
            CognitiveEventType.EVIDENCE_ADDED,
            object_id=ref.id,
            object_type="evidence",
            agent_id=agent_id,
            description=ref.description[:200],
        )

    def record_attempt(self, attempt: Attempt, agent_id: str = "") -> CognitiveEvent:
        """Record an attempt (successful or failed)."""
        attempt.engagement_id = self.engagement_id
        attempt.tenant_id = self.tenant_id
        if attempt.success:
            self.successful_attempts.append(attempt)
        else:
            self.failed_attempts.append(attempt)
        return self._emit(
            CognitiveEventType.ATTEMPT_RECORDED,
            object_id=attempt.id,
            object_type="attempt",
            agent_id=agent_id,
            description=f"{'Success' if attempt.success else 'Failed'}: {attempt.method[:150]}",
            payload={
                "success": attempt.success,
                "method": attempt.method,
                "lesson": attempt.lesson[:300] if attempt.lesson else "",
            },
        )

    def update_confidence(
        self, new_confidence: float, reason: str, agent_id: str = ""
    ) -> CognitiveEvent:
        """Update overall engagement confidence."""
        old = self.confidence
        self.confidence = max(0.0, min(1.0, new_confidence))
        return self._emit(
            CognitiveEventType.CONFIDENCE_CHANGED,
            agent_id=agent_id,
            description=f"Confidence {old:.2f} → {self.confidence:.2f}: {reason[:150]}",
            payload={"old_confidence": old, "new_confidence": self.confidence, "reason": reason},
        )

    def update_next_action(
        self, decision: NextBestActionDecision, agent_id: str = ""
    ) -> CognitiveEvent:
        """Update the next-best-action decision."""
        self.last_decision = decision
        self.next_best_action = decision.selected_action.action if decision.selected_action else ""
        return self._emit(
            CognitiveEventType.NEXT_ACTION_UPDATED,
            agent_id=agent_id,
            description=f"Next action: {self.next_best_action[:200]}",
            payload={
                "selected": decision.selected_action.model_dump() if decision.selected_action else {},
                "candidates_count": len(decision.candidate_actions),
                "reason": decision.reason[:300],
            },
        )

    def record_replan(self, trigger: str, reasoning: str, agent_id: str = "") -> CognitiveEvent:
        """Record a replanning event."""
        self.replan_count += 1
        return self._emit(
            CognitiveEventType.REPLAN_OCCURRED,
            agent_id=agent_id,
            description=f"Replan #{self.replan_count}: {trigger}",
            payload={"trigger": trigger, "reasoning": reasoning[:500], "count": self.replan_count},
        )

    # ============================================
    # Query Methods
    # ============================================

    def get_active_hypotheses(self) -> list[CognitiveHypothesis]:
        """Get hypotheses that are still being investigated."""
        active = {
            HypothesisLifecycle.PROPOSED,
            HypothesisLifecycle.CANDIDATE,
            HypothesisLifecycle.VALIDATING,
            HypothesisLifecycle.EVIDENCE_COLLECTED,
        }
        return [h for h in self.hypotheses if h.lifecycle in active]

    def get_unresolved_unknowns(self) -> list[Unknown]:
        """Get uncertainties that haven't been resolved."""
        return [u for u in self.unknowns if not u.resolved]

    def get_valid_assumptions(self) -> list[Assumption]:
        """Get assumptions that haven't been invalidated."""
        return [a for a in self.assumptions if a.is_valid]

    def get_active_facts(self) -> list[Fact]:
        """Get facts that haven't been superseded."""
        return [f for f in self.known_facts if not f.superseded_by]

    def get_failed_methods(self) -> set[str]:
        """Get methods that have already failed — avoid repeating."""
        return {a.method for a in self.failed_attempts}

    def can_replan(self) -> bool:
        """Check if replanning budget allows another replan."""
        return self.replan_count < self.budget.max_replans

    def is_within_budget(self) -> bool:
        """Check if engagement is within resource budget."""
        return (
            self.llm_calls_used < self.budget.max_llm_calls
            and self.tasks_completed + self.tasks_failed < self.budget.max_total_tasks
            and self.agents_spawned <= self.budget.max_agents_per_engagement
        )

    def add_competing_hypothesis(self, hyp: Any, agent_id: str = "") -> CognitiveEvent:
        """Record a competing hypothesis."""
        hyp.engagement_id = self.engagement_id
        hyp.tenant_id = self.tenant_id
        self.competing_hypotheses.append(hyp)
        return self._emit(
            CognitiveEventType.HYPOTHESIS_CREATED,
            object_id=hyp.id,
            object_type="competing_hypothesis",
            agent_id=agent_id,
            description=f"Competing Hypothesis: {hyp.statement[:150]}",
            payload={"statement": hyp.statement, "status": hyp.status},
        )

    def add_prediction(self, pred: Any, agent_id: str = "") -> CognitiveEvent:
        """Record a prediction before executing an action."""
        pred.engagement_id = self.engagement_id
        pred.tenant_id = self.tenant_id
        self.predictions.append(pred)
        return self._emit(
            CognitiveEventType.PREDICTION_MADE,
            object_id=pred.id,
            object_type="prediction",
            agent_id=agent_id,
            description=f"Prediction for '{pred.experiment_name}': {str(pred.expected_outcomes)[:100]}",
            payload={"task_id": pred.task_id, "confidence": pred.confidence},
        )

    def record_prediction_comparison(self, cmp: Any, agent_id: str = "") -> CognitiveEvent:
        """Record post-execution prediction vs actual outcome."""
        cmp.engagement_id = self.engagement_id
        cmp.tenant_id = self.tenant_id
        self.prediction_comparisons.append(cmp)
        return self._emit(
            CognitiveEventType.PREDICTION_EVALUATED,
            object_id=cmp.id,
            object_type="prediction_comparison",
            agent_id=agent_id,
            description=f"Prediction Error: {cmp.prediction_error:.2f} — {cmp.lesson[:100]}",
            payload={"prediction_error": cmp.prediction_error, "is_unexpected": cmp.is_unexpected},
        )

    def add_contradiction(self, ctrd: Any, agent_id: str = "") -> CognitiveEvent:
        """Record a detected conflict between observations/facts."""
        ctrd.engagement_id = self.engagement_id
        ctrd.tenant_id = self.tenant_id
        self.contradictions.append(ctrd)
        return self._emit(
            CognitiveEventType.CONTRADICTION_DETECTED,
            object_id=ctrd.id,
            object_type="contradiction",
            agent_id=agent_id,
            description=f"Contradiction [{ctrd.severity}]: '{ctrd.statement_a[:50]}' vs '{ctrd.statement_b[:50]}'",
            payload={"severity": ctrd.severity},
        )

    def resolve_contradiction(self, ctrd_id: str, notes: str, agent_id: str = "") -> CognitiveEvent:
        """Resolve a previously detected contradiction."""
        for c in self.contradictions:
            if c.id == ctrd_id:
                c.resolve(notes)
                break
        return self._emit(
            CognitiveEventType.CONTRADICTION_RESOLVED,
            object_id=ctrd_id,
            object_type="contradiction",
            agent_id=agent_id,
            description=f"Contradiction {ctrd_id} resolved: {notes[:100]}",
            payload={"notes": notes},
        )

    def add_decision_trace(self, trace: Any, agent_id: str = "") -> CognitiveEvent:
        """Record a structured 'Why this action?' decision trace."""
        self.decision_traces.append(trace)
        return self._emit(
            CognitiveEventType.DECISION_RECORDED,
            object_id=trace.decision_id,
            object_type="decision_trace",
            agent_id=agent_id,
            description=f"Selected: '{trace.selected_action}' — Reason: {trace.selection_reason[:100]}",
            payload={"selected": trace.selected_action, "info_gain": trace.expected_information_gain},
        )

    def set_stop_condition(self, condition: str, reason: str, agent_id: str = "") -> CognitiveEvent:
        """Record an explicit stop condition evaluation."""
        self.stop_condition = condition
        self.stop_reason = reason
        return self._emit(
            CognitiveEventType.STOP_CONDITION_EVALUATED,
            agent_id=agent_id,
            description=f"Stop Condition [{condition}]: {reason[:100]}",
            payload={"condition": condition, "reason": reason},
        )

    def get_active_contradictions(self) -> list[Any]:
        return [c for c in self.contradictions if not getattr(c, "resolved", False)]

    def get_active_competing_hypotheses(self) -> list[Any]:
        return [h for h in self.competing_hypotheses if getattr(h, "status", "") in ("proposed", "candidate", "validating")]

    def summary(self) -> dict[str, Any]:
        """Produce a concise summary for LLM context windows."""
        return {
            "goal": self.goal,
            "facts_count": len(self.get_active_facts()),
            "assumptions_count": len(self.get_valid_assumptions()),
            "active_hypotheses_count": len(self.get_active_hypotheses()) + len(self.get_active_competing_hypotheses()),
            "unresolved_unknowns_count": len(self.get_unresolved_unknowns()),
            "active_contradictions_count": len(self.get_active_contradictions()),
            "evidence_count": len(self.evidence),
            "failed_attempts_count": len(self.failed_attempts),
            "successful_attempts_count": len(self.successful_attempts),
            "confidence": self.confidence,
            "confidence_breakdown": self.confidence_breakdown,
            "next_best_action": self.next_best_action,
            "stop_condition": self.stop_condition,
            "replan_count": self.replan_count,
            "budget_remaining": {
                "replans": self.budget.max_replans - self.replan_count,
                "llm_calls": self.budget.max_llm_calls - self.llm_calls_used,
                "tasks": self.budget.max_total_tasks - (self.tasks_completed + self.tasks_failed),
            },
        }
