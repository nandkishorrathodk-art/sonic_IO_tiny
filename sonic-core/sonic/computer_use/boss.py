"""Boss Agent: Strategic Thinker & SubAgent Orchestrator.

The Boss Agent is the brain of the SONIC orchestration system. It:
1. Receives an objective from the user
2. Deep-thinks about what's needed (strategic decomposition)
3. Creates focused sub-missions and dispatches them to SubAgents
4. Collects all SubAgent reports
5. Analyzes findings and plans next phase
6. Repeats until objective is complete
7. Synthesizes a final comprehensive report

The Boss NEVER executes terminal commands, GUI actions, or browser actions
directly. It only THINKS (via LLM) and DELEGATES (via SubAgents). Each
SubAgent is a fresh ComputerUseAgent instance with a focused goal and limited
steps, executing on the shared workstation.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Callable, Optional

import structlog

from sonic.agents.replan import (
    ReplanEngine,
    ReplanTrigger,
)
from sonic.agents.task_graph import (
    TaskGraph,
    TaskNode,
    TaskPriority,
    TaskStatus,
)
from sonic.computer_use.models_boss import (
    BossReport,
    BossThinking,
    Phase,
    SubMission,
    SubMissionResult,
)

logger = structlog.get_logger(__name__)


def _trace_value(trace: Any, name: str, default: Any = "") -> Any:
    """Read trace fields from both model instances and serialized history."""
    if isinstance(trace, dict):
        return trace.get(name, default)
    return getattr(trace, name, default)


class BossAgent:
    """Strategic orchestrator that delegates work to SubAgent workers.

    Parameters
    ----------
    computer_provider : ComputerProvider
        The shared workstation provider all SubAgents execute on.
    llm_router : ModelRouter
        LLM router for the Boss's strategic thinking.
    safety : ActionPolicy | SealedActionPolicy | None
        Safety envelope inherited by every SubAgent.
    security_tools : dict | None
        Security tool registry passed to SubAgents.
    tenant_id : str
        Tenant isolation identifier.
    max_phases : int
        Maximum number of phases before the Boss stops.
    sub_agent_steps : int
        Default max steps each SubAgent gets per sub-mission.
    """

    def __init__(
        self,
        computer_provider: Any,
        llm_router: Any,
        safety: Any = None,
        security_tools: dict[str, Any] | None = None,
        tenant_id: str = "default",
        max_phases: int = 5,
        sub_agent_steps: int = 5,
        max_parallel_workers: int = 4,
        browser: Any = None,
        toolsmith: Any = None,
        method_lab: Any = None,
        lessons_ledger: Any = None,
        evolution_engine: Any = None,
    ):
        self.computer = computer_provider
        self.llm_router = llm_router
        self.safety = safety
        self.security_tools = security_tools or {}
        self.tenant_id = tenant_id
        self.max_phases = max_phases
        self.sub_agent_steps = sub_agent_steps
        # Explicit concurrency budget: the Boss may never create more live
        # workers than this configured bound in a dependency wave.
        self.max_parallel_workers = max(1, int(max_parallel_workers))
        self.browser = browser
        self.toolsmith = toolsmith
        self.method_lab = method_lab
        self.lessons_ledger = lessons_ledger
        self.evolution_engine = evolution_engine
        if self.evolution_engine is None:
            try:
                from sonic.evolution.engine import EvolutionEngine
                from sonic.evolution.strategy import DynamicStrategyEngine
                self.evolution_engine = EvolutionEngine(
                    strategy_engine=DynamicStrategyEngine(),
                    method_lab=self.method_lab,
                    toolsmith=self.toolsmith,
                    lessons_ledger=self.lessons_ledger,
                )
            except Exception as e:
                logger.warning("boss_lazy_evolution_engine_failed", error=str(e))

        # State
        self.phases: list[Phase] = []
        self.thinking_log: list[BossThinking] = []
        self.all_traces: list[Any] = []
        self._sub_agent_count: int = 0
        self._interrupted: bool = False
        self._accumulated_context: list[str] = []

        # DAG & Replan Engine
        self.task_graph = TaskGraph(
            engagement_id=f"boss-{self.tenant_id}",
            tenant_id=self.tenant_id,
            max_total_tasks=100,
        )
        self.replan_engine = ReplanEngine()

    def interrupt(self) -> None:
        """Signal the Boss to stop orchestration."""
        self._interrupted = True

    def _sync_phase_to_graph(self, phase: Phase) -> None:
        """Register phase sub-missions into TaskGraph DAG."""
        for sub in phase.sub_missions:
            if sub.id in self.task_graph._tasks:
                continue
            valid_deps = [
                d for d in sub.depends_on
                if d in self.task_graph._tasks
            ]
            priority = TaskPriority.HIGH if sub.priority > 1 else TaskPriority.MEDIUM
            tn = TaskNode(
                id=sub.id,
                name=sub.goal[:60],
                agent_type="dynamic",
                task_payload={"goal": sub.goal, "max_steps": sub.max_steps},
                depends_on=valid_deps,
                priority=priority,
                engagement_id=self.task_graph.engagement_id,
                tenant_id=self.task_graph.tenant_id,
            )
            try:
                self.task_graph.add_task(tn)
            except Exception as exc:
                logger.debug("task_graph_add_skipped", sub_id=sub.id, error=str(exc))

    def _detect_sub_mission_trigger(self, result: SubMissionResult) -> ReplanTrigger | None:
        """Inspect sub-mission outcome to determine if replanning is warranted.

        Covers full security domain taxonomy (web, API, binary/pwn, network, crypto, CTF flags)
        with negation guards so phrases like 'not vulnerable to sqli' do not falsely trigger.
        """
        if not result.success:
            return ReplanTrigger.AGENT_FAILURE

        combined_text = (
            result.findings_summary + " " + " ".join(result.key_discoveries)
        ).lower()

        if not combined_text.strip():
            return None

        vuln_patterns = (
            # Web & API
            r"\bsqli\b", r"\bsql injection\b", r"\bxss\b", r"\brce\b", r"\bcve-\d{4}-\d+\b",
            r"\bssrf\b", r"\bidor\b", r"\bbola\b", r"\bdeserializ", r"\bprototype pollution\b",
            r"\bpath traversal\b", r"\blfi\b", r"\brfi\b",
            r"\bauth(?:entication)? bypass\b", r"\bunauthorized access\b",
            # Binary & Systems
            r"\bbuffer overflow\b", r"\bmemory corruption\b", r"\brop chain\b",
            r"\bformat string\b", r"\buse[- ]after[- ]free\b", r"\bheap overflow\b",
            r"\bprivilege escalation\b", r"\broot shell\b",
            # Crypto & Secrets
            r"\bpadding oracle\b", r"\bweak key\b", r"\bprivate key leak\b",
            r"\bcredential leak\b", r"\bhardcoded secret\b",
            # Flags & Exploit Confirmation
            r"\bflag\{[^\}]+\}", r"\bctf\{[^\}]+\}", r"\bhtb\{[^\}]+\}",
            r"\bexploit confirmed\b", r"\bvulnerability confirmed\b",
        )

        negation_prefix = r"(?:not|no|never|failed to|unsuccessful|immune to|false positive)\s+(?:\w+\s+){0,3}"

        for pat in vuln_patterns:
            matches = list(re.finditer(pat, combined_text, flags=re.IGNORECASE))
            for m in matches:
                start_idx = m.start()
                preceding_text = combined_text[max(0, start_idx - 40):start_idx]
                if re.search(negation_prefix + r"$", preceding_text, flags=re.IGNORECASE):
                    continue
                return ReplanTrigger.NEW_HIGH_CONFIDENCE_FINDING

        surface_patterns = (
            r"\bopen port\b", r"\blistening port\b", r"\bdiscovered service\b",
            r"\bendpoint\b", r"\broute\b", r"\bsubdomain\b", r"\bapi url\b",
            r"\blogin page\b", r"\bexported symbol\b", r"\bhidden directory\b",
        )
        for sp in surface_patterns:
            if re.search(sp, combined_text, flags=re.IGNORECASE):
                return ReplanTrigger.NEW_ATTACK_SURFACE

        return None

    # ------------------------------------------------------------------
    # Main orchestration loop
    # ------------------------------------------------------------------

    async def run(
        self,
        workspace_id: str,
        objective: str | Any,
        phase_callback: Optional[Callable] = None,
        interrupt_check: Optional[Callable] = None,
    ) -> BossReport:
        """Run the full Boss Agent orchestration loop.

        Parameters
        ----------
        workspace_id : str
            The workstation workspace ID where SubAgents execute.
        objective : str
            The user's objective to accomplish.
        phase_callback : callable, optional
            Called with (event_type, data) for real-time UI streaming.
            Event types: "boss_thinking", "sub_dispatch", "sub_report",
            "phase_complete", "boss_report".
        interrupt_check : callable, optional
            Returns True if the user wants to stop.

        Returns
        -------
        BossReport
            Complete structured report of the orchestration.
        """
        t_start = time.perf_counter()
        self._interrupted = False

        if hasattr(objective, "goal"):
            objective = objective.goal
        elif not isinstance(objective, str):
            objective = str(objective)

        logger.info("boss_agent_start", objective=objective[:200])

        # Phase 1: Strategic decomposition (if not already populated)
        if not self.phases:
            first_phase = await self._strategic_decomposition(objective)
            if not first_phase or not first_phase.sub_missions:
                # Objective is too simple for Boss — return minimal report
                logger.info("boss_agent_simple_objective", objective=objective[:100])
                return BossReport(
                    objective=objective,
                    status="COMPLETE",
                    findings_summary="Objective is simple enough for direct execution.",
                    duration_seconds=round(time.perf_counter() - t_start, 2),
                )

            self.phases.append(first_phase)
            self._sync_phase_to_graph(first_phase)
        else:
            self._sync_phase_to_graph(self.phases[0])

        # Execute phases
        for phase_idx in range(self.max_phases):
            if self._interrupted or (callable(interrupt_check) and interrupt_check()):
                logger.info("boss_agent_interrupted", phase=phase_idx + 1)
                break

            current_phase = self.phases[-1]
            current_phase.status = "RUNNING"
            current_phase.started_at = self._now()

            # Stream Boss thinking to UI
            await self._emit(phase_callback, "boss_thinking", {
                "phase": current_phase.phase_number,
                "thinking_type": "strategic_decomposition" if phase_idx == 0 else "reaction_planning",
                "content": current_phase.thinking,
            })

            # Dispatch SubAgents in concurrent dependency waves
            completed_sub_ids = {r.sub_mission_id for p in self.phases for r in p.results if r.success}
            pending_subs = list(sorted(current_phase.sub_missions, key=lambda s: -s.priority))

            while pending_subs:
                if self._interrupted or (callable(interrupt_check) and interrupt_check()):
                    break

                # 1. Identify ready sub-missions (dependencies met)
                ready_batch = [
                    s for s in pending_subs
                    if not s.depends_on or all(dep_id in completed_sub_ids for dep_id in s.depends_on)
                ]

                # Check TaskGraph blocked status
                unblocked_ready = []
                for s in ready_batch:
                    tg_task = self.task_graph.get_task(s.id)
                    if tg_task and tg_task.status == TaskStatus.BLOCKED:
                        logger.info("boss_sub_mission_blocked_in_graph", sub_id=s.id)
                        pending_subs.remove(s)
                        continue
                    unblocked_ready.append(s)

                if not unblocked_ready:
                    # Deadlock or unresolvable dependencies among remaining sub-missions
                    for s in pending_subs:
                        s.status = "BLOCKED"
                        if self.task_graph.get_task(s.id):
                            try:
                                self.task_graph.mark_failed(s.id, "Dependencies could not be resolved")
                            except Exception:
                                pass
                    break

                # Respect the configured worker budget.  Dependencies still
                # determine waves; this only bounds concurrent execution.
                wave_batch = unblocked_ready[:self.max_parallel_workers]
                for s in wave_batch:
                    pending_subs.remove(s)

                # Atomically assign subagent numbers
                batch_tasks = []
                for s in wave_batch:
                    self._sub_agent_count += 1
                    batch_tasks.append((s, self._sub_agent_count))

                async def _run_sub_worker(sub_m: SubMission, agent_num: int):
                    sub_m.status = "RUNNING"
                    tg_t = self.task_graph.get_task(sub_m.id)
                    if tg_t:
                        try:
                            self.task_graph.mark_running(sub_m.id)
                        except Exception:
                            pass

                    await self._emit(phase_callback, "sub_dispatch", {
                        "sub_mission_id": sub_m.id,
                        "goal": sub_m.goal,
                        "max_steps": sub_m.max_steps,
                        "sub_agent_number": agent_num,
                    })

                    try:
                        res = await self._dispatch_sub_agent(
                            workspace_id, sub_m, phase_callback, sub_agent_num=agent_num
                        )
                    except Exception as e:
                        logger.error("boss_dispatch_sub_agent_error", sub_id=sub_m.id, error=str(e))
                        res = SubMissionResult(
                            sub_mission_id=sub_m.id,
                            goal=sub_m.goal,
                            success=False,
                            findings_summary=f"Subagent execution failed: {e}",
                            key_discoveries=[],
                            actions_taken=0,
                            duration_seconds=0.0,
                            traces=[],
                        )

                    sub_m.status = "COMPLETED" if res.success else "FAILED"
                    if tg_t:
                        try:
                            if res.success:
                                self.task_graph.mark_completed(sub_m.id, {
                                    "findings": res.key_discoveries,
                                    "summary": res.findings_summary,
                                })
                            else:
                                self.task_graph.mark_failed(sub_m.id, res.findings_summary)
                        except Exception:
                            pass

                    await self._emit(phase_callback, "sub_report", {
                        "sub_mission_id": sub_m.id,
                        "sub_agent_number": agent_num,
                        "goal": sub_m.goal,
                        "success": res.success,
                        "findings_summary": res.findings_summary,
                        "key_discoveries": res.key_discoveries,
                        "actions_taken": res.actions_taken,
                        "duration_seconds": res.duration_seconds,
                    })

                    return res

                # Concurrently execute wave
                if len(batch_tasks) == 1:
                    sm, num = batch_tasks[0]
                    res = await _run_sub_worker(sm, num)
                    wave_results = [res]
                else:
                    logger.info("boss_dispatching_concurrent_wave", wave_size=len(batch_tasks))
                    wave_results = await asyncio.gather(
                        *(_run_sub_worker(sm, num) for sm, num in batch_tasks),
                        return_exceptions=True,
                    )

                for idx, res in enumerate(wave_results):
                    if isinstance(res, Exception):
                        sm, num = batch_tasks[idx]
                        sm.status = "FAILED"
                        res = SubMissionResult(
                            sub_mission_id=sm.id,
                            goal=sm.goal,
                            success=False,
                            findings_summary=f"Subagent unhandled exception: {res}",
                            key_discoveries=[],
                            actions_taken=0,
                            duration_seconds=0.0,
                            traces=[],
                        )
                    current_phase.results.append(res)
                    self.all_traces.extend(res.traces)
                    if res.success:
                        completed_sub_ids.add(res.sub_mission_id)

                    # Replan trigger evaluation on SubAgent result
                    trigger = self._detect_sub_mission_trigger(res)
                    if trigger:
                        trigger_msg = f"⚡ Boss Replan Trigger: {trigger.value.upper()} detected from SubAgent findings. Adjusting tactical priorities."
                        await self._emit(phase_callback, "boss_thinking", {
                            "phase": current_phase.phase_number,
                            "thinking_type": "reaction_planning",
                            "content": trigger_msg,
                        })
                        self.thinking_log.append(BossThinking(
                            phase=current_phase.phase_number,
                            thinking_type="reaction_planning",
                            content=trigger_msg,
                        ))

            current_phase.status = "COMPLETED"
            current_phase.completed_at = self._now()

            await self._emit(phase_callback, "phase_complete", {
                "phase_number": current_phase.phase_number,
                "name": current_phase.name,
                "results_count": len(current_phase.results),
                "success_count": sum(1 for r in current_phase.results if r.success),
            })

            # Aggregate findings from this phase
            aggregated = await self._aggregate_findings(current_phase, objective)

            # Check if objective is complete
            all_findings = self._collect_all_findings()
            is_complete, completion_reason = await self._check_objective_complete(
                objective, all_findings
            )

            if is_complete:
                logger.info("boss_agent_objective_complete", reason=completion_reason[:200])
                break

            # Not complete — plan next phase
            if phase_idx < self.max_phases - 1:
                next_phase = await self._plan_next_phase(
                    objective, all_findings, self.phases
                )
                if next_phase and next_phase.sub_missions:
                    self.phases.append(next_phase)
                    self._sync_phase_to_graph(next_phase)
                else:
                    logger.info("boss_agent_no_more_phases")
                    break

        # Synthesize final report
        report = await self._synthesize_final_report(objective, t_start)

        await self._emit(phase_callback, "boss_report", {
            "status": report.status,
            "total_phases": report.total_phases,
            "total_sub_agents": report.total_sub_agents,
            "total_actions": report.total_actions,
            "findings_summary": report.findings_summary,
        })

        logger.info(
            "boss_agent_complete",
            status=report.status,
            phases=report.total_phases,
            sub_agents=report.total_sub_agents,
            actions=report.total_actions,
            duration=report.duration_seconds,
        )

        return report

    # ------------------------------------------------------------------
    # Strategic Decomposition (LLM Deep Think)
    # ------------------------------------------------------------------

    async def _strategic_decomposition(self, objective: str) -> Phase | None:
        """Analyze the objective and create the first phase of sub-missions.

        The Boss deep-thinks about what sub-tasks are needed to accomplish the
        objective, creates focused sub-missions, and returns them as a Phase.
        """
        t_start = time.perf_counter()

        prompt = f"""You are the Boss Agent of an Autonomous Self-Evolving Penetration Architect (A-SEA).
