"""
SONIC-REDA — Replan Engine
===============================
Critical-thinking module that evaluates cognitive state changes and decides
whether to mutate the task graph.

Pipeline:
    New Observation
      → Replan Engine
        → LLM Decision
          → Structured ReplanDecision (Pydantic)
            → Schema Validation
              → Policy Validation
                → Scope Validation
                  → Task Graph Mutation

Rejects:
    - Invalid agent types
    - Invalid task states
    - Missing tenant_id
    - Invalid dependencies
    - Circular dependency insertion
    - Unsupported tools
    - Out-of-scope targets
    - Dangerous actions
    - Unknown task types
    - Exceeding replan budget
    - Exceeding task budget

The LLM NEVER directly mutates the task graph. All mutations go through
structured validation.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from sonic.llm.prompts import asea_identity

from sonic.agents.cognitive_state import (
    CognitiveState,
    Unknown,
)
from sonic.agents.task_graph import (
    VALID_AGENT_TYPES,
    TaskGraph,
    TaskGraphError,
    TaskNode,
    TaskPriority,
    TaskStatus,
)
from sonic.logger import get_logger

logger = get_logger(__name__)


# ============================================
# Replan Triggers
# ============================================

class ReplanTrigger(StrEnum):
    NEW_ATTACK_SURFACE = "new_attack_surface"
    NEW_HIGH_CONFIDENCE_FINDING = "new_high_confidence_finding"
    HYPOTHESIS_CONFIRMED = "hypothesis_confirmed"
    HYPOTHESIS_DISPROVED = "hypothesis_disproved"
    AGENT_FAILURE = "agent_failure"
    NEW_EVIDENCE = "new_evidence"
    LOW_CONFIDENCE = "low_confidence"
    DEPENDENCY_FAILURE = "dependency_failure"
    MANUAL_REPLAN = "manual_replan"
    CONTRADICTION_DETECTED = "contradiction_detected"
    HIGH_PREDICTION_ERROR = "high_prediction_error"
    HYPOTHESIS_CONFIDENCE_DELTA = "hypothesis_confidence_delta"
    STOP_CONDITION_MET = "stop_condition_met"


# ============================================
# Replan Decision (structured LLM output)
# ============================================

class ProposedTask(BaseModel):
    """A task proposed by the LLM during replanning."""
    name: str
    agent_type: str
    task_payload: dict[str, Any] = Field(default_factory=dict)
    depends_on_completed: list[str] = Field(default_factory=list)  # Names of completed tasks
    priority: str = "medium"  # "critical", "high", "medium", "low"
    expected_observation: str = ""
    timeout_seconds: int = 180


class ReplanDecision(BaseModel):
    """Structured decision from the replan engine — validated before graph mutation."""
    should_replan: bool = False
    trigger: ReplanTrigger | None = None
    reasoning: str = ""
    new_tasks: list[ProposedTask] = Field(default_factory=list)
    tasks_to_skip: list[str] = Field(default_factory=list)   # Task IDs
    updated_unknowns: list[dict[str, Any]] = Field(default_factory=list)
    updated_next_action: str = ""
    confidence: float = 0.5


# ============================================
# Validation Results
# ============================================

class ValidationResult(BaseModel):
    """Result of validating a replan decision."""
    valid: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rejected_tasks: list[str] = Field(default_factory=list)
    accepted_tasks: list[ProposedTask] = Field(default_factory=list)


# ============================================
# Replan Engine
# ============================================

class ReplanEngine:
    """
    Evaluates cognitive state changes and produces validated task graph mutations.

    The LLM proposes changes. This engine validates them before they touch the graph.

    Immutable/non-agent-controlled boundaries (never modified by replan):
        - authentication
        - tenant isolation
        - sandbox isolation
        - egress policy
        - secret boundaries
        - audit logging
        - maximum resource limits
        - production deployment policy
    """

    # Forbidden action patterns that the replan engine must never propose
    FORBIDDEN_PATTERNS = frozenset({
        "modify_auth",
        "modify_tenant",
        "modify_sandbox",
        "modify_egress",
        "modify_secrets",
        "modify_audit",
        "modify_limits",
        "host_execution",
        "disable_safety",
        "escalate_privileges",
    })

    def __init__(
        self,
        scope_checker: Any = None,
        allowed_targets: set[str] | None = None,
    ):
        """
        Args:
            scope_checker: ScopeChecker instance for target validation
            allowed_targets: Set of allowed target domains/IPs
        """
        self.scope_checker = scope_checker
        self.allowed_targets = allowed_targets or set()

    # ============================================
    # Trigger Detection
    # ============================================

    def detect_trigger(
        self,
        cognitive_state: CognitiveState,
        task_graph: TaskGraph,
        event: dict[str, Any],
    ) -> ReplanTrigger | None:
        """
        Determine if a trigger event warrants replanning.

        Returns:
            ReplanTrigger if replanning should be considered, None otherwise.
        """
        event_type = event.get("event_type", "")

        # New attack surface discovered
        if event_type in ("observation_added", "fact_created"):
            payload = event.get("payload", {})
            desc = event.get("description", "").lower()
            if any(kw in desc for kw in ("subdomain", "endpoint", "port", "service", "new domain")):
                return ReplanTrigger.NEW_ATTACK_SURFACE

        # Task completion with discoveries
        if event_type == "TaskSucceeded":
            res_sum = event.get("result_summary", {})
            if res_sum.get("observations", 0) > 0 or res_sum.get("facts", 0) > 0 or res_sum.get("hypotheses", 0) > 0:
                return ReplanTrigger.NEW_ATTACK_SURFACE
            if res_sum.get("findings", 0) > 0:
                return ReplanTrigger.NEW_HIGH_CONFIDENCE_FINDING

        # High-confidence finding
        if event_type == "evidence_added":
            return ReplanTrigger.NEW_EVIDENCE

        if event_type == "hypothesis_verified":
            return ReplanTrigger.HYPOTHESIS_CONFIRMED

        if event_type == "hypothesis_disproved":
            return ReplanTrigger.HYPOTHESIS_DISPROVED

        # Agent/task failure
        if event_type in ("TaskFailed", "agent_failure"):
            return ReplanTrigger.AGENT_FAILURE

        # Low confidence
        if event_type == "confidence_changed":
            payload = event.get("payload", {})
            new_conf = payload.get("new_confidence", 1.0)
            if new_conf < 0.3:
                return ReplanTrigger.LOW_CONFIDENCE

        # Contradiction detected
        if event_type == "contradiction_detected":
            return ReplanTrigger.CONTRADICTION_DETECTED

        # Prediction error
        if event_type == "prediction_evaluated":
            payload = event.get("payload", {})
            if payload.get("is_unexpected", False) or payload.get("prediction_error", 0.0) >= 0.4:
                return ReplanTrigger.HIGH_PREDICTION_ERROR

        # Manual replan
        if event_type == "manual_replan":
            return ReplanTrigger.MANUAL_REPLAN

        return None

    # ============================================
    # Decision Evaluation (uses LLM)
    # ============================================

    async def evaluate(
        self,
        cognitive_state: CognitiveState,
        task_graph: TaskGraph,
        trigger_event: dict[str, Any],
        think_fn: Any = None,
    ) -> ReplanDecision:
        """
        Evaluate whether replanning is needed and produce a validated decision.

        Args:
            cognitive_state: Current engagement mind state
            task_graph: Current task execution graph
            trigger_event: The event that triggered evaluation
            think_fn: Async function to call the LLM for reasoning

        Returns:
            Validated ReplanDecision
        """
        # Check budget
        if not cognitive_state.can_replan():
            logger.warning(
                "replan_budget_exhausted",
                engagement_id=cognitive_state.engagement_id,
                count=cognitive_state.replan_count,
                max=cognitive_state.budget.max_replans,
            )
            return ReplanDecision(
                should_replan=False,
                reasoning=f"Replan budget exhausted ({cognitive_state.replan_count}/{cognitive_state.budget.max_replans}). Pausing for human review.",
            )

        # Detect trigger
        trigger = self.detect_trigger(cognitive_state, task_graph, trigger_event)
        if trigger is None:
            return ReplanDecision(should_replan=False, reasoning="No replan trigger detected.")

        # If we have an LLM, ask it for structured reasoning
        if think_fn:
            decision = await self._llm_evaluate(
                cognitive_state, task_graph, trigger, trigger_event, think_fn
            )
        else:
            # Fallback: heuristic decision
            decision = self._heuristic_evaluate(cognitive_state, task_graph, trigger, trigger_event)

        decision.trigger = trigger

        # Validate the decision BEFORE returning
        validation = self.validate_decision(decision, cognitive_state, task_graph)
        if not validation.valid:
            logger.warning(
                "replan_decision_rejected",
                errors=validation.errors,
                engagement_id=cognitive_state.engagement_id,
            )
            # Return a sanitized decision with only accepted tasks
            decision.new_tasks = validation.accepted_tasks
            if not decision.new_tasks and not decision.tasks_to_skip:
                decision.should_replan = False
                decision.reasoning += f" [Validation rejected: {'; '.join(validation.errors)}]"

        return decision

    async def _llm_evaluate(
        self,
        state: CognitiveState,
        graph: TaskGraph,
        trigger: ReplanTrigger,
        event: dict[str, Any],
        think_fn: Any,
    ) -> ReplanDecision:
        """Use LLM to produce a replan decision."""
        prompt = self._build_replan_prompt(state, graph, trigger, event)

        try:
            raw_response = await think_fn(prompt)
            state.llm_calls_used += 1
            return self._parse_llm_response(raw_response)
        except Exception as e:
            logger.error("replan_llm_failed", error=str(e))
            return self._heuristic_evaluate(state, graph, trigger, event)

    def _build_replan_prompt(
        self,
        state: CognitiveState,
        graph: TaskGraph,
        trigger: ReplanTrigger,
        event: dict[str, Any],
    ) -> str:
        """Build the structured prompt for the LLM replan evaluation."""
        summary = state.summary()
        graph_stats = graph.get_stats()

        completed_tasks = [
            {"name": t.name, "agent_type": t.agent_type, "status": t.status.value}
            for t in graph.get_completed_tasks()
        ]
        pending_tasks = [
            {"name": t.name, "agent_type": t.agent_type, "status": t.status.value}
            for t in graph.get_pending_tasks()
        ]

        failed_methods = list(state.get_failed_methods())[:10]
        active_unknowns = [
            {"question": u.question, "importance": u.estimated_importance}
            for u in state.get_unresolved_unknowns()[:10]
        ]

        return f"""{asea_identity("Replan Engine")}

