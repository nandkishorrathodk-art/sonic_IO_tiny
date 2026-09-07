"""
SONIC — Parallel Asynchronous Research Orchestrator
=====================================================
Coordinates concurrent specialist research agents ("Sab kaam at the same time"):
  - AsyncResearchOrchestrator with asyncio-native parallel execution
  - Shared blackboard / world model state
  - Dynamic decomposition & reactive specialist spawning
  - Priority queue scheduling & graceful cancellation mechanisms
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from sonic.logger import get_logger
from sonic.research.epistemic import (
    CompetingHypothesis,
    Unknown,
    UnknownStatus,
)
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
from sonic.research.specialist import (
    ApiSpecialist,
    AuthSpecialist,
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

logger = get_logger(__name__)


# =====================================================================
# 1. Observation Claims & Conflict Resolution Models
# =====================================================================

class ObservationClaim(BaseModel):
    """An asserted observation or state claim from a specialist agent."""
    claim_id: str = Field(default_factory=lambda: f"claim-{uuid.uuid4().hex[:8]}")
    entity: str                         # e.g., "target:443", "url:/login:auth_required", "host:10.0.0.1:port_80"
    state: Any                          # e.g., True, False, "open", "closed", "vulnerable", "secure"
    confidence: float = 0.5             # 0.0 to 1.0
    timestamp: float = Field(default_factory=time.time)
    source: str = ""                    # Specialist name
    evidence: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConflictRecord(BaseModel):
    """A detected contradiction between two specialist observations requiring falsification."""
    conflict_id: str = Field(default_factory=lambda: f"conflict-{uuid.uuid4().hex[:8]}")
    entity: str
    claim_a: ObservationClaim
    claim_b: ObservationClaim
    status: str = "unresolved"          # "unresolved", "falsification_scheduled", "resolved"
    evaluation: dict[str, Any] = Field(default_factory=dict)
    falsifier_agent_name: str = ""
    winning_claim: ObservationClaim | None = None
    resolution_notes: str = ""
    created_at: float = Field(default_factory=time.time)
    resolved_at: float | None = None


def is_contradictory(state_a: Any, state_b: Any) -> bool:
    """Determine if two observed states are contradictory."""
    if state_a == state_b:
        return False
    if isinstance(state_a, bool) and isinstance(state_b, bool):
        return state_a != state_b
    opposites = {
        ("open", "closed"),
        ("vulnerable", "secure"),
        ("vulnerable", "patched"),
        ("vulnerable", "not_vulnerable"),
        ("accessible", "blocked"),
        ("true", "false"),
        ("present", "absent"),
        ("enabled", "disabled"),
        ("valid", "invalid"),
        ("auth_required", "unauthenticated"),
        ("auth_required", "open_access"),
    }
    str_a = str(state_a).strip().lower()
    str_b = str(state_b).strip().lower()
    if str_a == str_b:
        return False
    for pos, neg in opposites:
        if (str_a == pos and str_b == neg) or (str_a == neg and str_b == pos):
            return True
    return True


# =====================================================================
# 2. Shared Blackboard State
# =====================================================================

class ResearchBlackboard:
    """
    Shared blackboard / world model representing accumulated research intelligence.
    Thread/async-safe repository updated by event bus subscriptions.
    Includes conflict resolution for contradictory specialist observations.
    """

    def __init__(self) -> None:
        self.targets: dict[str, TargetDiscoveredEvent] = {}
        self.endpoints: list[EndpointDiscoveredEvent] = []
        self.anomalies: list[AnomalyDetectedEvent] = []
        self.hypotheses: dict[str, HypothesisProposedEvent] = {}
        self.falsified_hypotheses: dict[str, HypothesisFalsifiedEvent] = {}
        self.verified_vulnerabilities: list[VulnerabilityVerifiedEvent] = []
        self.agent_states: dict[str, str] = {}
        self.state_history: list[ResearchStateChangedEvent] = []
        self.custom_data: dict[str, Any] = {}
        self.observations: dict[str, list[ObservationClaim]] = {}
        self.conflicts: list[ConflictRecord] = []
        self.active_workers: set[str] = set()
        self.failed_workers: set[str] = set()
        self.worker_failures: dict[str, list[dict[str, Any]]] = {}
        self.attack_graph: Any = None
        self._orchestrator: AsyncResearchOrchestrator | None = None
        self._event_bus: ResearchEventBus | None = None
        self._lock = asyncio.Lock()

    def attach_orchestrator(self, orchestrator: AsyncResearchOrchestrator) -> None:
        """Attach reference to orchestrator for proactive specialist dispatch."""
        self._orchestrator = orchestrator

    def attach_event_bus(self, event_bus: ResearchEventBus) -> None:
        """Attach reference to event bus for proactive event publishing."""
        self._event_bus = event_bus

    def _evaluate_conflict(
        self, claim_a: ObservationClaim, claim_b: ObservationClaim
    ) -> dict[str, Any]:
        """Evaluate confidence, timestamp recency, and determine priority for conflict resolution."""
        conf_delta = round(abs(claim_a.confidence - claim_b.confidence), 3)
        higher_conf = claim_a if claim_a.confidence >= claim_b.confidence else claim_b
        time_delta = round(abs(claim_b.timestamp - claim_a.timestamp), 3)
        more_recent = claim_b if claim_b.timestamp >= claim_a.timestamp else claim_a

        return {
            "entity": claim_a.entity,
            "confidence_a": claim_a.confidence,
            "confidence_b": claim_b.confidence,
            "confidence_delta": conf_delta,
            "higher_confidence_source": higher_conf.source,
            "timestamp_a": claim_a.timestamp,
            "timestamp_b": claim_b.timestamp,
            "recency_delta_seconds": time_delta,
            "more_recent_source": more_recent.source,
            "recommendation": (
                f"Contradiction detected on '{claim_a.entity}': '{claim_a.source}' asserts state {claim_a.state} "
                f"(conf: {claim_a.confidence}) while '{claim_b.source}' asserts state {claim_b.state} "
                f"(conf: {claim_b.confidence}). FalsificationSpecialist scheduled to establish ground truth."
            ),
        }

    def schedule_conflict_falsification(
        self,
        conflict: ConflictRecord,
        orchestrator: AsyncResearchOrchestrator | None = None,
    ) -> FalsificationSpecialist:
        """Schedule FalsificationSpecialist to resolve contradictory observations."""
        orch = orchestrator or self._orchestrator
        falsifier_name = f"Falsifier-{conflict.conflict_id}"
        falsifier = FalsificationSpecialist(
            name=falsifier_name,
            target_hypothesis_id=conflict.conflict_id,
            objective=f"Adversarially resolve conflict on {conflict.entity}: {conflict.claim_a.source} ({conflict.claim_a.state}) vs {conflict.claim_b.source} ({conflict.claim_b.state})",
            falsification_plan={
                "entity": conflict.entity,
                "conflict_id": conflict.conflict_id,
                "claim_a": conflict.claim_a.model_dump(),
                "claim_b": conflict.claim_b.model_dump(),
                "should_falsify": conflict.claim_a.confidence < conflict.claim_b.confidence,
            },
            priority=1,  # Highest priority for resolving epistemic contradictions
        )
        conflict.status = "falsification_scheduled"
        conflict.falsifier_agent_name = falsifier_name

        if orch is not None:
            orch.schedule_specialist(
                falsifier,
                context={
                    "hypothesis_id": conflict.conflict_id,
                    "statement": conflict.evaluation.get("recommendation", f"Resolve conflict on {conflict.entity}"),
                    "conflict_id": conflict.conflict_id,
                    "entity": conflict.entity,
                },
                priority=1,
            )

        if self._event_bus is not None:
            asyncio.create_task(
                self._event_bus.publish(
                    HypothesisProposedEvent(
                        source="BlackboardConflictResolver",
                        hypothesis_id=conflict.conflict_id,
                        statement=f"Conflict on {conflict.entity}: {conflict.claim_a.source} ({conflict.claim_a.state}) vs {conflict.claim_b.source} ({conflict.claim_b.state})",
                        vulnerability_class="EpistemicContradiction",
                        confidence=round((conflict.claim_a.confidence + conflict.claim_b.confidence) / 2, 2),
                        falsification_criteria=f"Discriminating test determines ground truth state between {conflict.claim_a.state} and {conflict.claim_b.state}",
                        target=conflict.entity,
                    )
                )
            )

        return falsifier

    async def assert_observation(
        self,
        entity: str,
        state: Any,
        confidence: float = 0.5,
        source: str = "",
        timestamp: float | None = None,
        evidence: Any = None,
        orchestrator: AsyncResearchOrchestrator | None = None,
    ) -> ConflictRecord | None:
        """
        Record a specialist's observation on an entity and resolve any contradictions.
        If specialist A asserts state X and specialist B asserts not-X, evaluate confidence,
        timestamp recency, and schedule FalsificationSpecialist to resolve the conflict.
        """
        async with self._lock:
            claim = ObservationClaim(
                entity=entity,
                state=state,
                confidence=confidence,
                source=source,
                timestamp=timestamp or time.time(),
                evidence=evidence,
            )

            existing_claims = self.observations.get(entity, [])
            for existing in existing_claims:
                if is_contradictory(existing.state, claim.state):
                    # Contradiction detected: Evaluate confidence, timestamp, and schedule FalsificationSpecialist
                    conflict = ConflictRecord(
                        entity=entity,
                        claim_a=existing,
                        claim_b=claim,
                        evaluation=self._evaluate_conflict(existing, claim),
                    )
                    self.conflicts.append(conflict)
                    self.schedule_conflict_falsification(conflict, orchestrator or self._orchestrator)
                    self.observations.setdefault(entity, []).append(claim)
                    return conflict

            self.observations.setdefault(entity, []).append(claim)
            return None

    def resolve_conflict(
        self,
        conflict_id: str,
        winning_claim_or_source: str = "",
        resolution_notes: str = "",
    ) -> bool:
        """Mark a conflict as resolved with rationale and winning claim."""
        for c in self.conflicts:
            if c.conflict_id == conflict_id:
                c.status = "resolved"
                c.resolution_notes = resolution_notes
                c.resolved_at = time.time()
                if winning_claim_or_source:
                    if winning_claim_or_source in (c.claim_a.source, c.claim_a.claim_id):
                        c.winning_claim = c.claim_a
                    elif winning_claim_or_source in (c.claim_b.source, c.claim_b.claim_id):
                        c.winning_claim = c.claim_b
                return True
        return False

    def get_conflicts(self) -> list[ConflictRecord]:
        return list(self.conflicts)

    def get_unresolved_conflicts(self) -> list[ConflictRecord]:
        return [c for c in self.conflicts if c.status != "resolved"]

    def record_worker_start(self, worker_name: str) -> None:
        """Record that a worker has begun execution."""
        self.active_workers.add(worker_name)
        self.failed_workers.discard(worker_name)
        self.agent_states[worker_name] = SpecialistState.RESEARCHING.value

    def record_worker_completion(
        self,
        worker_name: str,
        state: SpecialistState | str = SpecialistState.COMPLETED,
    ) -> None:
        """Record normal or terminal completion of a worker."""
        self.active_workers.discard(worker_name)
        st_val = state.value if isinstance(state, SpecialistState) else str(state)
        self.agent_states[worker_name] = st_val

    def record_worker_failure(
        self,
        worker_name: str,
        error: Any = "",
        reason: str = "",
        diagnostic: Any = None,
        substrate_issue: str = "",
        tool_issue: str = "",
        state: SpecialistState | str = SpecialistState.FAILED,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Record that a worker has failed, timed out, or been blocked.
        Provides diagnostic breakdown for the central brain.
        """
        self.active_workers.discard(worker_name)
        self.failed_workers.add(worker_name)
        st_val = state.value if isinstance(state, SpecialistState) else str(state)
        self.agent_states[worker_name] = st_val

        err_str = str(error)
        sub_issue = substrate_issue
        t_issue = tool_issue
        err_upper = err_str.upper()
        reason_upper = reason.upper()

        if not sub_issue:
            if any(
                k in err_upper or k in reason_upper
                for k in (
                    "PROVIDER_FAILURE",
                    "PROVIDER",
                    "SANDBOX",
                    "CONTAINER",
                    "DAEMON",
                    "EXIT 125",
                )
            ):
                sub_issue = "provider_failure"
            elif any(k in err_upper or k in reason_upper for k in ("TIMEOUT", "DEADLINE")):
                sub_issue = "timeout"
            elif any(
                k in err_upper or k in reason_upper
                for k in ("PERMISSION", "DENIED", "BLOCKED", "EGRESS", "EXIT 126")
            ):
                sub_issue = "permission_denied"
            else:
                sub_issue = "substrate_unknown"

        if not t_issue:
            if "tool" in err_str.lower():
                t_issue = "tool_execution_error"
            elif "network" in err_str.lower() or "connection" in err_str.lower() or "port" in err_str.lower():
                t_issue = "network_connection_error"
            elif "timeout" in err_str.lower() or "timeout" in reason.lower():
                t_issue = "tool_timeout"
            else:
                t_issue = "execution_error"

        clean_reason = reason or ("PROVIDER_FAILURE" if st_val == "blocked" else "EXECUTION_FAILURE")
        if ":" in clean_reason:
            prefix = clean_reason.split(":", 1)[0].strip()
            if prefix in (
                "TIMEOUT",
                "PROVIDER_FAILURE",
                "BLOCKED",
                "BUDGET_EXHAUSTED",
                "FAILED",
                "EXECUTION_FAILURE",
                "PERMISSION_FAILURE",
                "POLICY_BLOCK",
            ):
                clean_reason = prefix

        record = {
            "worker": worker_name,
            "specialist": worker_name,
            "agent_name": worker_name,
            "error": err_str,
            "error_type": type(error).__name__ if isinstance(error, BaseException) else "Exception",
            "reason": clean_reason,
            "substrate_issue": sub_issue,
            "tool_issue": t_issue,
            "diagnostic": diagnostic or err_str or reason,
            "state": st_val,
            "timestamp": time.time(),
            "context": context or {},
        }
        self.worker_failures.setdefault(worker_name, []).append(record)
        return record

    def get_active_workers(self) -> set[str]:
        """Return the set of currently active workers."""
        return set(self.active_workers)

    def get_failed_workers(self) -> set[str]:
        """Return the set of workers that failed or were blocked."""
        return set(self.failed_workers)

    def get_worker_failures(
        self, worker_name: str | None = None
    ) -> list[dict[str, Any]] | dict[str, list[dict[str, Any]]]:
        """Return failures for a specific worker or all workers."""
        if worker_name is not None:
            return list(self.worker_failures.get(worker_name, []))
        return {k: list(v) for k, v in self.worker_failures.items()}

    def diagnose_failure(self, worker_name: str) -> dict[str, Any] | None:
        """
        Diagnose the failure of a worker for central brain inspection.
        Returns failure reason, substrate/tool issues, and state.
        """
        records = self.worker_failures.get(worker_name, [])
        if not records:
            if worker_name in self.failed_workers:
                return {
                    "worker": worker_name,
                    "specialist": worker_name,
                    "agent_name": worker_name,
                    "state": self.agent_states.get(worker_name, "failed"),
                    "reason": "UNKNOWN_FAILURE",
                    "substrate_issue": "unknown",
                    "tool_issue": "unknown",
                    "diagnostic": "No diagnostic details recorded",
                    "can_resume": True,
                }
            return None
        latest = records[-1]
        return {
            "worker": worker_name,
            "specialist": worker_name,
            "agent_name": worker_name,
            "state": latest.get("state"),
            "reason": latest.get("reason"),
            "error": latest.get("error"),
            "substrate_issue": latest.get("substrate_issue"),
            "tool_issue": latest.get("tool_issue"),
            "diagnostic": latest.get("diagnostic"),
            "can_resume": True,
            "timestamp": latest.get("timestamp"),
        }

    def clear_worker_failure(self, worker_name: str) -> None:
        """Clear failure status when resuming a specialist."""
        self.failed_workers.discard(worker_name)

    def attach_attack_graph(self, attack_graph: Any) -> None:
        """Attach attack graph to blackboard to preserve DAG structure across specialist lifecycle."""
        self.attack_graph = attack_graph

    def get_attack_graph(self) -> Any:
        """Return attached attack graph if available."""
        return self.attack_graph

    async def record_event(self, event: ResearchEvent) -> None:
        """Categorize and store events into the blackboard."""
        async with self._lock:
            if isinstance(event, TargetDiscoveredEvent):
                # Index by pure target and by target:port
                self.targets[event.target] = event
                if event.port:
                    self.targets[f"{event.target}:{event.port}"] = event
            elif isinstance(event, EndpointDiscoveredEvent):
                if not any(
                    ep.url == event.url and ep.method == event.method for ep in self.endpoints
                ):
                    self.endpoints.append(event)
            elif isinstance(event, AnomalyDetectedEvent):
                self.anomalies.append(event)
            elif isinstance(event, HypothesisProposedEvent):
                self.hypotheses[event.hypothesis_id] = event
            elif isinstance(event, HypothesisFalsifiedEvent):
                self.falsified_hypotheses[event.hypothesis_id] = event
            elif isinstance(event, VulnerabilityVerifiedEvent):
                self.verified_vulnerabilities.append(event)
            elif isinstance(event, ResearchStateChangedEvent):
                self.agent_states[event.agent_name] = event.new_state
                self.state_history.append(event)
                if event.new_state == SpecialistState.RESEARCHING.value:
                    self.active_workers.add(event.agent_name)
                    self.failed_workers.discard(event.agent_name)
                elif event.new_state in (SpecialistState.FAILED.value, SpecialistState.BLOCKED.value):
                    self.active_workers.discard(event.agent_name)
                    self.failed_workers.add(event.agent_name)
                    if event.agent_name not in self.worker_failures:
                        self.record_worker_failure(
                            worker_name=event.agent_name,
                            error=event.reason,
                            reason="PROVIDER_FAILURE" if event.new_state == SpecialistState.BLOCKED.value else (event.reason or "FAILED"),
                            diagnostic=event.reason,
                            state=event.new_state,
                        )
                elif event.new_state == SpecialistState.COMPLETED.value:
                    self.active_workers.discard(event.agent_name)

    def get_endpoints(self) -> list[EndpointDiscoveredEvent]:
        return list(self.endpoints)

    def get_hypotheses(self) -> list[HypothesisProposedEvent]:
        return list(self.hypotheses.values())

    def get_active_hypotheses(self) -> list[HypothesisProposedEvent]:
        """Return hypotheses that have not yet been disproved."""
        falsified_ids = set(self.falsified_hypotheses.keys())
        return [h for h in self.hypotheses.values() if h.hypothesis_id not in falsified_ids]

    def get_verified_vulnerabilities(self) -> list[VulnerabilityVerifiedEvent]:
        return list(self.verified_vulnerabilities)

    def get_targets(self) -> list[TargetDiscoveredEvent]:
        return list(self.targets.values())

    def snapshot(self) -> dict[str, Any]:
        """Return serialized summary snapshot of the blackboard."""
        return {
            "targets_count": len(self.targets),
            "endpoints_count": len(self.endpoints),
            "anomalies_count": len(self.anomalies),
            "hypotheses_count": len(self.hypotheses),
            "falsified_hypotheses_count": len(self.falsified_hypotheses),
            "verified_vulnerabilities_count": len(self.verified_vulnerabilities),
            "conflicts_count": len(self.conflicts),
            "unresolved_conflicts_count": len(self.get_unresolved_conflicts()),
            "agent_states": dict(self.agent_states),
            "active_workers": list(self.active_workers),
            "failed_workers": list(self.failed_workers),
            "worker_failures": {k: list(v) for k, v in self.worker_failures.items()},
        }