Your job is to analyze the user's objective from first principles and decompose it into focused, independent sub-missions for worker agents.

USER OBJECTIVE: {objective}

Apply target-agnostic first-principles reasoning:
0. PROGRAM INTAKE:
   If the objective describes a program, repository, binary, service, or
   application, first build a verified profile from the supplied details and
   sandbox observations: modality, entry points, inputs/outputs, trust
   boundaries, dependencies, runtime behavior, unknowns, and evidence needed.
   Do not invent a target, tool, vulnerability, or successful execution.
   If the objective does not state what outcome is wanted, ask for the missing
   analysis objective instead of executing.
1. DOMAIN & MODALITY TRIAGE:
   Identify the primary target type:
   - [BINARY / REVERSE ENGINEERING / PWN]: local executable or firmware, code behavior, memory safety.
   - [NETWORK / INFRASTRUCTURE]: address space, reachable services, routing, and protocol behavior.
   - [API / MICROSERVICE / HEADLESS]: request/response contracts, auth state, schemas, and parameters.
   - [CRYPTOGRAPHY]: ciphers, hashes, oracles, key material, and entropy.
   - [FORENSICS / DATA]: memory, captures, logs, and file artifacts.
   - [WEB APPLICATION]: HTTP state, cookies, DOM, and client behavior when actually required.