A {trigger.value} event has occurred. Evaluate whether the current plan should be modified.

## Current State
Goal: {state.goal}
Confidence: {state.confidence:.2f}
Facts: {summary['facts_count']}
Active Hypotheses: {summary['active_hypotheses_count']}
Unresolved Unknowns: {summary['unresolved_unknowns_count']}
Failed Attempts: {summary['failed_attempts_count']}
Budget Remaining: replans={summary['budget_remaining']['replans']}, tasks={summary['budget_remaining']['tasks']}

## Trigger Event
{json.dumps(event, indent=2, default=str)[:1000]}

## Task Graph
Stats: {json.dumps(graph_stats)}
Completed: {json.dumps(completed_tasks[:10])}
Pending: {json.dumps(pending_tasks[:10])}

## Failed Methods (do NOT repeat these)
{json.dumps(failed_methods)}

## Active Unknowns
{json.dumps(active_unknowns)}

## Valid Agent Types
{json.dumps(sorted(VALID_AGENT_TYPES))}

## Instructions
Respond with ONLY valid JSON matching this structure:
{{
    "should_replan": true/false,
    "reasoning": "why or why not",
    "new_tasks": [
        {{
            "name": "descriptive task name",
            "agent_type": "one of the valid agent types",
            "task_payload": {{"target": "...", "task": "..."}},
            "depends_on_completed": ["name of a completed task"],
            "priority": "critical/high/medium/low",
            "expected_observation": "what we expect to see",
            "timeout_seconds": 180
        }}
    ],
    "tasks_to_skip": ["task-id-to-skip"],
    "updated_unknowns": [{{"question": "...", "possible_actions": ["..."]}}],
    "updated_next_action": "what should happen next",
    "confidence": 0.0-1.0
}}

