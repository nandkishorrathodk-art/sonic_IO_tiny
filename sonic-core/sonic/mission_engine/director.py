"""
SONIC-REDA — Mission Director Engine (Phase 15)
=================================================
Top-level autonomous Mission Owner orchestrating the complete lifecycle:
Decomposition -> Planning -> Resource Allocation -> Multi-Track Execution ->
Computer Operation -> Verification -> Replanning -> Deliverable Generation.
"""

from __future__ import annotations

import time
from typing import Any

from sonic.computer.models import ComputerWorkspaceType
from sonic.computer.provider import UnifiedComputerProvider
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import ComputerAutonomyLevel, EngineeringMissionMode
from sonic.logger import get_logger
from sonic.mission_engine.models import (
    MilestoneStatus,
    MissionDeliverable,
    MissionEvent,
    MissionKnowledgeSummary,
    MissionMilestone,
    MissionObjective,
    MissionOutcome,
    MissionPhase,
    MissionPlan,
    MissionState,
    MissionStatus,
    _new_id,
    _now,
)
from sonic.mission_engine.resource_manager import MissionResourceManager
from sonic.mission_engine.store import MissionStateStore

logger = get_logger(__name__)


class MissionDirector:
    """
    Autonomous Mission Owner coordinating long-horizon missions across
    Cognitive Reasoning, Research Tracks, Computer Workspaces, and Verification.
    """

    def __init__(
        self,
        computer_provider: UnifiedComputerProvider,
        resource_manager: MissionResourceManager | None = None,
        autonomy_level: ComputerAutonomyLevel = ComputerAutonomyLevel.L3_AUTONOMOUS,
        state_store: MissionStateStore | None = None,
        model_router: Any | None = None,
    ):
        self.computer = computer_provider
        self.resource_mgr = resource_manager or MissionResourceManager()
        self.autonomy_level = autonomy_level
        if model_router is not None:
            self.model_router = model_router
        else:
            try:
                from sonic.llm.router import ModelRouter
                self.model_router = ModelRouter()
            except Exception:
                self.model_router = None

        # Active missions state cache (in-memory, persisted to store on mutation)
        self.missions: dict[str, MissionState] = {}
        self.events: dict[str, list[MissionEvent]] = {}
        self.deliverables: dict[str, list[MissionDeliverable]] = {}

        # Persistent backing store (Redis with in-memory fallback)
        self.store = state_store or MissionStateStore()

    async def connect_store(self) -> bool:
        """Initialize the state store connection. Call once at startup."""
        return await self.store.connect()

    async def _persist_mission(self, mission_id: str) -> None:
        state = self.missions.get(mission_id)
        if state:
            await self.store.save_state(state)
            events = self.events.get(mission_id, [])
            for evt in events:
                await self.store.append_event(evt)
            if self.deliverables.get(mission_id):
                await self.store.save_deliverables(mission_id, self.deliverables[mission_id])

    async def restore_mission(self, mission_id: str) -> MissionState | None:
        """Load a mission from the persistent store into the in-memory cache."""
        state = await self.store.load_state(mission_id)
        if not state:
            return None
        self.missions[mission_id] = state
        self.events[mission_id] = await self.store.load_events(mission_id)
        self.deliverables[mission_id] = await self.store.load_deliverables(mission_id)
        logger.info("mission_restored", mission_id=mission_id, status=state.status)
        return state

    async def restore_all(self) -> list[str]:
        """Restore all persisted missions into the in-memory cache (startup recovery)."""
        ids = await self.store.list_mission_ids()
        for mid in ids:
            await self.restore_mission(mid)
        return ids

    # =============================================================
    # 1. Mission Creation & Objective Understanding
    # =============================================================
    async def create_mission(
        self,
        tenant_id: str,
        goal: str,
        constraints: list[str] | None = None,
        scope: list[str] | None = None,
        budget_dollars: float = 25.0,
        deadline_seconds: int = 3600,
    ) -> MissionState:
        """Create and initialize a new top-level autonomous mission."""
        mission_id = _new_id("msn")

        objective = MissionObjective(
            tenant_id=tenant_id,
            mission_id=mission_id,
            goal=goal,
            constraints=constraints or ["Zero host execution", "Strict tenant isolation"],
            scope=scope or ["/home/sonic/workspace", "http://127.0.0.1:8080"],
            success_criteria=["Remediate vulnerability", "100% unit tests passing", "Clean git commit created"],
            failure_criteria=["Host safety violation", "Budget exhaustion", "Deadlock without recovery"],
            budget_dollars=budget_dollars,
            deadline_seconds=deadline_seconds,
        )

        self.resource_mgr.register_mission(mission_id, budget_dollars=budget_dollars)

        state = MissionState(
            mission_id=mission_id,
            tenant_id=tenant_id,
            objective=objective,
            current_phase=MissionPhase.DISCOVERY,
            status=MissionStatus.PLANNING,
            current_next_action="Decompose mission objective into research and engineering plan",
        )

        self.missions[mission_id] = state
        self.events[mission_id] = []
        self.deliverables[mission_id] = []

        self._record_event(mission_id, "MissionStarted", {"goal": goal, "tenant_id": tenant_id})
        await self._persist_mission(mission_id)
        logger.info("mission_created", mission_id=mission_id, goal=goal)

        # Automatically decompose objective into initial plan
        await self.decompose_mission(mission_id)
        return state

    # =============================================================
    # 2. Objective Decomposition & Adaptive Planning
    # =============================================================
    async def decompose_mission(self, mission_id: str) -> MissionPlan:
        """Decomposes a high-level goal into structured phases, questions, tracks, and milestones."""
        state = self._require_mission(mission_id)

        questions = [
            f"What is the root cause of the issue described in: '{state.objective.goal}'?",
            "Which source files and test fixtures define this system behavior?",
            "What security boundaries or side-effects exist for remediation candidate?",
        ]

        tracks = [
            "Track-A: Source Code & Repository Analysis",
            "Track-B: Test Fixture & Defect Reproduction",
            "Track-C: Patch Formulation & Verification",
        ]

        milestones = [
            MissionMilestone(
                mission_id=mission_id,
                name="Milestone 1: Repository & Defect Inspection",
                objective="Locate failing functionality and vulnerable code pathways",
                success_conditions=["Vulnerable code file identified", "Test failure reproduced"],
                status=MilestoneStatus.ACTIVE,
            ),
            MissionMilestone(
                mission_id=mission_id,
                name="Milestone 2: Remediation & Unit Test Validation",
                objective="Apply fix and verify test suite passes without regressions",
                success_conditions=["Patch written to disk", "All unit tests passing"],
                dependencies=["Milestone 1"],
                status=MilestoneStatus.PENDING,
            ),
            MissionMilestone(
                mission_id=mission_id,
                name="Milestone 3: Git Commit & Deliverable Finalization",
                objective="Create commit and export verified deliverable report",
                success_conditions=["Git commit created", "Evidence custody chain signed"],
                dependencies=["Milestone 2"],
                status=MilestoneStatus.PENDING,
            ),
        ]

        plan = MissionPlan(
            mission_id=mission_id,
            objective=state.objective.goal,
            research_questions=questions,
            investigation_tracks=tracks,
            milestones=milestones,
            stop_conditions=["Goal satisfied with verified tests", "Budget exhausted"],
            version=1,
        )

        state.current_plan = plan
        state.open_questions = list(questions)
        state.active_tracks = list(tracks)
        state.remaining_unknowns = [
            f"Verification of: {state.objective.goal[:60]}",
            "Downstream impact and blast radius",
        ] if state.objective and state.objective.goal else [
            "Root cause analysis",
            "Remediation verification",
        ]
        state.status = MissionStatus.ACTIVE

        self._record_event(mission_id, "PlanDecomposed", {"version": 1, "milestones": len(milestones)})
        return plan

    # =============================================================
    # 3. Execution Coordination & Computer Operation
    # =============================================================
    async def coordinate(self, mission_id: str) -> MissionState:
        """Executes the complete long-horizon mission lifecycle autonomously."""
        state = self._require_mission(mission_id)
        t_start = time.perf_counter()

        try:
            # 1. Phase: DISCOVERY & Computer Workspace Allocation
            state.current_phase = MissionPhase.DISCOVERY
            ws = await self.computer.create(
                tenant_id=state.tenant_id,
                engagement_id=state.mission_id,
                workspace_type=ComputerWorkspaceType.MISSION_COMPUTER,
            )
            state.computer_workspaces.append(ws.id)
            self.resource_mgr.allocate_sandbox(mission_id, ws.id)
            self._record_event(mission_id, "ComputerCreated", {"workspace_id": ws.id})

            # 2. Phase: UNDERSTANDING & RESEARCH
            state.current_phase = MissionPhase.RESEARCH
            # Hypotheses are seeded from the objective's own constraints/scope,
            # not a hardcoded vulnerability name.
            if state.objective.constraints:
                state.active_hypotheses.append(
                    f"Working hypothesis derived from constraints: {'; '.join(state.objective.constraints[:2])}"
                )
            else:
                state.active_hypotheses.append(
                    f"Investigate the root cause of: {state.objective.goal}"
                )
            state.evidence.append(f"Mission initialized in workspace {ws.id}")

            # 3. Phase: ENGINEERING (Delegate to ComputerUseAgent)
            state.current_phase = MissionPhase.ENGINEERING
            # Wire the REAL security-tool adapters (in-sandbox, fail-closed) so
            # the agent can dispatch scans as a first-class reasoning action.
            # Bind to the underlying ComputeProvider (UnifiedComputerProvider
            # delegates terminal exec to it; SecurityTool.execute calls execute()).
            # Wire the browser into the unified action surface so the agent can
            # navigate/click/type/screenshot as a first-class reasoning action
            # (was orphaned — BrowserAgent existed but no caller passed browser=).
            from sonic.agents.browser_agent import BrowserAgent
            from sonic.being.toolsmith import ToolsmithLoop
            from sonic.being.method_lab import MethodLab
            from sonic.being.craft import BeingCraft
            from sonic.memory.vector import get_vector_memory
            from sonic.safety.sealed import seal_default
            browser = BrowserAgent(headless=True)
            await browser.launch()
            toolsmith = ToolsmithLoop(
                craft=BeingCraft(being_id=f"mission-{mission_id}"),
                llm=self.model_router,
                registry=None,
            )
            method_lab = MethodLab(
                llm=self.model_router,
                vector_memory=get_vector_memory(),
                toolsmith=toolsmith,
            )
            from sonic.being.lessons import LessonsLedger
            obj_tenant = getattr(state.objective, "tenant_id", "default") if hasattr(state, "objective") else "default"
            lessons_ledger = LessonsLedger(tenant_id=obj_tenant, agent_id="computer-use-agent")

            workspace_root = "/home/sonic/workspace"
            if getattr(state, "objective", None) and getattr(state.objective, "scope", None):
                for s in state.objective.scope:
                    if s.startswith("/"):
                        workspace_root = s
                        break
            safety_policy = seal_default(workspace_root=workspace_root)

            from sonic.tools.computer_as_compute_provider import ComputerAsComputeProvider
            from sonic.tools.registry import get_default_registry

            # THE LLM BRAIN + REAL security tools — previously omitted, so the
            # production agent fell back to _diagnostic_fallback() (re-reading the
            # same file) instead of reasoning. This is the machine's mind.
            security_registry = get_default_registry(
                ComputerAsComputeProvider(self.computer)
            )

            agent = ComputerUseAgent(
                computer_provider=self.computer,
                llm_router=self.model_router,
                security_tools=security_registry.as_dict(),
                autonomy_level=self.autonomy_level,
                mode=EngineeringMissionMode.ENGINEERING_MODE,
                browser=browser,
                safety=safety_policy,
                toolsmith=toolsmith,
                method_lab=method_lab,
                lessons_ledger=lessons_ledger,
            )
            mission_steps = getattr(self, "max_actions", getattr(agent, "max_actions", 25))
            traces = await agent.run_mission(
                workspace_id=ws.id,
                goal=state.objective.goal,
                steps=mission_steps,
            )
            # Stash traces so get_knowledge_summary / re-finalize can derive
            # honest artifacts without re-running the agent.
            object.__setattr__(state, "_last_traces", traces)

            # Record Resource Consumption derived from actual execution
            num_traces = len(traces)
            est_tokens = sum(len(getattr(t, "actual_observation", "") or "") // 4 + 400 for t in traces) if traces else 250
            est_dollars = round((est_tokens / 1_000_000.0) * 1.50, 4)
            self.resource_mgr.record_spend(
                mission_id=mission_id,
                dollars=est_dollars,
                tokens=est_tokens,
                compute_seconds=round(time.perf_counter() - t_start, 2),
            )

            # Update Milestones — COMPLETED only where traces prove progress,
            # never force-completed by decree.
            from sonic.mission_engine.trace_synthesis import milestone_status_from_traces
            updated_milestones, progress = milestone_status_from_traces(traces, state.current_plan)
            if updated_milestones and state.current_plan:
                state.current_plan.milestones = updated_milestones
            state.progress_pct = progress

            # 4. Phase: VERIFICATION & REPORTING
            state.current_phase = MissionPhase.VERIFICATION
            # Confidence is derived from the agent's actual success ratio.
            total_actions = len(traces)
            successful = sum(1 for t in traces if t.status in ("SUCCESS", "RECOVERED"))
            state.confidence = round(successful / total_actions, 2) if total_actions else 0.0
            state.completed_tracks = list(state.active_tracks)
            state.active_tracks = []
            state.remaining_unknowns = [] if successful else state.remaining_unknowns

            # 5. Finalize Deliverables — derived from the agent's real actions.
            await self.finalize(mission_id, traces=traces)

            # Outcome reflects reality: success only if the agent actually did
            # something that succeeded.
            state.current_phase = MissionPhase.COMPLETED
            success_ratio = (successful / total_actions) if total_actions else 0.0
            deliverables_count = len(self.deliverables.get(mission_id, []))

            if successful > 0 and success_ratio >= 0.60 and deliverables_count > 0:
                state.status = MissionStatus.COMPLETED
                state.outcome = MissionOutcome.SUCCESS
                state.current_next_action = (
                    f"Mission completed: {successful}/{total_actions} actions succeeded; "
                    f"{deliverables_count} deliverables produced."
                )
            elif successful > 0:
                state.status = MissionStatus.COMPLETED
                state.outcome = MissionOutcome.PARTIAL_SUCCESS
                state.current_next_action = (
                    f"Mission completed with partial success: {successful}/{total_actions} actions succeeded; "
                    f"{deliverables_count} deliverables produced."
                )
            else:
                state.status = MissionStatus.COMPLETED
                state.outcome = MissionOutcome.FAILED
                state.current_next_action = (
                    f"Mission ended with no successful actions ({total_actions} attempted)."
                )

            self._record_event(mission_id, "MissionCompleted", {"outcome": "SUCCESS", "traces": len(traces)})
            await self._persist_mission(mission_id)

        except Exception as e:
            logger.error("mission_coordination_failed", mission_id=mission_id, error=str(e))
            state.status = MissionStatus.FAILED
            state.outcome = MissionOutcome.FAILED
            self._record_event(mission_id, "MissionFailed", {"error": str(e)})
            await self._persist_mission(mission_id)

        state.updated_at = _now()
        await self._persist_mission(mission_id)
        return state

    # =============================================================
    # 4. Dynamic Replanning & Self-Correction
    # =============================================================
    async def replan(self, mission_id: str, trigger: str, context: dict[str, Any]) -> MissionPlan:
        """Adapts the mission plan in response to new evidence or unexpected errors."""
        state = self._require_mission(mission_id)
        if not state.current_plan:
            return await self.decompose_mission(mission_id)

        plan = state.current_plan
        plan.version += 1
        plan.research_questions.append(f"Diagnostic Question: What caused trigger '{trigger}'?")
        plan.stop_conditions.append(f"Verify recovery from {trigger}")

        self._record_event(mission_id, "PlanReplanned", {"trigger": trigger, "version": plan.version, "context": context})
        logger.info("mission_replanned", mission_id=mission_id, trigger=trigger, version=plan.version)
        return plan

    # =============================================================
    # 5. Human Intervention Controls (Pause / Resume / Cancel)
    # =============================================================
    async def pause_mission(self, mission_id: str) -> bool:
        """Pause mission execution preserving state."""
        state = self._require_mission(mission_id)
        state.status = MissionStatus.PAUSED
        state.current_phase = MissionPhase.PAUSED
        state.current_next_action = "Mission paused by operator. Awaiting resume instruction."
        self._record_event(mission_id, "MissionPaused", {"actor": "operator"})
        await self._persist_mission(mission_id)
        return True

    async def resume_mission(self, mission_id: str) -> bool:
        """Resume a paused mission."""
        state = self._require_mission(mission_id)
        state.status = MissionStatus.ACTIVE
        state.current_phase = MissionPhase.ENGINEERING
        state.current_next_action = "Mission resumed. Continuing autonomous coordination."
        self._record_event(mission_id, "MissionResumed", {"actor": "operator"})
        await self._persist_mission(mission_id)
        return True

    async def cancel_mission(self, mission_id: str, reason: str = "Operator cancelled") -> bool:
        """Cancel mission execution."""
        state = self._require_mission(mission_id)
        state.status = MissionStatus.CANCELLED
        state.current_phase = MissionPhase.CANCELLED
        state.outcome = MissionOutcome.FAILED
        state.current_next_action = f"Mission cancelled: {reason}"
        self._record_event(mission_id, "MissionCancelled", {"reason": reason})
        await self._persist_mission(mission_id)
        return True

    # =============================================================
    # 6. Deliverables & Knowledge Summary
    # =============================================================
    async def finalize(self, mission_id: str, traces: list | None = None) -> list[MissionDeliverable]:
        """Generates validated final deliverables derived from the agent's traces.

        No traces (or no successful artifact-producing action) → empty list
        (honest: no fabricated deliverables). Re-derive on each call so a
        re-finalize after more actions stays accurate.
        """
        from sonic.computer_use.models import ComputerDecisionTrace
        from sonic.mission_engine.trace_synthesis import synthesize_deliverables

        state = self._require_mission(mission_id)
        # Prefer explicitly-passed traces; fall back to any previously stored.
        trace_list = traces or getattr(state, "_last_traces", []) or []
        deliverables = synthesize_deliverables(
            mission_id, state.objective.goal,
            [t for t in trace_list if isinstance(t, ComputerDecisionTrace)],
        )
        self.deliverables[mission_id] = deliverables
        self._record_event(mission_id, "DeliverablesFinalized", {"count": len(deliverables)})
        return deliverables

    def get_knowledge_summary(self, mission_id: str) -> MissionKnowledgeSummary:
        """Generates a structured knowledge snapshot derived from the agent's
        actual traces — not hardcoded vulnerability strings."""
        from sonic.mission_engine.trace_synthesis import synthesize_knowledge

        state = self._require_mission(mission_id)
        res_summary = self.resource_mgr.get_resource_summary(mission_id)
        traces = getattr(state, "_last_traces", []) or []
        summary = synthesize_knowledge(
            goal=state.objective.goal,
            traces=traces,
            remaining_unknowns=state.remaining_unknowns,
            active_tracks=state.active_tracks,
        )
        summary.current_hypotheses = state.active_hypotheses
        summary.resource_state = res_summary
        return summary

    # =============================================================
    # Helpers
    # =============================================================
    def _require_mission(self, mission_id: str) -> MissionState:
        state = self.missions.get(mission_id)
        if not state:
            raise KeyError(f"Mission '{mission_id}' not found.")
        return state

    def _record_event(self, mission_id: str, event_type: str, payload: dict[str, Any]) -> None:
        evt = MissionEvent(mission_id=mission_id, event_type=event_type, payload=payload)
        self.events.setdefault(mission_id, []).append(evt)