# =====================================================================
# 2. Dynamic Decomposition Rules
# =====================================================================

class DecompositionRule:
    """Trigger rule that spawns new specialists in response to specific events."""

    def __init__(
        self,
        name: str,
        matcher: Callable[[ResearchEvent], bool],
        spawn_factory: Callable[[ResearchEvent, ResearchBlackboard], list[SpecialistAgent]],
    ) -> None:
        self.name = name
        self.matcher = matcher
        self.spawn_factory = spawn_factory


def default_decomposition_rules() -> list[DecompositionRule]:
    """
    Standard dynamic decomposition rules:
      1. Network port 80/8080/443 -> WebSpecialist
      2. Web endpoint with /api/ or graphql -> ApiSpecialist
      3. Endpoint or anomaly with auth/login/token/user -> AuthSpecialist
      4. Proposed hypothesis -> FalsificationSpecialist
    """

    def match_network_web(event: ResearchEvent) -> bool:
        if isinstance(event, TargetDiscoveredEvent):
            return event.port in (80, 443, 8080, 8443, 3000, 5000) or event.service in (
                "http",
                "http-alt",
                "https",
            )
        if isinstance(event, EndpointDiscoveredEvent):
            return event.url.startswith("http://") or event.url.startswith("https://")
        return False

    def spawn_network_web(event: ResearchEvent, bb: ResearchBlackboard) -> list[SpecialistAgent]:
        target = ""
        if isinstance(event, TargetDiscoveredEvent):
            port_str = f":{event.port}" if event.port and event.port not in (80, 443) else ""
            scheme = "https" if event.port == 443 or event.service == "https" else "http"
            target = f"{scheme}://{event.target}{port_str}"
        elif isinstance(event, EndpointDiscoveredEvent):
            target = event.url

        return [
            WebSpecialist(
                name=f"WebSpecialist-{target}",
                target_url=target,
                objective=f"Map web surface and forms for {target}",
            )
        ]

    def match_api(event: ResearchEvent) -> bool:
        if isinstance(event, EndpointDiscoveredEvent):
            url_lower = event.url.lower()
            return any(k in url_lower for k in ("/api/", "/v1/", "/v2/", "graphql", ".json"))
        return False

    def spawn_api(event: ResearchEvent, bb: ResearchBlackboard) -> list[SpecialistAgent]:
        if isinstance(event, EndpointDiscoveredEvent):
            return [
                ApiSpecialist(
                    name=f"ApiSpecialist-{event.url}",
                    target_url=event.url,
                    objective=f"Deeply inspect API schema and parameters on {event.url}",
                )
            ]
        return []

    def match_auth(event: ResearchEvent) -> bool:
        if isinstance(event, EndpointDiscoveredEvent):
            url_lower = event.url.lower()
            return (
                any(
                    k in url_lower
                    for k in (
                        "/auth",
                        "/login",
                        "/token",
                        "/user",
                        "/me",
                        "/session",
                        "/oauth",
                    )
                )
                or event.auth_required is True
            )
        return False

    def spawn_auth(event: ResearchEvent, bb: ResearchBlackboard) -> list[SpecialistAgent]:
        if isinstance(event, EndpointDiscoveredEvent):
            return [
                AuthSpecialist(
                    name=f"AuthSpecialist-{event.url}",
                    target_url=event.url,
                    objective=f"Evaluate authentication integrity and token boundaries for {event.url}",
                )
            ]
        return []

    def match_falsification(event: ResearchEvent) -> bool:
        return isinstance(event, HypothesisProposedEvent)

    def spawn_falsification(event: ResearchEvent, bb: ResearchBlackboard) -> list[SpecialistAgent]:
        if isinstance(event, HypothesisProposedEvent):
            return [
                FalsificationSpecialist(
                    name=f"FalsificationSpecialist-{event.hypothesis_id}",
                    target_hypothesis_id=event.hypothesis_id,
                    objective=f"Adversarially challenge hypothesis: '{event.statement}'",
                )
            ]
        return []

    def match_business_logic(event: ResearchEvent) -> bool:
        if isinstance(event, EndpointDiscoveredEvent):
            url_lower = event.url.lower()
            return any(
                k in url_lower
                for k in (
                    "/cart",
                    "/checkout",
                    "/pay",
                    "/order",
                    "/purchase",
                    "/billing",
                    "/transfer",
                    "/discount",
                    "/coupon",
                )
            )
        return False

    def spawn_business_logic(event: ResearchEvent, bb: ResearchBlackboard) -> list[SpecialistAgent]:
        if isinstance(event, EndpointDiscoveredEvent):
            return [
                BusinessLogicSpecialist(
                    name=f"BusinessLogicSpecialist-{event.url}",
                    target_url=event.url,
                    objective=f"Analyze workflow state machines and race conditions on {event.url}",
                )
            ]
        return []

    def match_cloud(event: ResearchEvent) -> bool:
        if isinstance(event, TargetDiscoveredEvent):
            t_lower = event.target.lower()
            return (
                event.target_type == "cloud_resource"
                or "169.254.169.254" in t_lower
                or any(k in t_lower for k in ("s3.", "amazonaws.com", "blob.core.windows.net", "storage.googleapis.com"))
            )
        return False

    def spawn_cloud(event: ResearchEvent, bb: ResearchBlackboard) -> list[SpecialistAgent]:
        if isinstance(event, TargetDiscoveredEvent):
            return [
                CloudSpecialist(
                    name=f"CloudSpecialist-{event.target}",
                    target_host=event.target,
                    objective=f"Evaluate cloud metadata and bucket permissions for {event.target}",
                )
            ]
        return []

    return [
        DecompositionRule("NetworkToWeb", match_network_web, spawn_network_web),
        DecompositionRule("WebToApi", match_api, spawn_api),
        DecompositionRule("WebToAuth", match_auth, spawn_auth),
        DecompositionRule("WebToBusinessLogic", match_business_logic, spawn_business_logic),
        DecompositionRule("TargetToCloud", match_cloud, spawn_cloud),
        DecompositionRule("HypothesisToFalsification", match_falsification, spawn_falsification),
    ]