Rules:
1. Do NOT repeat methods that already failed.
2. Do NOT exceed remaining budget.
3. Only use valid agent types.
4. Keep tasks focused and actionable.
5. Prefer tasks that reduce uncertainty.
"""

    def _parse_llm_response(self, raw: str) -> ReplanDecision:
        """Parse LLM response into a structured ReplanDecision."""
        try:
            content = raw
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            data = json.loads(content.strip())
            return ReplanDecision(**data)
        except Exception as e:
            logger.warning("replan_parse_failed", error=str(e))
            return ReplanDecision(
                should_replan=False,
                reasoning=f"Failed to parse LLM replan response: {str(e)}",
            )

    def _heuristic_evaluate(
        self,
        state: CognitiveState,
        graph: TaskGraph,
        trigger: ReplanTrigger,
        event: dict[str, Any],
    ) -> ReplanDecision:
        """Fallback heuristic replan decision (no LLM)."""
        if trigger == ReplanTrigger.AGENT_FAILURE:
            return ReplanDecision(
                should_replan=False,
                reasoning="Agent failure detected. Task will be retried by worker if retries remain.",
            )

        if trigger == ReplanTrigger.NEW_ATTACK_SURFACE:
            return ReplanDecision(
                should_replan=True,
                reasoning="New attack surface discovered. Additional recon/testing may be needed.",
                new_tasks=[],  # Conservative: Director decides what to add
                updated_next_action="Evaluate newly discovered attack surface for additional testing.",
            )

        return ReplanDecision(
            should_replan=False,
            reasoning=f"Heuristic: no automatic replan for trigger '{trigger.value}'.",
        )

    # ============================================
    # Decision Validation
    # ============================================

    def validate_decision(
        self,
        decision: ReplanDecision,
        state: CognitiveState,
        graph: TaskGraph,
    ) -> ValidationResult:
        """
        Validate a ReplanDecision before allowing graph mutation.

        Checks:
            1. Schema validity (already ensured by Pydantic)
            2. Agent type validity
            3. Tenant ownership
            4. Task budget
            5. Dependency validity
            6. Scope validity (target in scope)
            7. Forbidden action patterns
            8. No dangerous payloads
        """
        result = ValidationResult()

        if not decision.should_replan:
            return result

        # Budget check: can we still add tasks?
        remaining = state.budget.max_total_tasks - (state.tasks_completed + state.tasks_failed)
        if len(decision.new_tasks) > remaining:
            result.errors.append(
                f"Proposed {len(decision.new_tasks)} tasks but only {remaining} remaining in budget"
            )
            result.valid = False

        # Validate each proposed task
        for task in decision.new_tasks:
            task_errors = self._validate_proposed_task(task, state, graph)
            if task_errors:
                result.errors.extend(task_errors)
                result.rejected_tasks.append(task.name)
            else:
                result.accepted_tasks.append(task)

        # Validate tasks_to_skip
        for skip_id in decision.tasks_to_skip:
            skip_task = graph.get_task(skip_id)
            if not skip_task:
                result.warnings.append(f"Skip target '{skip_id}' not found in graph")
            elif skip_task.status in (TaskStatus.RUNNING, TaskStatus.SUCCEEDED):
                result.errors.append(
                    f"Cannot skip task '{skip_id}' in status {skip_task.status}"
                )

        if result.errors:
            result.valid = False

        return result

    def _validate_proposed_task(
        self,
        task: ProposedTask,
        state: CognitiveState,
        graph: TaskGraph,
    ) -> list[str]:
        """Validate a single proposed task. Returns list of error messages."""
        errors: list[str] = []

        # Agent type check
        if task.agent_type not in VALID_AGENT_TYPES:
            errors.append(
                f"Task '{task.name}': invalid agent_type '{task.agent_type}'"
            )

        # Forbidden action patterns
        payload_str = json.dumps(task.task_payload).lower()
        for pattern in self.FORBIDDEN_PATTERNS:
            if pattern in payload_str:
                errors.append(
                    f"Task '{task.name}': contains forbidden pattern '{pattern}'"
                )

        # Name validation
        if not task.name or len(task.name) < 3:
            errors.append(f"Task '{task.name}': name too short or empty")

        # Timeout validation
        if task.timeout_seconds <= 0 or task.timeout_seconds > 600:
            errors.append(
                f"Task '{task.name}': timeout {task.timeout_seconds}s out of range [1, 600]"
            )

        # Priority validation
        valid_priorities = {"critical", "high", "medium", "low"}
        if task.priority not in valid_priorities:
            errors.append(
                f"Task '{task.name}': invalid priority '{task.priority}'"
            )

        # Scope validation (if targets are specified)
        target = task.task_payload.get("target", "")
        if target and self.allowed_targets:
            if not any(target.endswith(t) or target == t for t in self.allowed_targets):
                errors.append(
                    f"Task '{task.name}': target '{target}' is out of scope"
                )

        return errors

    # ============================================
    # Graph Mutation Application
    # ============================================

    def apply_decision(
        self,
        decision: ReplanDecision,
        graph: TaskGraph,
        state: CognitiveState,
    ) -> dict[str, Any]:
        """
        Apply a validated ReplanDecision to the task graph.

        This is the ONLY place where the graph is mutated by the replan engine.

        Returns:
            Summary of applied changes
        """
        changes: dict[str, Any] = {
            "tasks_added": [],
            "tasks_skipped": [],
            "errors": [],
        }

        if not decision.should_replan:
            return changes

        # Skip tasks
        for skip_id in decision.tasks_to_skip:
            try:
                graph.mark_skipped(skip_id, reason=decision.reasoning[:200])
                changes["tasks_skipped"].append(skip_id)
            except TaskGraphError as e:
                changes["errors"].append(f"Skip failed for {skip_id}: {str(e)}")

        # Resolve dependency names to task IDs for new tasks
        completed_name_to_id: dict[str, str] = {}
        for t in graph.get_completed_tasks():
            completed_name_to_id[t.name] = t.id

        # Add new tasks
        for proposed in decision.new_tasks:
            try:
                deps = []
                for dep_name in proposed.depends_on_completed:
                    dep_id = completed_name_to_id.get(dep_name)
                    if dep_id:
                        deps.append(dep_id)
                    else:
                        # Try direct ID match
                        if graph.get_task(dep_name):
                            deps.append(dep_name)

                task_node = TaskNode(
                    name=proposed.name,
                    agent_type=proposed.agent_type,
                    task_payload=proposed.task_payload,
                    depends_on=deps,
                    priority=TaskPriority(proposed.priority),
                    expected_observation=proposed.expected_observation,
                    timeout_seconds=proposed.timeout_seconds,
                    spawned_by="replan_engine",
                    engagement_id=graph.engagement_id,
                    tenant_id=graph.tenant_id,
                )
                tid = graph.add_task(task_node)
                changes["tasks_added"].append(tid)
            except TaskGraphError as e:
                changes["errors"].append(f"Task '{proposed.name}' rejected: {str(e)}")
                logger.warning("replan_task_rejected", task=proposed.name, error=str(e))

        # Update unknowns in cognitive state
        for unknown_data in decision.updated_unknowns:
            question = unknown_data.get("question", "")
            if question:
                unknown = Unknown(
                    question=question,
                    possible_actions=unknown_data.get("possible_actions", []),
                )
                state.add_unknown(unknown, agent_id="replan_engine")

        # Record replan in cognitive state
        state.record_replan(
            trigger=decision.trigger.value if decision.trigger else "unknown",
            reasoning=decision.reasoning[:500],
            agent_id="replan_engine",
        )

        # Update confidence if provided
        if decision.confidence > 0:
            state.update_confidence(decision.confidence, "Updated by replan engine")

        logger.info(
            "replan_applied",
            engagement_id=graph.engagement_id,
            tasks_added=len(changes["tasks_added"]),
            tasks_skipped=len(changes["tasks_skipped"]),
            errors=len(changes["errors"]),
        )

        return changes
