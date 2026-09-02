"""
SONIC-REDA — Director (Event-Driven Engagement Coordinator)
==============================================================
Replaces the linear EngagementManager pipeline with event-driven,
graph-based orchestration.

Lifecycle:
    1. Receive target + scope + tenant_id (from authenticated context)
    2. LLM creates initial cognitive state + task graph
    3. Scheduler dispatches ready tasks to worker pool
    4. On task completion → update cognitive state → check replan trigger
    5. If replan triggered → LLM evaluates → validates → mutates graph
    6. Repeat until graph complete or max replans/budget exceeded
    7. Final report compilation

Critical-Thinking Loop:
    OBSERVE → INTERPRET → SEPARATE FACTS FROM INFERENCE
    → IDENTIFY UNCERTAINTY → GENERATE HYPOTHESES
    → GENERATE CANDIDATE EXPERIMENTS → SELECT NEXT-BEST ACTION
    → EXECUTE → COMPARE EXPECTED VS OBSERVED → UPDATE WORLD MODEL → REPLAN

The Director NEVER executes agent work directly.
All execution goes through: Director → Queue → Worker → Agent.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sonic.agents.cognitive_state import (
    Assumption,
    Attempt,
    CandidateAction,
    CognitiveHypothesis,
    CognitiveState,
    EngagementBudget,
    EvidenceRef,
    Fact,
    HypothesisLifecycle,
    Inference,
    NextBestActionDecision,
    Observation,
    Provenance,
    Unknown,
)
from sonic.agents.replan import (
    ReplanDecision,
    ReplanEngine,
    ReplanTrigger,
)
from sonic.agents.state_store import StateStore, get_state_store
from sonic.agents.task_graph import (
    TaskGraph,
    TaskGraphError,
    TaskNode,
    TaskPriority,
    TaskStatus,
    VALID_AGENT_TYPES,
)
from sonic.research.epistemic import (
    CompetingHypothesis,
    ConfidenceCalculator,
    Contradiction,
    ContradictionSeverity,
    EvidenceWeight,
    EvidenceSourceType,
    Prediction,
    PredictionComparison,
)
from sonic.research.information_gain import (
    ActionCandidate,
    ActionSelector,
)
from sonic.research.decision_trace import DecisionTrace
from sonic.research.world_model import (
    StopCondition,
    StopConditionEvaluator,
    WorldModel,
)
from sonic.logger import get_logger
from sonic.llm.router import ModelRouter
from sonic.llm.schemas import LLMRequest, Message, MessageRole
from sonic.memory.graph import GraphMemory
from sonic.memory.schemas import EngagementNode, EngagementStatus, AgentNode
from sonic.safety.scope import ScopeChecker

logger = get_logger(__name__)


# ============================================
# Agent Contract Types
# ============================================

class AgentInput:
    """Standard input contract for specialist agents."""

    def __init__(
        self,
        *,
        tenant_id: str,
        engagement_id: str,
        task_id: str,
        agent_type: str,
        workspace_id: str = "",
        target: str = "",
        task_payload: dict[str, Any] | None = None,
        cognitive_context: dict[str, Any] | None = None,
        failed_methods: list[str] | None = None,
    ):
        self.tenant_id = tenant_id
        self.engagement_id = engagement_id
        self.task_id = task_id
        self.agent_type = agent_type
        self.workspace_id = workspace_id
        self.target = target
        self.task_payload = task_payload or {}
        self.cognitive_context = cognitive_context or {}
        self.failed_methods = failed_methods or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "engagement_id": self.engagement_id,
            "task_id": self.task_id,
            "agent_type": self.agent_type,
            "workspace_id": self.workspace_id,
            "target": self.target,
            "task_payload": self.task_payload,
            "cognitive_context": self.cognitive_context,
            "failed_methods": self.failed_methods,
        }


class AgentOutput:
    """Standard output contract for specialist agents."""

    def __init__(
        self,
        *,
        observations: list[dict[str, Any]] | None = None,
        facts: list[dict[str, Any]] | None = None,
        hypotheses: list[dict[str, Any]] | None = None,
        evidence_refs: list[dict[str, Any]] | None = None,
        findings: list[dict[str, Any]] | None = None,
        failed_attempts: list[dict[str, Any]] | None = None,
        recommended_next_actions: list[str] | None = None,
        metrics: dict[str, Any] | None = None,
    ):
        self.observations = observations or []
        self.facts = facts or []
        self.hypotheses = hypotheses or []
        self.evidence_refs = evidence_refs or []
        self.findings = findings or []
        self.failed_attempts = failed_attempts or []
        self.recommended_next_actions = recommended_next_actions or []
        self.metrics = metrics or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "observations": self.observations,
            "facts": self.facts,
            "hypotheses": self.hypotheses,
            "evidence_refs": self.evidence_refs,
            "findings": self.findings,
            "failed_attempts": self.failed_attempts,
            "recommended_next_actions": self.recommended_next_actions,
            "metrics": self.metrics,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentOutput:
        return cls(**{k: data.get(k, []) for k in (
            "observations", "facts", "hypotheses", "evidence_refs",
            "findings", "failed_attempts", "recommended_next_actions", "metrics",
        )})


# ============================================
# Lifecycle Events
# ============================================

class LifecycleEvent:
    """Structured event for engagement lifecycle tracking."""

    def __init__(
        self,
        event_type: str,
        tenant_id: str,
        engagement_id: str,
        task_id: str = "",
        agent_id: str = "",
        payload: dict[str, Any] | None = None,
    ):
        self.event_id = f"evt-{uuid.uuid4().hex[:12]}"
        self.event_type = event_type
        self.tenant_id = tenant_id
        self.engagement_id = engagement_id
        self.task_id = task_id
        self.agent_id = agent_id
        self.payload = payload or {}
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "tenant_id": self.tenant_id,
            "engagement_id": self.engagement_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }


# ============================================
# Director
# ============================================

class Director:
    """
    Event-driven engagement director.

    Replaces the linear EngagementManager pipeline with:
        1. Cognitive State Machine (world model)
        2. Task Graph (DAG with dependencies)
        3. Scheduler (event-driven, parallel dispatch)
        4. Replan Engine (LLM-driven critical thinking)

    The Director NEVER receives tenant_id="default" in production.
    Tenant identity comes from authenticated request context.
    """

    def __init__(
        self,
        model_router: ModelRouter,
        graph_memory: GraphMemory,
        scope_checker: ScopeChecker,
        state_store: StateStore | None = None,
        max_parallel: int = 4,
        budget: EngagementBudget | None = None,
    ):
        self.router = model_router
        self.memory = graph_memory
        self.scope = scope_checker
        self.state_store = state_store or get_state_store()
        self.max_parallel = max_parallel
        self.default_budget = budget or EngagementBudget(max_parallel=max_parallel)

        # Active engagements (in-memory, backed by Redis)
        self._states: dict[str, CognitiveState] = {}
        self._graphs: dict[str, TaskGraph] = {}
        self._events: dict[str, list[LifecycleEvent]] = {}

        # Replan engine & Action selector (Phase 6)
        self.replan_engine = ReplanEngine(scope_checker=scope_checker)
        self.action_selector = ActionSelector()

    # ============================================
    # Engagement Lifecycle
    # ============================================

    async def start_engagement(
        self,
        target: str,
        scope: dict[str, Any],
        tenant_id: str,
        created_by: str = "",
        budget: EngagementBudget | None = None,
    ) -> str:
        """
        Start a new engagement.

        Args:
            target: Primary target (domain, URL, etc.)
            scope: Scope configuration
            tenant_id: From authenticated request context. NEVER "default".
            created_by: User email/ID
            budget: Resource limits for this engagement

        Returns:
            engagement_id
        """
        engagement_id = f"eng-{uuid.uuid4().hex[:12]}"
        eng_budget = budget or self.default_budget

        # Create cognitive state
        state = CognitiveState(
            engagement_id=engagement_id,
            tenant_id=tenant_id,
            goal=f"Comprehensive security assessment of {target}",
            budget=eng_budget,
        )

        # Create task graph
        graph = TaskGraph(
            engagement_id=engagement_id,
            tenant_id=tenant_id,
            max_total_tasks=eng_budget.max_total_tasks,
        )

        # Store
        self._states[engagement_id] = state
        self._graphs[engagement_id] = graph
        self._events[engagement_id] = []

        # Persist to graph memory
        engagement_node = EngagementNode(
            uid=engagement_id,
            tenant_id=tenant_id,
            name=f"Assessment: {target}",
            target_summary=target,
            created_by=created_by,
            scope_config=json.dumps(scope),
            status=EngagementStatus.RUNNING,
        )
        await self.memory.create_engagement(engagement_node)

        # Emit lifecycle event
        self._emit_event(LifecycleEvent(
            event_type="EngagementStarted",
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            payload={"target": target, "scope": scope, "budget": eng_budget.model_dump()},
        ))

        # Create initial plan using LLM
        await self._create_initial_plan(state, graph, target, scope)

        # Persist state
        await self._persist(engagement_id)

        logger.info(
            "engagement_started",
            engagement_id=engagement_id,
            tenant_id=tenant_id,
            target=target,
            initial_tasks=graph.size,
        )

        return engagement_id

    async def _create_initial_plan(
        self,
        state: CognitiveState,
        graph: TaskGraph,
        target: str,
        scope: dict[str, Any],
    ) -> None:
        """Use LLM to create the initial engagement plan (cognitive state + task graph)."""
        prompt = f"""You are planning a security assessment for: {target}

