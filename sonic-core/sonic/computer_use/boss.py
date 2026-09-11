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

import json
import re
import time
from typing import Any, Callable, Optional

import structlog

from sonic.computer_use.models_boss import (
    BossReport,
    BossThinking,
    Phase,
    SubMission,
    SubMissionResult,
)

logger = structlog.get_logger(__name__)


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
    ):
        self.computer = computer_provider
        self.llm_router = llm_router
        self.safety = safety
        self.security_tools = security_tools or {}
        self.tenant_id = tenant_id
        self.max_phases = max_phases
        self.sub_agent_steps = sub_agent_steps

        # State
        self.phases: list[Phase] = []
        self.thinking_log: list[BossThinking] = []
        self.all_traces: list[Any] = []
        self._sub_agent_count: int = 0
        self._interrupted: bool = False

    def interrupt(self) -> None:
        """Signal the Boss to stop orchestration."""
        self._interrupted = True

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

        # Phase 1: Strategic decomposition
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

            # Dispatch each SubAgent sequentially
            for sub_mission in sorted(current_phase.sub_missions, key=lambda s: -s.priority):
                if self._interrupted or (callable(interrupt_check) and interrupt_check()):
                    break

                # Check dependencies
                if sub_mission.depends_on:
                    deps_met = all(
                        any(r.sub_mission_id == dep_id and r.success for r in current_phase.results)
                        for dep_id in sub_mission.depends_on
                    )
                    if not deps_met:
                        logger.info("boss_sub_mission_deps_not_met", sub_id=sub_mission.id)
                        continue

                sub_mission.status = "RUNNING"
                self._sub_agent_count += 1

                await self._emit(phase_callback, "sub_dispatch", {
                    "sub_mission_id": sub_mission.id,
                    "goal": sub_mission.goal,
                    "max_steps": sub_mission.max_steps,
                    "sub_agent_number": self._sub_agent_count,
                })

                result = await self._dispatch_sub_agent(
                    workspace_id, sub_mission, phase_callback
                )
                current_phase.results.append(result)
                self.all_traces.extend(result.traces)

                sub_mission.status = "COMPLETED" if result.success else "FAILED"

                await self._emit(phase_callback, "sub_report", {
                    "sub_mission_id": sub_mission.id,
                    "goal": sub_mission.goal,
                    "success": result.success,
                    "findings_summary": result.findings_summary,
                    "key_discoveries": result.key_discoveries,
                    "actions_taken": result.actions_taken,
                    "duration_seconds": result.duration_seconds,
                })

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

        prompt = f"""You are a Boss Agent orchestrator. Your job is to analyze the user's objective and break it into focused, independent sub-tasks that can be assigned to separate worker agents.

USER OBJECTIVE: {objective}

Analyze this objective deeply. Think about:
1. What information do you need first? (reconnaissance / discovery)
2. What are the independent sub-tasks that can be done?
3. What is the logical order? (what depends on what?)
4. How many workers do you need? (2-5 workers per phase, no more)

Respond with EXACTLY this JSON format (no extra text):
{{
  "thinking": "Your strategic analysis of the objective - what needs to be done and why",
  "phase_name": "Short name for this phase (e.g., Reconnaissance, Testing, Analysis)",
  "sub_missions": [
    {{
      "goal": "Clear, focused goal for this worker agent. Be specific about what to do and what to report back.",
      "max_steps": 3,
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
        for sm in sub_missions_raw[:5]:  # Cap at 5 sub-missions per phase
            sub_missions.append(SubMission(
                goal=sm.get("goal", ""),
                max_steps=min(sm.get("max_steps", self.sub_agent_steps), 8),
                priority=sm.get("priority", 1),
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
        """Heuristic fallback when LLM decomposition fails."""
        return Phase(
            phase_number=1,
            name="Direct Execution",
            thinking=f"LLM decomposition unavailable. Executing objective directly: {objective}",
            sub_missions=[
                SubMission(
                    goal=objective,
                    max_steps=self.sub_agent_steps,
                    priority=1,
                ),
            ],
        )

    # ------------------------------------------------------------------
    # SubAgent Dispatch
    # ------------------------------------------------------------------

    async def _dispatch_sub_agent(
        self,
        workspace_id: str,
        sub_mission: SubMission,
        phase_callback: Optional[Callable] = None,
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

            agent = ComputerUseAgent(
                computer_provider=self.computer,
                autonomy_level=ComputerAutonomyLevel.L3_AUTONOMOUS,
                mode=EngineeringMissionMode.GENERAL_ENGINEERING_MODE,
                max_actions=sub_mission.max_steps,
                llm_router=self.llm_router,
                security_tools=self.security_tools,
                safety=self.safety,
                self_host=True if self.safety else False,
                tenant_id=self.tenant_id,
                agent_id=f"sub-agent-{self._sub_agent_count}",
                enable_llm_decomposition=False,
            )

            # Step callback to stream SubAgent actions to UI
            async def _sub_step_callback(trace):
                if phase_callback:
                    await self._emit(phase_callback, "sub_step", {
                        "sub_mission_id": sub_mission.id,
                        "sub_agent_number": self._sub_agent_count,
                        "trace": {
                            "step_index": trace.step_index,
                            "action_type": trace.action_type.value if hasattr(trace.action_type, "value") else str(trace.action_type),
                            "target": trace.target_resource,
                            "thought": getattr(trace, "thought", ""),
                            "observation": (trace.actual_observation or "")[:500],
                            "status": str(trace.status),
                            "duration_seconds": getattr(trace, "duration_seconds", 0),
                            "exit_code": getattr(trace, "exit_code", None),
                        },
                    })

            traces = await agent.run_mission(
                workspace_id=workspace_id,
                goal=sub_mission.goal,
                steps=sub_mission.max_steps,
                step_callback=_sub_step_callback,
            )

            duration = round(time.perf_counter() - t_start, 2)

            # Summarize findings from traces
            findings_summary = await self._summarize_sub_agent_traces(
                sub_mission.goal, traces
            )

            # Extract key discoveries
            key_discoveries = self._extract_key_discoveries(traces)

            succeeded = sum(
                1 for t in traces
                if str(t.status) in ("COMPLETED", "SUCCESS", "VERIFIED")
            )
            total = len(traces)

            return SubMissionResult(
                sub_mission_id=sub_mission.id,
                goal=sub_mission.goal,
                traces=traces,
                findings_summary=findings_summary,
                success=succeeded > 0,
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
            f"- {t.action_type.value if hasattr(t.action_type, 'value') else t.action_type} "
            f"on {t.target_resource}: {(t.actual_observation or '')[:300]}"
            for t in traces
            if t.actual_observation
        )

        if not observations:
            return "SubAgent executed but produced no observations."

        try:
            from sonic.llm.schemas import LLMRequest, Message, MessageRole

            req = LLMRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content="Summarize the worker agent's findings concisely. Focus on key facts discovered."),
                    Message(role=MessageRole.USER, content=f"Worker goal: {goal}\n\nActions and observations:\n{observations}\n\nSummarize the key findings in 2-4 sentences."),
                ],
                task_type="reasoning",
                max_tokens=300,
                temperature=0.2,
            )
            resp = await self.llm_router.complete(req)
            return (resp.content or "").strip() or observations[:500]
        except Exception:
            # Fallback: return raw observations
            return observations[:500]

    def _extract_key_discoveries(self, traces: list[Any]) -> list[str]:
        """Extract key facts/discoveries from SubAgent traces."""
        discoveries = []
        for t in traces:
            obs = (t.actual_observation or "").strip()
            if not obs or len(obs) < 10:
                continue
            status_str = str(t.status)
            if status_str not in ("COMPLETED", "SUCCESS", "VERIFIED"):
                continue
            # Take the first meaningful line of each successful observation
            first_line = obs.split("\n")[0][:200]
            if first_line and first_line not in discoveries:
                discoveries.append(first_line)
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
            sub_missions.append(SubMission(
                goal=sm.get("goal", ""),
                max_steps=min(sm.get("max_steps", self.sub_agent_steps), 8),
                priority=sm.get("priority", 1),
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