# =====================================================================
# 3. Execution Result
# =====================================================================

class ResearchResult(BaseModel):
    """Structured report returned by the orchestrator after a parallel research run."""
    success: bool = True
    completed_specialists: int = 0
    total_specialists: int = 0
    status: str = "completed"  # "completed", "cancelled", "timed_out", "failed"
    duration_seconds: float = 0.0
    parallel_wall_time: float = 0.0
    sum_of_task_times: float = 0.0
    parallelism_factor: float = 1.0
    timeline_traces: list[dict[str, Any]] = Field(default_factory=list)
    unknowns: list[dict[str, Any]] = Field(default_factory=list)
    unresolved_hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    information_gain_priorities: list[dict[str, Any]] = Field(default_factory=list)
    total_events: int = 0
    specialists_executed: list[str] = Field(default_factory=list)
    specialists_succeeded: list[str] = Field(default_factory=list)
    specialists_blocked: list[str] = Field(default_factory=list)
    specialists_failed: list[str] = Field(default_factory=list)
    blackboard_summary: dict[str, Any] = Field(default_factory=dict)
    verified_vulnerabilities_count: int = 0
    falsified_hypotheses_count: int = 0
    conflicts_count: int = 0
    resolved_conflicts_count: int = 0


# =====================================================================
# 4. Asynchronous Research Orchestrator
# =====================================================================