2. METHODOLOGY:
   - Do not force an application, scanner, protocol, or interaction modality before observing the target.
   - Each worker must receive a clear, operational task tailored to the specific target modality.

Respond with EXACTLY this JSON format (no extra text):
{{
  "domain": "BINARY | NETWORK | API | CRYPTO | FORENSICS | WEB",
  "thinking": "First-principles analysis: target architecture, hypotheses, and strategy",
  "phase_name": "Domain-appropriate phase name (e.g., Static Binary Analysis, Service Enumeration, Schema Discovery)",
  "sub_missions": [
    {{
      "goal": "Clear, focused goal for this worker agent with concrete inputs and expected observations.",
      "max_steps": 4,
      "priority": 1
    }}
  ]
}}

Rules:
- Each sub_mission goal must be FOCUSED and SPECIFIC (one clear task per worker)
- max_steps should be 3-5 (workers are efficient, not wasteful)
- priority: higher number = execute first
- Create 2-5 sub_missions per phase (not more)
- If the objective is trivially simple (single command), return {{"thinking": "...", "phase_name": "", "sub_missions": []}}"""

        try:
            from sonic.llm.schemas import LLMRequest, Message, MessageRole

            req = LLMRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content="You are an expert task decomposition agent. Output ONLY valid JSON."),
                    Message(role=MessageRole.USER, content=prompt),
                ],
                task_type="planning",
                max_tokens=800,
                temperature=0.3,
            )
            resp = await self.llm_router.complete(req)
            raw = (resp.content or "").strip()
        except Exception as e:
            logger.warning("boss_strategic_decomposition_llm_failed", error=str(e))
            return self._fallback_decomposition(objective)

        duration = round(time.perf_counter() - t_start, 2)

        # Parse LLM response
        parsed = self._parse_json_response(raw)
        if not parsed:
            logger.warning("boss_strategic_decomposition_parse_failed", raw=raw[:300])
            return self._fallback_decomposition(objective)

        thinking = parsed.get("thinking", "Analyzing objective...")
        phase_name = parsed.get("phase_name", "Phase 1")
        sub_missions_raw = parsed.get("sub_missions", [])

        if not sub_missions_raw:
            return None  # Too simple for Boss

        sub_missions = []
        for sm in sub_missions_raw[:5]:  # Cap planning fan-out per phase
            goal = str(sm.get("goal", "")).strip()
            if not goal:
                continue
            requested_steps = sm.get("max_steps", self.sub_agent_steps)
            try:
                requested_steps = int(requested_steps)
            except (TypeError, ValueError):
                requested_steps = self.sub_agent_steps
            sub_missions.append(SubMission(
                goal=goal,
                max_steps=max(1, min(requested_steps, 8)),
                priority=max(0, int(sm.get("priority", 1) or 1)),
            ))

        # Record thinking
        self.thinking_log.append(BossThinking(
            phase=1,
            thinking_type="strategic_decomposition",
            content=thinking,
            duration_seconds=duration,
        ))

        return Phase(
            phase_number=1,
            name=phase_name,
            thinking=thinking,
            sub_missions=sub_missions,
        )

    def _fallback_decomposition(self, objective: str) -> Phase:
        """Provide a tool-agnostic fallback when strategic LLM planning fails.

        This deliberately does not infer an application, scanner, protocol,
        target class, or exploit recipe from keywords. A single adaptive worker
        receives the original objective and must choose its next action from
        live state, then replan when evidence contradicts its hypothesis.
        Splitting this into a fixed "observe then test" chain would turn the
        failure path into a scripted puppet.
        """
        budget = max(1, min(int(self.sub_agent_steps), 8))
        sub_missions = [
            SubMission(
                id="adaptive-investigator",
                goal=(
                    "Pursue this objective autonomously from the current live state: "
                    f"{objective}. First establish the smallest useful evidence, "
                    "choose the least-assumptive execution surface, form a testable "
                    "hypothesis, and adapt after every result. Do not follow a "
                    "predefined tool sequence. Record only reproduced evidence and "
                    "stop when the objective is verified or no safe progress remains."
                ),
                max_steps=budget,
                priority=1,
            ),
        ]

        thinking_text = (
            "LLM strategic decomposition unavailable; delegated the objective to "
            "one bounded adaptive investigator rather than activating a fixed "
            "observation/test pipeline."
        )

        self.thinking_log.append(BossThinking(
            phase=1,
            thinking_type="strategic_decomposition",
            content=thinking_text,
            duration_seconds=0.0,
        ))

        return Phase(
            phase_number=1,
            name="Adaptive Investigation (Fallback)",
            thinking=thinking_text,
            sub_missions=sub_missions,
        )

    # ------------------------------------------------------------------
    # SubAgent Dispatch
    # ------------------------------------------------------------------

    async def _dispatch_sub_agent(
        self,
        workspace_id: str,
        sub_mission: SubMission,
        phase_callback: Optional[Callable] = None,
        sub_agent_num: int = 0,
    ) -> SubMissionResult:
        """Create a focused ComputerUseAgent and run it on a sub-mission.

        Each SubAgent is a FRESH agent with its own traces and history,
        executing on the shared workstation with the inherited safety policy.
        """
        t_start = time.perf_counter()

        try:
            from sonic.computer_use.agent import ComputerUseAgent
            from sonic.computer_use.models import (
                ComputerAutonomyLevel,
                EngineeringMissionMode,
            )

            from sonic.safety.action_policy import ActionPolicy

            safety_policy = (
                self.safety.clone_for_agent(f"sub-{sub_agent_num}")
                if isinstance(self.safety, ActionPolicy)
                else self.safety
            )

            agent = ComputerUseAgent(
                computer_provider=self.computer,
                autonomy_level=ComputerAutonomyLevel.L3_AUTONOMOUS,
                mode=EngineeringMissionMode.GENERAL_ENGINEERING_MODE,
                max_actions=sub_mission.max_steps,
                llm_router=self.llm_router,
                security_tools=self.security_tools,
                safety=safety_policy,
                self_host=True if safety_policy else False,
                tenant_id=self.tenant_id,
                agent_id=f"sub-agent-{sub_agent_num}",
                enable_llm_decomposition=False,
                browser=self.browser,
                toolsmith=self.toolsmith,
                method_lab=self.method_lab,
                lessons_ledger=self.lessons_ledger,
                evolution_engine=self.evolution_engine,
            )

            # Step callback to stream SubAgent actions to UI
            async def _sub_step_callback(trace):
                if phase_callback:
                    await self._emit(phase_callback, "sub_step", {
                        "sub_mission_id": sub_mission.id,
                        "sub_agent_number": sub_agent_num,
                        "trace": {
                                "step_index": _trace_value(trace, "step_index", 0),
                                "action_type": (
                                    _trace_value(trace, "action_type", "")
                                    .value
                                    if hasattr(_trace_value(trace, "action_type", ""), "value")
                                    else str(_trace_value(trace, "action_type", ""))
                                ),
                                "target": _trace_value(trace, "target_resource", ""),
                                "thought": _trace_value(trace, "thought", ""),
                                "observation": str(
                                    _trace_value(trace, "actual_observation", "")
                                    or _trace_value(trace, "observation", "")
                                )[:500],
                                "status": str(_trace_value(trace, "status", "")),
                                "duration_seconds": _trace_value(trace, "duration_seconds", 0),
                                "exit_code": _trace_value(trace, "exit_code", None),
                            },
                    })

            # Forward accumulated discoveries so SubAgents aren't context-starved
            sub_goal = sub_mission.goal
            if self._accumulated_context:
                valid_discoveries = []
                for item in self._accumulated_context:
                    clean = item.strip()
                    if not clean:
                        continue
                    # Exclude raw strings that are just IP addresses (often from diagnostic commands)
                    if re.match(r"^(?:https?://)?(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?(?:/.*)?$", clean):
                        continue
                    # Exclude local diagnostic commands/outputs
                    if any(diag in clean.lower() for diag in (
                        "ifconfig.me", "icanhazip", "whoami", "uname", "pwd", "hostname", "ip addr", "ip a", "ifconfig", "route"
                    )):
                        continue
                    valid_discoveries.append(clean)

                if valid_discoveries:
                    recent_ctx = "; ".join(valid_discoveries[-3:])
                    sub_goal = f"{sub_mission.goal} [Prior Discoveries: {recent_ctx}]"

            sub_timeout = max(60.0, float(sub_mission.max_steps) * 60.0)
            try:
                traces = await asyncio.wait_for(
                    agent.run_mission(
                        workspace_id=workspace_id,
                        goal=sub_goal,
                        steps=sub_mission.max_steps,
                        step_callback=_sub_step_callback,
                    ),
                    timeout=sub_timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("sub_agent_timed_out", sub_id=sub_mission.id, agent_num=sub_agent_num)
                traces = getattr(agent, "history", [])

            duration = round(time.perf_counter() - t_start, 2)

            # Summarize findings from traces (prefer agent's own self-summary)
            raw_summary = getattr(agent, "mission_summary", "")
            if isinstance(raw_summary, str) and raw_summary.strip():
                findings_summary = raw_summary
            else:
                findings_summary = await self._summarize_sub_agent_traces(
                    sub_mission.goal, traces
                )

            # Extract key discoveries
            key_discoveries = self._extract_key_discoveries(traces)
            if key_discoveries:
                self._accumulated_context.extend(key_discoveries)
            if findings_summary and len(findings_summary.strip()) > 10:
                self._accumulated_context.append(findings_summary[:180])

            succeeded = sum(
                1 for t in traces
                if str(_trace_value(t, "status", "")) in ("COMPLETED", "SUCCESS", "VERIFIED")
            )
            total = len(traces)

            has_goal_complete = any(
                _trace_value(t, "expected_observation", "") == "GOAL_COMPLETE"
                or _trace_value(t, "actual_observation", "") == "GOAL_COMPLETE"
                or "goal-complete" in str(_trace_value(t, "target_resource", "")).lower()
                for t in traces
            )
            last_trace = traces[-1] if traces else None
            last_succeeded = last_trace and str(_trace_value(last_trace, "status", "")) in (
                "COMPLETED",
                "SUCCESS",
                "VERIFIED",
            )
            success_ratio = (succeeded / total) if total > 0 else 0.0

            is_successful = has_goal_complete or (last_succeeded and success_ratio >= 0.5) or (succeeded > 0 and total == 1)

            return SubMissionResult(
                sub_mission_id=sub_mission.id,
                goal=sub_mission.goal,
                traces=traces,
                findings_summary=findings_summary,
                success=is_successful,
                key_discoveries=key_discoveries,
                actions_taken=total,
                duration_seconds=duration,
            )

        except Exception as e:
            logger.warning(
                "boss_sub_agent_dispatch_failed",
                sub_id=sub_mission.id,
                goal=sub_mission.goal[:100],
                error=str(e),
            )
            return SubMissionResult(
                sub_mission_id=sub_mission.id,
                goal=sub_mission.goal,
                findings_summary=f"SubAgent execution failed: {e}",
                success=False,
                duration_seconds=round(time.perf_counter() - t_start, 2),
            )

    async def _summarize_sub_agent_traces(
        self, goal: str, traces: list[Any]
    ) -> str:
        """Use LLM to summarize what a SubAgent found from its traces."""
        if not traces:
            return "No actions executed."

        observations = "\n".join(
            f"- {(
                _trace_value(t, 'action_type', '').value
                if hasattr(_trace_value(t, 'action_type', ''), 'value')
                else _trace_value(t, 'action_type', '')
            )} "
            f"on {_trace_value(t, 'target_resource', '')}: "
            f"{str(_trace_value(t, 'actual_observation', '') or _trace_value(t, 'observation', ''))[:1500]}"
            for t in traces
            if _trace_value(t, "actual_observation", "") or _trace_value(t, "observation", "")
        )

        if not observations:
            return "SubAgent executed but produced no observations."

        try:
            from sonic.llm.schemas import LLMRequest, Message, MessageRole

            req = LLMRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content="You are an autonomous intelligence officer. Summarize the worker agent's findings accurately and concisely. Focus on concrete facts: open ports, HTTP status codes, server banners, URLs/paths discovered, configuration details, credentials, flags, or error causes."),
                    Message(role=MessageRole.USER, content=f"Worker goal: {goal}\n\nActions and observations:\n{observations}\n\nSummarize the key findings in 2-4 sentences."),
                ],
                task_type="reasoning",
                max_tokens=500,
                temperature=0.2,
            )
            resp = await self.llm_router.complete(req)
            return (resp.content or "").strip() or observations[:1000]
        except Exception:
            # Fallback: return raw observations
            return observations[:1000]

    def _extract_key_discoveries(self, traces: list[Any]) -> list[str]:
        """Extract key facts and security discoveries from SubAgent traces."""
        discoveries = []
        diag_patterns = (
            "ifconfig.me",
            "icanhazip",
            "whoami",
            "uname",
            "pwd",
            "hostname",
            "ip addr",
            "ip a",
            "ifconfig",
            "route",
        )
        for t in traces:
            # Check for local diagnostic / environment / identity commands
            target = getattr(t, "target_resource", None) or getattr(t, "target", "") or ""
            payload = getattr(t, "payload", "") or ""
            if isinstance(t, dict):
                target = t.get("target_resource") or t.get("target") or target
                payload = t.get("payload") or payload

            cmd_text = f"{target} {payload}".strip().lower()
            is_diag = False
            for diag in diag_patterns:
                if diag in ("ifconfig.me", "icanhazip"):
                    if diag in cmd_text:
                        is_diag = True
                        break
                elif diag in ("ip addr", "ip a"):
                    if re.search(r"\bip\s+(addr|a)\b", cmd_text) or diag in cmd_text:
                        is_diag = True
                        break
                else:
                    if re.search(rf"\b{re.escape(diag)}\b", cmd_text):
                        is_diag = True
                        break

            if is_diag:
                continue

            if isinstance(t, dict):
                obs = (t.get("actual_observation") or t.get("observation") or "").strip()
                status_str = str(t.get("status", ""))
            else:
                obs = (getattr(t, "actual_observation", None) or getattr(t, "observation", "") or "").strip()
                status_str = str(getattr(t, "status", ""))

            if not obs or len(obs) < 5:
                continue
            if status_str not in ("COMPLETED", "SUCCESS", "VERIFIED"):
                continue

            # 1. Search for high-value security entities: open ports
            port_matches = re.findall(r'\b(\d{1,5}/(?:tcp|udp)\s+open\s+[^\r\n]+)', obs, re.IGNORECASE)
            for pm in port_matches:
                clean_pm = f"Open port: {pm.strip()}"
                if clean_pm not in discoveries:
                    discoveries.append(clean_pm)

            # 2. Search for flags, keys, tokens
            flag_matches = re.findall(r'(?:flag|secret|key|token)[\s:=]+([^\s\r\n]{6,})', obs, re.IGNORECASE)
            for fm in flag_matches:
                clean_fm = f"Discovered value: {fm.strip(' .,;:\"\'')}"
                if clean_fm not in discoveries:
                    discoveries.append(clean_fm)

            # 3. Search for HTTP status and server headers
            http_matches = re.findall(r'\b(HTTP/[12](?:\.[01])?\s+\d{3}\s+[^\r\n]+)', obs, re.IGNORECASE)
            for hm in http_matches:
                clean_hm = hm.strip()
                if clean_hm not in discoveries:
                    discoveries.append(clean_hm)

            # 4. Fallback line extraction with banner filtering
            for line in obs.splitlines():
                line_str = line.strip()
                if not line_str or len(line_str) < 10:
                    continue
                lower_line = line_str.lower()
                # Skip tool noise and startup banners
                if any(noise in lower_line for noise in (
                    "starting nmap", "nmap scan report", "reading package lists",
                    "building dependency tree", "need to get", "after this operation",
                    "=== test session", "platform win32", "rootdir:", "plugins:",
                    "collected ", "total duration", "exit 0", "exit 127",
                    "curl -", "ping -", "ssh ", "nc -", "warning:",
                )):
                    continue
                # Skip if line is a bare IP address
                if re.match(r"^(?:https?://)?(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?(?:/.*)?$", line_str):
                    continue
                if line_str not in discoveries:
                    discoveries.append(line_str[:200])
                    break

        return discoveries[:10]  # Cap at 10

    # ------------------------------------------------------------------
    # Findings Aggregation
    # ------------------------------------------------------------------

    async def _aggregate_findings(self, phase: Phase, objective: str) -> str:
        """Synthesize all SubAgent outputs from a phase into unified findings."""
        t_start = time.perf_counter()

        summaries = "\n\n".join(
            f"SubAgent ({r.goal}):\n{r.findings_summary}"
            for r in phase.results
            if r.findings_summary
        )

        if not summaries:
            return "No findings from this phase."

        try:
            from sonic.llm.schemas import LLMRequest, Message, MessageRole

            req = LLMRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content="You are a Boss Agent analyzing reports from your worker agents. Synthesize their findings into a unified intelligence picture."),
                    Message(role=MessageRole.USER, content=f"Objective: {objective}\n\nPhase {phase.phase_number} ({phase.name}) reports:\n{summaries}\n\nSynthesize these findings into a clear, unified analysis. What do we know now? What are the key takeaways?"),
                ],
                task_type="reasoning",
                max_tokens=500,
                temperature=0.2,
            )
            resp = await self.llm_router.complete(req)
            content = (resp.content or "").strip()
        except Exception:
            content = summaries

        duration = round(time.perf_counter() - t_start, 2)
        phase.summary = content
        self.thinking_log.append(BossThinking(
            phase=phase.phase_number,
            thinking_type="findings_analysis",
            content=content,
            duration_seconds=duration,
        ))

        return content

    # ------------------------------------------------------------------
    # Objective Completion Check
    # ------------------------------------------------------------------

    async def _check_objective_complete(
        self, objective: str, all_findings: str
    ) -> tuple[bool, str]:
        """Ask the LLM whether the objective has been fully satisfied."""
        t_start = time.perf_counter()

        try:
            from sonic.llm.schemas import LLMRequest, Message, MessageRole

            req = LLMRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content="You are a completion checker. Determine if the user's objective has been fully satisfied based on the findings. Respond with ONLY valid JSON."),
                    Message(role=MessageRole.USER, content=f"Objective: {objective}\n\nAll findings so far:\n{all_findings[:2000]}\n\nHas the objective been fully accomplished?\nRespond: {{\"complete\": true/false, \"reason\": \"explanation\"}}"),
                ],
                task_type="reasoning",
                max_tokens=200,
                temperature=0.1,
            )
            resp = await self.llm_router.complete(req)
            raw = (resp.content or "").strip()
        except Exception as e:
            logger.warning("boss_completion_check_failed", error=str(e))
            return False, f"Completion check failed: {e}"

        duration = round(time.perf_counter() - t_start, 2)

        parsed = self._parse_json_response(raw)
        is_complete = parsed.get("complete", False) if parsed else False
        reason = parsed.get("reason", raw[:200]) if parsed else raw[:200]

        self.thinking_log.append(BossThinking(
            phase=len(self.phases),
            thinking_type="completion_check",
            content=f"Complete: {is_complete}. {reason}",
            duration_seconds=duration,
        ))

        return is_complete, reason

    # ------------------------------------------------------------------
    # Next Phase Planning (Reaction)
    # ------------------------------------------------------------------

    async def _plan_next_phase(
        self, objective: str, all_findings: str, phases: list[Phase]
    ) -> Phase | None:
        """Based on findings so far, plan the next phase of sub-missions."""
        t_start = time.perf_counter()
        phase_number = len(phases) + 1

        phase_history = "\n".join(
            f"Phase {p.phase_number} ({p.name}): {len(p.results)} workers, "
            f"{sum(1 for r in p.results if r.success)} succeeded"
            for p in phases
        )

        try:
            from sonic.llm.schemas import LLMRequest, Message, MessageRole

            prompt = f"""You are a Boss Agent planning the next phase of work.