Scope: {json.dumps(scope, indent=2)[:500]}

Create an initial plan with:
1. Key assumptions about the target
2. Initial unknowns to investigate
3. Phased tasks (recon first, then analysis, then testing)

Where a gap exists that no registered scanner covers, prefer a toolsmith or
method-invention task (agent_type "toolsmith" or "method") over forcing a
known-scanner that does not apply.

Respond with JSON:
{{
    "assumptions": ["assumption 1", "assumption 2"],
    "unknowns": ["question 1", "question 2"],
    "tasks": [
        {{
            "name": "descriptive name",
            "agent_type": "recon|static|dynamic|hypothesis|verifier",
            "priority": "critical|high|medium|low",
            "depends_on": [],
            "payload": {{"target": "{target}", "task": "specific_task"}}
        }}
    ]
}}

Valid agent types: {json.dumps(sorted(VALID_AGENT_TYPES))}
Create 3-6 initial tasks. Start with recon."""

        try:
            response = await self._think(prompt)
            state.llm_calls_used += 1
            plan = self._parse_plan(response, target)
        except Exception as e:
            logger.warning("initial_plan_llm_failed", error=str(e))
            plan = self._default_plan(target)

        # Populate cognitive state
        for assumption_text in plan.get("assumptions", []):
            state.add_assumption(
                Assumption(description=assumption_text),
                agent_id="director",
            )

        for unknown_text in plan.get("unknowns", []):
            state.add_unknown(
                Unknown(question=unknown_text),
                agent_id="director",
            )

        # Build task graph
        task_id_map: dict[str, str] = {}  # name → task_id
        for task_def in plan.get("tasks", []):
            deps = [
                task_id_map[d]
                for d in task_def.get("depends_on", [])
                if d in task_id_map
            ]
            try:
                task = TaskNode(
                    name=task_def["name"],
                    agent_type=task_def.get("agent_type", "recon"),
                    task_payload=task_def.get("payload", {"target": target}),
                    depends_on=deps,
                    priority=TaskPriority(task_def.get("priority", "medium")),
                    expected_observation=task_def.get("expected_observation", ""),
                    engagement_id=state.engagement_id,
                    tenant_id=state.tenant_id,
                )
                tid = graph.add_task(task)
                task_id_map[task_def["name"]] = tid

                self._emit_event(LifecycleEvent(
                    event_type="TaskCreated",
                    tenant_id=state.tenant_id,
                    engagement_id=state.engagement_id,
                    task_id=tid,
                    payload={"name": task_def["name"], "agent_type": task_def.get("agent_type")},
                ))
            except TaskGraphError as e:
                logger.warning("initial_task_rejected", task=task_def.get("name"), error=str(e))

    def _parse_plan(self, raw: str, target: str) -> dict[str, Any]:
        """Parse LLM plan output."""
        try:
            content = raw
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            return json.loads(content.strip())
        except Exception:
            return self._default_plan(target)

    def _default_plan(self, target: str) -> dict[str, Any]:
        """Fallback plan when LLM is unavailable."""
        return {
            "assumptions": [
                f"{target} is a web application with standard HTTP(S) endpoints",
                "Standard security headers may or may not be configured",
            ],
            "unknowns": [
                f"What technology stack does {target} use?",
                f"What subdomains exist for {target}?",
                f"What authentication mechanism does {target} use?",
            ],
            "tasks": [
                {
                    "name": f"Recon: Surface discovery for {target}",
                    "agent_type": "recon",
                    "priority": "high",
                    "depends_on": [],
                    "payload": {"target": target, "task": "full_recon"},
                },
                {
                    "name": f"Hypothesis: Vulnerability ideation for {target}",
                    "agent_type": "hypothesis",
                    "priority": "medium",
                    "depends_on": [f"Recon: Surface discovery for {target}"],
                    "payload": {"target": target, "task": "generate_hypotheses"},
                },
                {
                    "name": f"Static: Configuration analysis for {target}",
                    "agent_type": "static",
                    "priority": "medium",
                    "depends_on": [f"Recon: Surface discovery for {target}"],
                    "payload": {"target": target, "task": "full_analysis"},
                },
            ],
        }

    # ============================================
    # Task Completion Handling
    # ============================================

    async def on_task_completed(
        self,
        engagement_id: str,
        task_id: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Handle task completion event.

        Pipeline:
            1. Mark task SUCCEEDED in graph
            2. Parse AgentOutput
            3. Update cognitive state (observations, facts, hypotheses, etc.)
            4. Compare expected vs actual
            5. Check replan triggers
            6. If replan needed → evaluate → validate → apply
            7. Dispatch next ready tasks

        Returns:
            Summary of actions taken
        """
        state = self._states.get(engagement_id)
        graph = self._graphs.get(engagement_id)
        if not state or not graph:
            return {"error": f"Engagement {engagement_id} not found"}

        task = graph.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found in graph"}

        # 1. Mark completed in graph
        try:
            graph.mark_completed(task_id, result)
        except TaskGraphError as e:
            return {"error": f"Cannot complete task: {str(e)}"}

        state.tasks_completed += 1

        # Emit event
        self._emit_event(LifecycleEvent(
            event_type="TaskSucceeded",
            tenant_id=state.tenant_id,
            engagement_id=engagement_id,
            task_id=task_id,
            payload={"agent_type": task.agent_type},
        ))

        # 2. Parse agent output
        output = AgentOutput.from_dict(result)

        # 3. Update cognitive state
        self._ingest_agent_output(state, output, task)

        # 4. Compare expected vs actual & evaluate Prediction (Phase 6)
        matching_pred = next((p for p in state.predictions if getattr(p, "task_id", "") == task_id), None)
        if matching_pred:
            comparison = PredictionComparison.evaluate(
                prediction=matching_pred,
                actual_data=result,
                engagement_id=engagement_id,
                tenant_id=state.tenant_id,
            )
            state.record_prediction_comparison(comparison, agent_id="director")

        self._compare_expected_vs_actual(state, task, result)

        # 5. Check Contradictions (Phase 6)
        self._check_contradictions(state, output)

        # 6. Recompute Confidence (Phase 6 transparent model)
        self._recompute_confidence(state)

        # 7. Check Stop Conditions (Phase 6)
        stop_eval = self._evaluate_stop_condition(state, graph)
        if stop_eval.should_stop:
            state.set_stop_condition(stop_eval.condition.value, stop_eval.reason, agent_id="director")
            if stop_eval.condition == StopCondition.HUMAN_REVIEW_REQUIRED:
                await self.pause_engagement(engagement_id)

        # 8. Check replan triggers
        trigger_event = {
            "event_type": "TaskSucceeded",
            "task_id": task_id,
            "agent_type": task.agent_type,
            "result_summary": {
                "observations": len(output.observations),
                "facts": len(output.facts),
                "hypotheses": len(output.hypotheses),
                "findings": len(output.findings),
            },
        }

        replan_result = {}
        trigger = self.replan_engine.detect_trigger(state, graph, trigger_event)
        if trigger and state.can_replan():
            decision = await self.replan_engine.evaluate(
                state, graph, trigger_event,
                think_fn=self._think,
            )
            if decision.should_replan:
                replan_result = self.replan_engine.apply_decision(decision, graph, state)

        # 6. Persist
        await self._persist(engagement_id)

        # 7. Get ready tasks for dispatch
        ready = graph.get_ready_tasks()

        summary = {
            "task_id": task_id,
            "agent_type": task.agent_type,
            "observations_ingested": len(output.observations),
            "facts_ingested": len(output.facts),
            "hypotheses_ingested": len(output.hypotheses),
            "replan": replan_result,
            "ready_tasks": [t.id for t in ready[:self.max_parallel]],
            "graph_complete": graph.is_complete(),
        }

        # Check if engagement is complete
        if graph.is_complete():
            await self._finalize_engagement(engagement_id)

        return summary

    async def on_task_failed(
        self,
        engagement_id: str,
        task_id: str,
        error: str,
    ) -> dict[str, Any]:
        """Handle task failure event."""
        state = self._states.get(engagement_id)
        graph = self._graphs.get(engagement_id)
        if not state or not graph:
            return {"error": f"Engagement {engagement_id} not found"}

        task = graph.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        # Mark failed and cascade blocked
        blocked_ids = graph.mark_failed(task_id, error)
        state.tasks_failed += 1

        # Record as failed attempt
        state.record_attempt(
            Attempt(
                method=f"{task.agent_type}: {task.name}",
                task_id=task_id,
                agent_id=task.agent_id,
                success=False,
                failure_reason=error,
                lesson=f"Task failed with error: {error[:200]}",
            ),
            agent_id="director",
        )

        # Emit event
        self._emit_event(LifecycleEvent(
            event_type="TaskFailed",
            tenant_id=state.tenant_id,
            engagement_id=engagement_id,
            task_id=task_id,
            payload={"error": error, "blocked_tasks": blocked_ids},
        ))

        # Check replan
        trigger_event = {
            "event_type": "TaskFailed",
            "task_id": task_id,
            "agent_type": task.agent_type,
            "error": error,
        }

        replan_result = {}
        if state.can_replan():
            decision = await self.replan_engine.evaluate(
                state, graph, trigger_event,
                think_fn=self._think,
            )
            if decision.should_replan:
                replan_result = self.replan_engine.apply_decision(decision, graph, state)

        await self._persist(engagement_id)

        # Check completion
        if graph.is_complete():
            await self._finalize_engagement(engagement_id)

        return {
            "task_id": task_id,
            "error": error,
            "blocked_tasks": blocked_ids,
            "replan": replan_result,
            "graph_complete": graph.is_complete(),
        }

    # ============================================
    # Cognitive State Ingestion
    # ============================================

    def _ingest_agent_output(
        self,
        state: CognitiveState,
        output: AgentOutput,
        task: TaskNode,
    ) -> None:
        """
        Ingest agent results into the cognitive state.

        Agent results pass through:
            Agent → Evidence Engine → Graph → Cognitive State

        The Director does NOT directly mark hypotheses as verified findings.
        State transitions go: HYPOTHESIS → CANDIDATE → VALIDATING → EVIDENCE_COLLECTED → VERIFIED
        """
        provenance = Provenance(
            source_type="agent",
            source_agent=task.agent_id,
            tool=task.agent_type,
            execution_id=task.id,
        )

        # Observations (raw data)
        for obs_data in output.observations:
            state.add_observation(
                Observation(
                    description=obs_data.get("description", ""),
                    raw_data=str(obs_data.get("raw_data", ""))[:2000],
                    provenance=provenance,
                ),
                agent_id=task.agent_id,
            )

        # Facts (verified truths)
        for fact_data in output.facts:
            state.add_fact(
                Fact(
                    description=fact_data.get("description", ""),
                    evidence_ids=fact_data.get("evidence_ids", []),
                    provenance=provenance,
                ),
                agent_id=task.agent_id,
            )

        # Hypotheses
        for hyp_data in output.hypotheses:
            state.add_hypothesis(
                CognitiveHypothesis(
                    title=hyp_data.get("title", ""),
                    description=hyp_data.get("description", ""),
                    vulnerability_class=hyp_data.get("vulnerability_class", ""),
                    rationale=hyp_data.get("rationale", ""),
                    test_plan=hyp_data.get("test_plan", ""),
                    expected_observation=hyp_data.get("expected_observation", ""),
                    priority=hyp_data.get("priority", 5),
                    provenance=provenance,
                ),
                agent_id=task.agent_id,
            )

        # Evidence references
        for ev_data in output.evidence_refs:
            state.add_evidence(
                EvidenceRef(
                    evidence_type=ev_data.get("evidence_type", "log"),
                    description=ev_data.get("description", ""),
                    content_hash=ev_data.get("content_hash", ""),
                    storage_key=ev_data.get("storage_key", ""),
                ),
                agent_id=task.agent_id,
            )

        # Failed attempts
        for attempt_data in output.failed_attempts:
            state.record_attempt(
                Attempt(
                    method=attempt_data.get("method", ""),
                    assumption=attempt_data.get("assumption", ""),
                    success=False,
                    failure_reason=attempt_data.get("failure_reason", ""),
                    lesson=attempt_data.get("lesson", ""),
                    task_id=task.id,
                    agent_id=task.agent_id,
                ),
                agent_id=task.agent_id,
            )

    def _compare_expected_vs_actual(
        self,
        state: CognitiveState,
        task: TaskNode,
        result: dict[str, Any],
    ) -> None:
        """Compare expected vs actual observation. Create inference on mismatch."""
        if not task.expected_observation:
            return

        actual_summary = json.dumps(result, default=str)[:500]

        # Simple heuristic: if expected keywords aren't in actual, flag it
        expected_keywords = set(task.expected_observation.lower().split())
        actual_lower = actual_summary.lower()
        match_ratio = sum(1 for kw in expected_keywords if kw in actual_lower) / max(len(expected_keywords), 1)

        if match_ratio < 0.3:
            state.add_observation(
                Observation(
                    description=f"UNEXPECTED RESULT for '{task.name}': expected '{task.expected_observation}' but got different outcome",
                    raw_data=actual_summary[:500],
                ),
                agent_id="director",
            )
            state.add_unknown(
                Unknown(
                    question=f"Why did '{task.name}' produce unexpected results?",
                    possible_actions=["investigate further", "retry with different parameters"],
                    estimated_importance=0.7,
                ),
                agent_id="director",
            )

    # ============================================
    # Task Dispatch
    # ============================================

    def get_dispatchable_tasks(self, engagement_id: str) -> list[dict[str, Any]]:
        """
        Get tasks ready for dispatch as job payloads.

        Returns AgentInput-compatible dicts for the worker to consume.
        """
        state = self._states.get(engagement_id)
        graph = self._graphs.get(engagement_id)
        if not state or not graph:
            return []

        ready = graph.get_ready_tasks()
        running = graph.get_running_tasks()
        slots = self.max_parallel - len(running)

        if slots <= 0:
            return []

        dispatchable = []
        for task in ready[:slots]:
            # Formulate prediction before dispatch (Phase 6)
            pred = Prediction(
                task_id=task.id,
                experiment_name=task.name,
                expected_outcomes={"expected_observation": task.expected_observation or "Conclusive measurement"},
                expected_signature=task.expected_observation or "",
                confidence=0.75,
                engagement_id=engagement_id,
                tenant_id=state.tenant_id,
            )
            state.add_prediction(pred, agent_id="director")

            # Record Decision Trace ("Why this action?") (Phase 6)
            trace = DecisionTrace(
                engagement_id=engagement_id,
                tenant_id=state.tenant_id,
                current_state_summary=state.summary(),
                unknown_being_addressed=task.task_payload.get("question", task.name),
                candidate_actions=[{"task_id": t.id, "name": t.name, "priority": t.priority.value} for t in ready],
                selected_action=task.name,
                selected_action_id=task.id,
                selection_reason=f"Priority {task.priority.value} dependency-resolved action with high expected information gain",
                expected_information_gain=0.8,
                estimated_cost=0.2,
                risk=0.1,
                predicted_outcome=task.expected_observation or "Successful tool execution",
                confidence_before=state.confidence,
            )
            state.add_decision_trace(trace, agent_id="director")

            agent_input = AgentInput(
                tenant_id=state.tenant_id,
                engagement_id=engagement_id,
                task_id=task.id,
                agent_type=task.agent_type,
                workspace_id=task.workspace_id or f"ws-{engagement_id}",
                target=task.task_payload.get("target", ""),
                task_payload=task.task_payload,
                cognitive_context=state.summary(),
                failed_methods=list(state.get_failed_methods()),
            )
            dispatchable.append(agent_input.to_dict())

            # Mark as running in graph
            try:
                graph.mark_running(task.id)
                self._emit_event(LifecycleEvent(
                    event_type="TaskStarted",
                    tenant_id=state.tenant_id,
                    engagement_id=engagement_id,
                    task_id=task.id,
                ))
            except TaskGraphError as e:
                logger.warning("task_dispatch_failed", task_id=task.id, error=str(e))

        return dispatchable

    # ============================================
    # Research Helper Methods (Phase 6)
    # ============================================

    def _check_contradictions(self, state: CognitiveState, output: AgentOutput) -> None:
        """Scan for conflicting observations."""
        for new_obs in output.observations:
            desc = new_obs.get("description", "").lower()
            for existing_fact in state.get_active_facts():
                fact_desc = existing_fact.description.lower()
                # Simple keyword conflict detection
                if ("not vulnerable" in desc and "vulnerable" in fact_desc) or \
                   ("403 forbidden" in desc and "200 ok" in fact_desc and "unauthenticated" in desc):
                    ctrd = Contradiction(
                        statement_a=existing_fact.description,
                        statement_b=new_obs.get("description", ""),
                        source_a_id=existing_fact.id,
                        source_b_id=new_obs.get("id", ""),
                        severity=ContradictionSeverity.HIGH,
                        engagement_id=state.engagement_id,
                        tenant_id=state.tenant_id,
                    )
                    state.add_contradiction(ctrd, agent_id="director")

    def _recompute_confidence(self, state: CognitiveState) -> None:
        """Recalculate overall confidence using transparent multi-factor formula."""
        evidence_weights = [
            EvidenceWeight(
                source_type=EvidenceSourceType.TOOL_MEASUREMENT,
                reliability=0.9,
                directness=1.0,
            ) for _ in state.evidence
        ]
        breakdown = ConfidenceCalculator.calculate(
            evidence_weights=evidence_weights,
            independent_confirmations_count=len(state.successful_attempts),
            unresolved_contradictions_count=len(state.get_active_contradictions()),
            unresolved_unknowns_count=len(state.get_unresolved_unknowns()),
            is_reproducible=len(state.evidence) >= 2,
        )
        state.confidence = breakdown.composite_confidence
        state.confidence_breakdown = breakdown.model_dump()

    def _evaluate_stop_condition(self, state: CognitiveState, graph: TaskGraph) -> Any:
        """Evaluate explicit stopping policies."""
        from sonic.research.world_model import WorldModel, StopConditionEvaluator
        wm = WorldModel(
            goal=state.goal,
            target="",
            tenant_id=state.tenant_id,
            engagement_id=state.engagement_id,
            known_facts=[f.description for f in state.get_active_facts()],
            unknowns=state.unknowns,
            contradictions=state.contradictions,
            overall_confidence=state.confidence,
        )
        return StopConditionEvaluator.evaluate(
            world_model=wm,
            replan_count=state.replan_count,
            max_replans=state.budget.max_replans,
            tasks_count=state.tasks_completed + state.tasks_failed,
            max_tasks=state.budget.max_total_tasks,
        )

    # ============================================
    # Engagement Finalization
    # ============================================

    async def _finalize_engagement(self, engagement_id: str) -> None:
        """Finalize an engagement after all tasks are complete."""
        state = self._states.get(engagement_id)
        if not state:
            return

        self._emit_event(LifecycleEvent(
            event_type="EngagementCompleted",
            tenant_id=state.tenant_id,
            engagement_id=engagement_id,
            payload=state.summary(),
        ))

        await self.memory.update_engagement(
            engagement_id, status=EngagementStatus.COMPLETED,
        )

        logger.info(
            "engagement_completed",
            engagement_id=engagement_id,
            facts=len(state.get_active_facts()),
            hypotheses=len(state.hypotheses),
            evidence=len(state.evidence),
            confidence=state.confidence,
        )

    # ============================================
    # State Recovery
    # ============================================

    async def recover_engagement(self, engagement_id: str) -> bool:
        """
        Recover an engagement from persisted state after restart.

        Protocol:
            1. Load CognitiveState + TaskGraph from Redis
            2. Tasks in RUNNING state → reset to READY (for re-dispatch)
            3. Resume from last known state
            4. No duplicate execution for SUCCEEDED tasks
        """
        state_dict = await self.state_store.load_state(engagement_id)
        graph_dict = await self.state_store.load_graph(engagement_id)

        if not state_dict or not graph_dict:
            logger.warning("recovery_failed_no_state", engagement_id=engagement_id)
            return False

        try:
            state = CognitiveState(**state_dict)
            graph = TaskGraph.from_dict(graph_dict)
        except Exception as e:
            logger.error("recovery_parse_failed", engagement_id=engagement_id, error=str(e))
            return False

        # Reset RUNNING tasks to READY (they were in-flight during crash)
        for task in graph.get_running_tasks():
            task.status = TaskStatus.READY
            task.started_at = None
            task.agent_id = ""

        self._states[engagement_id] = state
        self._graphs[engagement_id] = graph
        self._events[engagement_id] = []

        logger.info(
            "engagement_recovered",
            engagement_id=engagement_id,
            tasks=graph.size,
            ready=len(graph.get_ready_tasks()),
        )

        return True

    # ============================================
    # Pause / Resume
    # ============================================

    async def pause_engagement(self, engagement_id: str) -> bool:
        """Pause an engagement, preserving state."""
        state = self._states.get(engagement_id)
        if not state:
            return False

        await self._persist(engagement_id)

        self._emit_event(LifecycleEvent(
            event_type="EngagementPaused",
            tenant_id=state.tenant_id,
            engagement_id=engagement_id,
        ))

        await self.memory.update_engagement(
            engagement_id, status=EngagementStatus.PAUSED,
        )

        return True

    async def resume_engagement(self, engagement_id: str) -> bool:
        """Resume a paused engagement."""
        if engagement_id not in self._states:
            recovered = await self.recover_engagement(engagement_id)
            if not recovered:
                return False

        state = self._states.get(engagement_id)
        if not state:
            return False

        await self.memory.update_engagement(
            engagement_id, status=EngagementStatus.RUNNING,
        )

        return True

    # ============================================
    # LLM Interface
    # ============================================

    async def _think(self, prompt: str) -> str:
        """Send a prompt to the LLM via the model router."""
        if not self.router:
            raise RuntimeError("No model router configured")

        request = LLMRequest(
            messages=[
                Message(
                    role=MessageRole.SYSTEM,
                    content="You are the Director of SONIC — an Autonomous Self-Evolving Penetration Architect (A-SEA) — an AI security-assessment coordinator. Respond with valid JSON only.",
                ),
                Message(role=MessageRole.USER, content=prompt),
            ],
            task_type="planning",
            agent_id="director",
        )
        response = await self.router.complete(request, task_type="planning")
        return response.content

    # ============================================
    # Persistence
    # ============================================

    async def _persist(self, engagement_id: str) -> None:
        """Persist cognitive state and task graph to Redis."""
        state = self._states.get(engagement_id)
        graph = self._graphs.get(engagement_id)
        if not state or not graph:
            return

        await self.state_store.save_state(engagement_id, state.model_dump())
        await self.state_store.save_graph(engagement_id, graph.to_dict())

        # Persist recent events
        for event in self._events.get(engagement_id, []):
            await self.state_store.append_event(engagement_id, event.to_dict())
        self._events[engagement_id] = []

    # ============================================
    # Event Emission
    # ============================================

    def _emit_event(self, event: LifecycleEvent) -> None:
        """Record a lifecycle event."""
        eid = event.engagement_id
        if eid not in self._events:
            self._events[eid] = []
        self._events[eid].append(event)
        logger.info("lifecycle_event", event_type=event.event_type, engagement_id=eid)

    # ============================================
    # Query / Status
    # ============================================

    def get_engagement_state(self, engagement_id: str) -> dict[str, Any] | None:
        """Get the cognitive state summary for an engagement."""
        state = self._states.get(engagement_id)
        if not state:
            return None
        return state.summary()

    def get_task_graph(self, engagement_id: str) -> dict[str, Any] | None:
        """Get the task graph for an engagement."""
        graph = self._graphs.get(engagement_id)
        if not graph:
            return None
        return graph.to_dict()

    def get_events(self, engagement_id: str) -> list[dict[str, Any]]:
        """Get lifecycle events for an engagement."""
        return [e.to_dict() for e in self._events.get(engagement_id, [])]

    def list_engagements(self) -> list[str]:
        """List active engagement IDs."""
        return list(self._states.keys())