class AsyncResearchOrchestrator:
    """
    Orchestrates parallel research specialists using non-blocking asynchronous execution.

    Capabilities:
      - Concurrently schedules SpecialistAgents with configurable concurrency limits
      - Priority queue management for ordering critical vs exploratory tasks
      - Shared blackboard state synced in real-time with the event bus
      - Dynamic decomposition: events trigger spawning of downstream specialists
      - Epistemic inquiry: dynamically identifies unknowns and unresolved hypotheses
      - Information-gain prioritized dispatch
      - Fine-grained cancellation (per-agent or global cancel_all)
      - Timeline traces and parallel concurrency metrics (wall time, task sum, parallelism factor)
    """

    def __init__(
        self,
        event_bus: ResearchEventBus | None = None,
        blackboard: ResearchBlackboard | None = None,
        max_concurrent_specialists: int = 10,
        max_total_specialists: int = 50,
        decomposition_rules: list[DecompositionRule] | None = None,
    ) -> None:
        self.event_bus = event_bus or ResearchEventBus()
        self.blackboard = blackboard or ResearchBlackboard()
        self.blackboard.attach_orchestrator(self)
        self.blackboard.attach_event_bus(self.event_bus)
        self.max_concurrent_specialists = max_concurrent_specialists
        self.max_total_specialists = max_total_specialists
        self.decomposition_rules = (
            decomposition_rules
            if decomposition_rules is not None
            else default_decomposition_rules()
        )

        # Priority queue stores tuples of: (priority, seq_id, specialist, context)
        self._priority_queue: asyncio.PriorityQueue[
            tuple[int, int, SpecialistAgent, dict[str, Any]]
        ] = asyncio.PriorityQueue()
        self._seq_counter = 0

        # State tracking
        self._active_tasks: dict[str, asyncio.Task[Any]] = {}
        self._active_specialists: dict[str, SpecialistAgent] = {}
        self._all_specialists: dict[str, SpecialistAgent] = {}
        self._spawned_keys: set[str] = set()
        self.task_traces: list[dict[str, Any]] = []
        self._task_counter: int = 0

        self._cancelled = False
        self._semaphore = asyncio.Semaphore(max_concurrent_specialists)
        self._new_work_event = asyncio.Event()

        # Connect blackboard & decomposition listener to event bus
        self.event_bus.subscribe("*", self._handle_bus_event)

    def register_decomposition_rule(
        self,
        rule_or_event_type: type[ResearchEvent] | str | DecompositionRule,
        spawn_factory_or_matcher: Any = None,
        spawn_factory: Any = None,
    ) -> None:
        """
        Register a custom dynamic decomposition rule.
        Supports:
          - register_decomposition_rule(DecompositionRule(...))
          - register_decomposition_rule(EventClass, spawn_fn)
          - register_decomposition_rule(name, matcher, spawn_factory)
        """
        if isinstance(rule_or_event_type, DecompositionRule):
            self.decomposition_rules.append(rule_or_event_type)
        elif isinstance(rule_or_event_type, type) and issubclass(rule_or_event_type, ResearchEvent):
            event_type = rule_or_event_type
            factory_fn = spawn_factory_or_matcher

            def wrapped_factory(evt: ResearchEvent, bb: ResearchBlackboard) -> list[SpecialistAgent]:
                res = factory_fn(evt)
                if res is None:
                    return []
                if isinstance(res, list):
                    return res
                return [res]

            self.decomposition_rules.append(
                DecompositionRule(
                    name=event_type.__name__,
                    matcher=lambda e, t=event_type: isinstance(e, t),
                    spawn_factory=wrapped_factory,
                )
            )
        elif isinstance(rule_or_event_type, str):
            self.decomposition_rules.append(
                DecompositionRule(
                    name=rule_or_event_type,
                    matcher=spawn_factory_or_matcher,
                    spawn_factory=spawn_factory,
                )
            )

    async def _handle_bus_event(self, event: ResearchEvent) -> None:
        """Record event in blackboard and trigger dynamic decomposition."""
        await self.blackboard.record_event(event)

        # If already cancelled or max specialist cap reached, skip spawning
        if self._cancelled or len(self._all_specialists) >= self.max_total_specialists:
            return

        # Check decomposition triggers
        for rule in list(self.decomposition_rules):
            try:
                if rule.matcher(event):
                    new_specialists = rule.spawn_factory(event, self.blackboard)
                    for spec in new_specialists:
                        dedup_key = f"{spec.__class__.__name__}:{spec.name}:{spec.objective}"
                        if dedup_key not in self._spawned_keys:
                            self._spawned_keys.add(dedup_key)
                            context = self._derive_context_from_event(event)
                            self.schedule_specialist(spec, context=context)
            except Exception as ex:
                logger.warning(
                    "decomposition_rule_error",
                    rule=rule.name,
                    event_type=event.__class__.__name__,
                    error=str(ex),
                )

    def _derive_context_from_event(self, event: ResearchEvent) -> dict[str, Any]:
        """Derive relevant context dictionary from an event for spawned specialists."""
        context: dict[str, Any] = {}
        if isinstance(event, TargetDiscoveredEvent):
            context["target"] = event.target
            context["target_url"] = (
                f"http://{event.target}:{event.port}" if event.port else f"http://{event.target}"
            )
            context["port"] = event.port
            context["service"] = event.service
        elif isinstance(event, EndpointDiscoveredEvent):
            context["target"] = event.url
            context["target_url"] = event.url
            context["url"] = event.url
            context["params"] = event.params
        elif isinstance(event, HypothesisProposedEvent):
            context["hypothesis_id"] = event.hypothesis_id
            context["statement"] = event.statement
            context["vulnerability_class"] = event.vulnerability_class
            context["target"] = event.target
            context["hypotheses"] = [
                {
                    "id": event.hypothesis_id,
                    "statement": event.statement,
                    "vulnerability_class": event.vulnerability_class,
                }
            ]
        elif isinstance(event, AnomalyDetectedEvent):
            context["target"] = event.target
            context["anomaly"] = event.description or event.observation
        return context

    def schedule_specialist(
        self,
        specialist: SpecialistAgent,
        context: dict[str, Any] | None = None,
        priority: int | None = None,
    ) -> None:
        """Enqueue a specialist into the priority queue."""
        if self._cancelled:
            return

        p = priority if priority is not None else specialist.priority
        self._seq_counter += 1
        self._all_specialists[specialist.name] = specialist
        self._priority_queue.put_nowait((p, self._seq_counter, specialist, context or {}))
        self._new_work_event.set()

    def cancel_all(self) -> None:
        """Cancel all pending and active specialist executions."""
        self._cancelled = True
        logger.info("orchestrator_cancelling_all")

        # Drain priority queue
        while not self._priority_queue.empty():
            try:
                _, _, spec, _ = self._priority_queue.get_nowait()
                spec.cancel()
                self._priority_queue.task_done()
            except asyncio.QueueEmpty:
                break

        # Cancel active specialists and their tasks
        for spec in list(self._active_specialists.values()):
            spec.cancel()
        for task in list(self._active_tasks.values()):
            if not task.done():
                task.cancel()

        self._new_work_event.set()

    def cancel_agent(self, agent_name: str) -> bool:
        """Cancel a specific agent by name."""
        spec = self._active_specialists.get(agent_name) or self._all_specialists.get(agent_name)
        if spec:
            spec.cancel()
            task = self._active_tasks.get(agent_name)
            if task and not task.done():
                task.cancel()
            return True
        return False

    def resume_specialist(
        self,
        specialist_name_or_agent: str | SpecialistAgent,
        context: dict[str, Any] | None = None,
        reset_budget: bool = True,
        priority: int | None = None,
        investigation_fn: Callable[..., Any] | None = None,
    ) -> SpecialistAgent:
        """
        Restart or resume a failed/blocked specialist using preserved research state on blackboard.
        Preserves all previous findings, discoveries, attack graph nodes, and active tasks.
        """
        if isinstance(specialist_name_or_agent, SpecialistAgent):
            specialist = specialist_name_or_agent
            name = specialist.name
        else:
            name = str(specialist_name_or_agent)
            specialist = self._all_specialists.get(name)
            if specialist is None:
                for s_name, s_agent in self._all_specialists.items():
                    if s_name == name or s_agent.__class__.__name__ == name or s_name.startswith(name):
                        specialist = s_agent
                        name = s_name
                        break
            if specialist is None:
                raise ValueError(f"Specialist '{name}' not found in orchestrator specialists registry.")

        # 1. Reset lifecycle state and cancellation flags
        specialist.state = SpecialistState.IDLE
        specialist._cancelled = False
        specialist._cancel_event.clear()
        specialist.last_error = None
        specialist.failure_reason = None
        specialist.failure_diagnostic = None
        specialist.state_reason = ""
        if investigation_fn is not None:
            specialist._investigation_fn = investigation_fn

        if reset_budget:
            specialist.budget.actions_used = 0
            specialist.budget.tokens_used = 0
            specialist.budget.start_time = None

        # 2. Update blackboard state
        self.blackboard.clear_worker_failure(name)
        self.blackboard.agent_states[name] = SpecialistState.IDLE.value

        # 3. Cleanly clear any previous active task reference
        existing_task = self._active_tasks.pop(name, None)
        if existing_task and not existing_task.done():
            existing_task.cancel()
        self._active_specialists.pop(name, None)

        # 4. Prepare preserved context enriched with accumulated blackboard state
        resumed_context: dict[str, Any] = {
            "targets": self.blackboard.get_targets(),
            "endpoints": [ep.model_dump() for ep in self.blackboard.endpoints],
            "active_hypotheses": [h.model_dump() for h in self.blackboard.get_active_hypotheses()],
            "resumed": True,
        }
        if context:
            resumed_context.update(context)

        # 5. Enqueue into priority queue and notify orchestrator loop
        self.schedule_specialist(
            specialist,
            context=resumed_context,
            priority=priority if priority is not None else specialist.priority,
        )

        logger.info("specialist_resumed", specialist=name, priority=priority)
        return specialist

    def formulate_unknowns(self) -> list[Unknown]:
        """
        Formulate 'What is still unknown?' by analyzing current blackboard state:
        identifying uncovered endpoints, untested authentication boundaries,
        unmapped attack surfaces, and unresolved contradictions.
        """
        unknowns: list[Unknown] = []

        # 1. Unmapped targets without discovered endpoints
        endpoints_urls = {ep.url for ep in self.blackboard.endpoints}
        for target in self.blackboard.targets.values():
            has_endpoint = any(target.target in url for url in endpoints_urls)
            if not has_endpoint:
                unknowns.append(
                    Unknown(
                        question=f"What web endpoints and application routes are exposed on target {target.target}:{target.port or 'default'}?",
                        context=f"Target {target.target} discovered as {target.service or 'service'} but routes unmapped.",
                        category="network_web",
                        importance=0.85,
                        confidence_in_current_answer=0.1,
                        possible_actions=["WebSpecialist crawl", "ApiSpecialist probe"],
                    )
                )

        # 2. Endpoints with unverified authentication
        for ep in self.blackboard.endpoints:
            if ep.auth_required is None:
                unknowns.append(
                    Unknown(
                        question=f"Does endpoint {ep.method} {ep.url} require authentication or allow public/guest access?",
                        context=f"Endpoint discovered with params {ep.params}, auth requirements unknown.",
                        category="authorization",
                        importance=0.90,
                        confidence_in_current_answer=0.2,
                        possible_actions=["AuthSpecialist token test", "ApiSpecialist schema probe"],
                    )
                )

        # 3. Cloud resources with unverified IAM / storage permissions
        for target in self.blackboard.targets.values():
            if target.target_type == "cloud_resource" or "s3" in target.target or "169.254" in target.target:
                unknowns.append(
                    Unknown(
                        question=f"Are cloud metadata (IMDS) or bucket ACLs on {target.target} publicly accessible or leak credentials?",
                        context=f"Cloud target {target.target} identified without full privilege audit.",
                        category="cloud_infrastructure",
                        importance=0.95,
                        confidence_in_current_answer=0.15,
                        possible_actions=["CloudSpecialist bucket audit", "CloudSpecialist IMDS probe"],
                    )
                )

        # 4. Unresolved contradictions in blackboard
        for conflict in self.blackboard.get_unresolved_conflicts():
            unknowns.append(
                Unknown(
                    question=f"What is the true ground-truth state of {conflict.entity} given contradictory specialist claims?",
                    context=(
                        f"Conflict {conflict.conflict_id}: {conflict.claim_a.source} asserts {conflict.claim_a.state} "
                        f"vs {conflict.claim_b.source} asserts {conflict.claim_b.state}."
                    ),
                    category="contradiction",
                    importance=0.98,
                    confidence_in_current_answer=0.0,
                    possible_actions=["FalsificationSpecialist discriminating experiment"],
                )
            )

        return unknowns

    def get_unresolved_hypotheses(self) -> list[HypothesisProposedEvent]:
        """
        Formulate 'What hypotheses are unresolved?'
        Returns active hypotheses that have neither been disproved nor confirmed as verified vulnerabilities.
        """
        falsified_ids = set(self.blackboard.falsified_hypotheses.keys())
        verified_titles = {v.title.lower() for v in self.blackboard.verified_vulnerabilities}
        verified_classes = {v.vulnerability_class.lower() for v in self.blackboard.verified_vulnerabilities}

        unresolved = []
        for hypo in self.blackboard.hypotheses.values():
            if hypo.hypothesis_id in falsified_ids:
                continue
            stmt_lower = hypo.statement.lower()
            cls_lower = hypo.vulnerability_class.lower()
            if any(v in stmt_lower for v in verified_titles) or (cls_lower and cls_lower in verified_classes):
                continue
            unresolved.append(hypo)
        return unresolved

    def prioritize_by_information_gain(self) -> list[dict[str, Any]]:
        """
        Prioritize investigations by Information Gain:
        Information gain is highest for:
          1. Contradictions (resolving them eliminates false assumptions from world model)
          2. Hypotheses with maximum entropy (confidence near 0.5 where outcome is most uncertain)
          3. High-importance unknowns with low current confidence
        """
        priorities: list[dict[str, Any]] = []

        # 1. Unresolved conflicts
        for conflict in self.blackboard.get_unresolved_conflicts():
            priorities.append({
                "type": "conflict",
                "id": conflict.conflict_id,
                "target": conflict.entity,
                "description": f"Contradiction: {conflict.claim_a.source} vs {conflict.claim_b.source} on {conflict.entity}",
                "information_gain": 0.99,  # Resolving contradiction gives maximum epistemic value
                "action": "schedule_falsification",
            })

        # 2. Unresolved hypotheses
        for hypo in self.get_unresolved_hypotheses():
            # Uncertainty entropy metric: 1.0 when confidence=0.5, lower as confidence approaches 0 or 1
            uncertainty = 1.0 - 2.0 * abs(hypo.confidence - 0.5)
            info_gain = round(0.5 + 0.5 * uncertainty, 3)
            priorities.append({
                "type": "hypothesis",
                "id": hypo.hypothesis_id,
                "target": hypo.target or hypo.vulnerability_class,
                "description": hypo.statement,
                "confidence": hypo.confidence,
                "information_gain": info_gain,
                "action": "adversarial_falsification",
            })

        # 3. Unknowns
        for unk in self.formulate_unknowns():
            gain = round(unk.importance * (1.0 - unk.confidence_in_current_answer), 3)
            priorities.append({
                "type": "unknown",
                "id": unk.id,
                "target": unk.category,
                "description": unk.question,
                "information_gain": gain,
                "action": unk.possible_actions[0] if unk.possible_actions else "investigate",
            })

        # Sort descending by information gain
        priorities.sort(key=lambda x: x["information_gain"], reverse=True)
        return priorities

    async def run(
        self,
        initial_specialists: list[SpecialistAgent] | None = None,
        initial_context: dict[str, Any] | None = None,
        timeout: float | None = None,
        timeout_seconds: float | None = None,
    ) -> ResearchResult:
        """
        Execute concurrent specialist research until all tasks finish or limits are hit.
        Uses non-blocking asynchronous dispatch with priority ordering and epistemic unknown formulation.
        """
        effective_timeout = timeout_seconds if timeout_seconds is not None else timeout
        start_time = time.time()
        self._cancelled = False
        self.task_traces.clear()
        self._task_counter = 0

        # Schedule initial specialists
        if initial_specialists:
            for spec in initial_specialists:
                dedup_key = f"{spec.__class__.__name__}:{spec.name}:{spec.objective}"
                self._spawned_keys.add(dedup_key)
                self.schedule_specialist(spec, context=initial_context or {})

        status = "completed"

        async def _execution_loop() -> None:
            nonlocal status
            while not self._cancelled:
                # 1. If no items in queue and nothing running, check epistemic unknowns before completing
                if self._priority_queue.empty() and len(self._active_tasks) == 0:
                    prioritized_agenda = self.prioritize_by_information_gain()
                    dispatched = False
                    for item in prioritized_agenda:
                        if len(self._all_specialists) >= self.max_total_specialists:
                            break
                        dedup_agenda_key = f"agenda:{item['type']}:{item['id']}"
                        if dedup_agenda_key not in self._spawned_keys:
                            self._spawned_keys.add(dedup_agenda_key)
                            if item["type"] == "conflict":
                                conflict = next(
                                    (c for c in self.blackboard.conflicts if c.conflict_id == item["id"]),
                                    None,
                                )
                                if conflict and conflict.status != "resolved":
                                    self.blackboard.schedule_conflict_falsification(conflict, self)
                                    dispatched = True
                                    break
                            elif item["type"] == "hypothesis":
                                falsifier = FalsificationSpecialist(
                                    name=f"Falsifier-{item['id']}",
                                    target_hypothesis_id=item["id"],
                                    objective=f"Adversarially challenge unresolved hypothesis: '{item['description']}'",
                                    priority=3,
                                )
                                self.schedule_specialist(
                                    falsifier,
                                    context={
                                        "hypothesis_id": item["id"],
                                        "statement": item["description"],
                                    },
                                )
                                dispatched = True
                                break
                    if dispatched:
                        continue
                    break

                # 2. If queue is empty but active tasks are still running, wait for state change
                if self._priority_queue.empty():
                    self._new_work_event.clear()
                    task_futures = list(self._active_tasks.values())
                    if task_futures:
                        wait_tasks = [asyncio.ensure_future(self._new_work_event.wait())]
                        done, pending = await asyncio.wait(
                            task_futures + wait_tasks,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for p in pending:
                            if p in wait_tasks:
                                p.cancel()
                    else:
                        await self._new_work_event.wait()
                    continue

                # 3. If concurrency permits, launch next specialist from priority queue
                if len(self._active_tasks) < self.max_concurrent_specialists:
                    try:
                        _, _, specialist, ctx = self._priority_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        continue

                    # Launch agent execution task
                    task = asyncio.create_task(
                        self._execute_specialist_wrapper(specialist, ctx)
                    )
                    self._active_tasks[specialist.name] = task
                    self._active_specialists[specialist.name] = specialist

                    def _on_done(t: asyncio.Task[Any], name: str = specialist.name) -> None:
                        self._active_tasks.pop(name, None)
                        self._active_specialists.pop(name, None)
                        self._new_work_event.set()

                    task.add_done_callback(_on_done)
                else:
                    self._new_work_event.clear()
                    await asyncio.wait(
                        list(self._active_tasks.values()),
                        return_when=asyncio.FIRST_COMPLETED,
                    )

        try:
            if effective_timeout is not None and effective_timeout > 0:
                try:
                    async with asyncio.timeout(effective_timeout):
                        await _execution_loop()
                except TimeoutError:
                    logger.info("orchestrator_timeout_reached", timeout=effective_timeout)
                    status = "timed_out"
                    self.cancel_all()
            else:
                await _execution_loop()

        except asyncio.CancelledError:
            status = "cancelled"
            self.cancel_all()
            raise

        except Exception as ex:
            logger.error("orchestrator_run_error", error=str(ex))
            status = "failed"
            self.cancel_all()
            raise

        finally:
            if self._active_tasks:
                await asyncio.gather(*list(self._active_tasks.values()), return_exceptions=True)

        duration = time.time() - start_time
        if self._cancelled and status != "timed_out":
            status = "cancelled"

        # Tally outcomes
        executed = list(self._all_specialists.keys())
        succeeded = [
            name
            for name, spec in self._all_specialists.items()
            if spec.state == SpecialistState.COMPLETED
        ]
        blocked = [
            name
            for name, spec in self._all_specialists.items()
            if spec.state == SpecialistState.BLOCKED
        ]
        failed = [
            name
            for name, spec in self._all_specialists.items()
            if spec.state == SpecialistState.FAILED
        ]

        # Concurrently record execution metrics
        sum_of_task_times = round(sum(t["duration"] for t in self.task_traces), 4)
        parallel_wall_time = round(duration, 4)
        parallelism_factor = (
            round(sum_of_task_times / parallel_wall_time, 2)
            if parallel_wall_time > 0.001
            else 1.0
        )

        unknowns = [u.model_dump() for u in self.formulate_unknowns()]
        unresolved_hypos = [
            {
                "hypothesis_id": h.hypothesis_id,
                "statement": h.statement,
                "vulnerability_class": h.vulnerability_class,
                "confidence": h.confidence,
            }
            for h in self.get_unresolved_hypotheses()
        ]
        agenda = self.prioritize_by_information_gain()

        return ResearchResult(
            success=(status == "completed"),
            completed_specialists=len(succeeded),
            total_specialists=len(executed),
            status=status,
            duration_seconds=duration,
            parallel_wall_time=parallel_wall_time,
            sum_of_task_times=sum_of_task_times,
            parallelism_factor=parallelism_factor,
            timeline_traces=list(self.task_traces),
            unknowns=unknowns,
            unresolved_hypotheses=unresolved_hypos,
            information_gain_priorities=agenda,
            total_events=self.event_bus.event_count,
            specialists_executed=executed,
            specialists_succeeded=succeeded,
            specialists_blocked=blocked,
            specialists_failed=failed,
            blackboard_summary=self.blackboard.snapshot(),
            verified_vulnerabilities_count=len(self.blackboard.verified_vulnerabilities),
            falsified_hypotheses_count=len(self.blackboard.falsified_hypotheses),
            conflicts_count=len(self.blackboard.conflicts),
            resolved_conflicts_count=len([c for c in self.blackboard.conflicts if c.status == "resolved"]),
        )

    async def _execute_specialist_wrapper(
        self,
        specialist: SpecialistAgent,
        context: dict[str, Any],
    ) -> Any:
        """Run specialist under semaphore control and record exact timeline metrics."""
        self._task_counter += 1
        task_id = f"task-{self._task_counter:03d}-{specialist.agent_id}"
        t_start = time.time()
        self.blackboard.record_worker_start(specialist.name)
        async with self._semaphore:
            try:
                res = await specialist.run(context, self.event_bus)
                if specialist.state == SpecialistState.COMPLETED:
                    self.blackboard.record_worker_completion(specialist.name, specialist.state)
                elif specialist.state in (SpecialistState.FAILED, SpecialistState.BLOCKED):
                    self.blackboard.record_worker_failure(
                        worker_name=specialist.name,
                        error=specialist.last_error or specialist.state_reason,
                        reason=specialist.failure_reason or specialist.state_reason,
                        diagnostic=specialist.failure_diagnostic or specialist.state_reason,
                        state=specialist.state,
                        context=context,
                    )
                return res
            except asyncio.CancelledError:
                self.blackboard.record_worker_completion(specialist.name, SpecialistState.COMPLETED)
            except Exception as ex:
                logger.warning(
                    "specialist_execution_exception", agent=specialist.name, error=str(ex)
                )
                target_state, reason, err_type, diag = classify_specialist_failure(ex)
                if specialist.state not in (SpecialistState.FAILED, SpecialistState.BLOCKED):
                    with contextlib.suppress(Exception):
                        await specialist.transition_to(target_state, f"{reason}: {diag}", self.event_bus)
                self.blackboard.record_worker_failure(
                    worker_name=specialist.name,
                    error=str(ex),
                    reason=reason,
                    diagnostic=diag,
                    state=specialist.state,
                    context=context,
                )
                return None
            finally:
                t_end = time.time()
                t_duration = round(t_end - t_start, 4)
                self.task_traces.append({
                    "task_id": task_id,
                    "specialist": specialist.name,
                    "start_time": t_start,
                    "end_time": t_end,
                    "duration": t_duration,
                })
                with contextlib.suppress(ValueError):
                    self._priority_queue.task_done()