OBJECTIVE: {objective}

PREVIOUS PHASES:
{phase_history}

FINDINGS SO FAR:
{all_findings[:2000]}

Based on these findings, what should the NEXT phase focus on? Create focused sub-tasks for worker agents.

Respond with EXACTLY this JSON format:
{{
  "thinking": "Your strategic analysis of what's needed next based on findings",
  "phase_name": "Short name for this phase",
  "sub_missions": [
    {{
      "goal": "Specific goal for this worker",
      "max_steps": 4,
      "priority": 1
    }}
  ]
}}

If the objective is complete or no more work is needed, return:
{{"thinking": "Objective appears complete", "phase_name": "", "sub_missions": []}}"""

            req = LLMRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content="You are an expert task planning agent. Output ONLY valid JSON."),
                    Message(role=MessageRole.USER, content=prompt),
                ],
                task_type="planning",
                max_tokens=800,
                temperature=0.3,
            )
            resp = await self.llm_router.complete(req)
            raw = (resp.content or "").strip()
        except Exception as e:
            logger.warning("boss_plan_next_phase_failed", error=str(e))
            return None

        duration = round(time.perf_counter() - t_start, 2)

        parsed = self._parse_json_response(raw)
        if not parsed:
            return None

        thinking = parsed.get("thinking", "")
        phase_name = parsed.get("phase_name", f"Phase {phase_number}")
        sub_missions_raw = parsed.get("sub_missions", [])

        if not sub_missions_raw:
            return None

        sub_missions = []
        for sm in sub_missions_raw[:5]:
            goal = str(sm.get("goal", "")).strip()
            if not goal:
                continue
            try:
                requested_steps = int(sm.get("max_steps", self.sub_agent_steps))
            except (TypeError, ValueError):
                requested_steps = self.sub_agent_steps
            try:
                priority = max(0, int(sm.get("priority", 1) or 1))
            except (TypeError, ValueError):
                priority = 1
            sub_missions.append(SubMission(
                goal=goal,
                max_steps=max(1, min(requested_steps, 8)),
                priority=priority,
            ))

        self.thinking_log.append(BossThinking(
            phase=phase_number,
            thinking_type="reaction_planning",
            content=thinking,
            duration_seconds=duration,
        ))

        return Phase(
            phase_number=phase_number,
            name=phase_name,
            thinking=thinking,
            sub_missions=sub_missions,
        )

    # ------------------------------------------------------------------
    # Final Report Synthesis
    # ------------------------------------------------------------------

    async def _synthesize_final_report(
        self, objective: str, t_start: float
    ) -> BossReport:
        """Generate the final comprehensive report."""
        total_actions = sum(len(r.traces) for p in self.phases for r in p.results)
        all_findings = self._collect_all_findings()

        # LLM synthesis of final summary
        final_summary = ""
        try:
            from sonic.llm.schemas import LLMRequest, Message, MessageRole

            req = LLMRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content="You are a Boss Agent creating a final report. Summarize all findings clearly and comprehensively."),
                    Message(role=MessageRole.USER, content=f"Objective: {objective}\n\nAll findings:\n{all_findings[:3000]}\n\nCreate a clear, structured final summary answering the user's objective."),
                ],
                task_type="reasoning",
                max_tokens=600,
                temperature=0.2,
            )
            resp = await self.llm_router.complete(req)
            final_summary = (resp.content or "").strip()
        except Exception:
            final_summary = all_findings[:1000]

        self.thinking_log.append(BossThinking(
            phase=len(self.phases),
            thinking_type="final_synthesis",
            content=final_summary,
            duration_seconds=0.0,
        ))

        # Determine status
        any_success = any(
            r.success for p in self.phases for r in p.results
        )
        all_success = all(
            r.success for p in self.phases for r in p.results
        ) if self.phases and any(p.results for p in self.phases) else False

        if all_success:
            status = "COMPLETE"
        elif any_success:
            status = "PARTIAL"
        else:
            status = "INCOMPLETE"

        return BossReport(
            objective=objective,
            status=status,
            phases=self.phases,
            thinking_log=self.thinking_log,
            all_traces=self.all_traces,
            total_sub_agents=self._sub_agent_count,
            total_actions=total_actions,
            total_phases=len(self.phases),
            findings_summary=final_summary,
            duration_seconds=round(time.perf_counter() - t_start, 2),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _collect_all_findings(self) -> str:
        """Collect all SubAgent findings across all phases."""
        findings = []
        for phase in self.phases:
            if getattr(phase, "summary", ""):
                findings.append(
                    f"[Phase {phase.phase_number} ({phase.name}) Unified Intelligence]:\n"
                    f"{phase.summary}"
                )
            else:
                for result in phase.results:
                    if result.findings_summary:
                        findings.append(
                            f"[Phase {phase.phase_number} / {result.goal}]:\n"
                            f"{result.findings_summary}"
                        )
        return "\n\n".join(findings) if findings else "No findings yet."

    @staticmethod
    def _parse_json_response(raw: str) -> dict | None:
        """Extract and parse JSON from LLM response text."""
        if not raw:
            return None

        # Try direct parse
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        code_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw, re.DOTALL)
        if code_match:
            try:
                return json.loads(code_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding first { ... } block
        brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def _now() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    async def _emit(
        callback: Optional[Callable], event_type: str, data: dict
    ) -> None:
        """Emit an event to the phase callback."""
        if callback is None:
            return
        try:
            import asyncio
            result = callback(event_type, data)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.debug("boss_emit_callback_failed", event=event_type, error=str(e))
