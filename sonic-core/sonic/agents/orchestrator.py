"""
SONIC-REDA — Meta Orchestrator Agent
========================================
The brain of the multi-agent system. Responsible for:
    - High-level engagement planning
    - Task decomposition into sub-tasks for specialist agents
    - Agent coordination and sequencing
    - Strategy adaptation based on findings
    - Final report compilation
"""

from __future__ import annotations

import inspect
import json
import uuid
from typing import Any

from sonic.agents.base import BaseAgent
from sonic.agents.task_graph import TaskGraph, TaskNode, TaskPriority
from sonic.llm.prompts import ORCHESTRATOR_SYSTEM
from sonic.logger import get_logger

logger = get_logger(__name__)


class MetaOrchestrator(BaseAgent):
    """
    Top-level orchestrator that plans and coordinates all other agents.

    Workflow:
        1. Analyze target scope
        2. Create engagement plan (which agents, what order, priorities)
        3. Dispatch tasks to specialist agents via TaskGraph / Director
        4. Monitor progress and adapt strategy
        5. Compile final report
    """

    def __init__(self, director: Any = None, tenant_id: str = "", **kwargs: Any):
        super().__init__(name="MetaOrchestrator", **kwargs)
        self.engagement_plan: dict[str, Any] = {}
        self.phase = "planning"  # planning, recon, analysis, exploitation, verification, reporting
        self.director = director
        self.tenant_id = tenant_id

    def get_system_prompt(self) -> str:
        return ORCHESTRATOR_SYSTEM

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute the orchestration workflow."""
        self.status = "running"
        target = task.get("target", "")
        scope = task.get("scope", {})
        engagement_id = task.get("engagement_id", "") or f"eng-{uuid.uuid4().hex[:12]}"
        tenant_id = task.get("tenant_id", "") or getattr(self, "tenant_id", "") or "default"
        worker_fn = task.get("worker_fn", None)

        logger.info("orchestrator_starting", target=target, engagement_id=engagement_id)

        # Phase 1: Create engagement plan
        self.phase = "planning"
        plan = await self._create_plan(target, scope)

        # Phase 2: Execute plan phases via Director or TaskGraph
        all_findings: list[dict[str, Any]] = []
        phases = plan.get("phases", [])
        phases_completed: list[str] = []
        loop_res: dict[str, Any] = {}

        if self.director is not None:
            # Wire execution through Director
            eid = await self.director.start_engagement(
                target=target,
                scope=scope,
                tenant_id=tenant_id,
            )
            if worker_fn is not None:
                loop_res = await self.director.run_engagement_loop(
                    eid,
                    worker_fn=worker_fn,
                )
                all_findings.extend(loop_res.get("findings", []))
            phases_completed = (
                [p.get("name", "") for p in phases if p.get("name")]
                if loop_res.get("graph_complete") and not loop_res.get("failed")
                else []
            )
        else:
            # Build and execute via TaskGraph DAG
            graph = TaskGraph(engagement_id=engagement_id, tenant_id=tenant_id)
            prev_phase_task_ids: list[str] = []

            for idx, p in enumerate(phases):
                p_name = p.get("name", f"Phase-{idx}")
                agent_type = p.get("agent", "recon")
                cur_phase_task_ids = []
                for task_name in p.get("tasks", []):
                    tn = TaskNode(
                        name=f"{p_name}: {task_name}",
                        agent_type=agent_type,
                        task_payload={"target": target, "task": task_name, "scope": scope},
                        depends_on=list(prev_phase_task_ids),
                        priority=TaskPriority(p.get("priority", "medium")),
                        engagement_id=graph.engagement_id,
                        tenant_id=graph.tenant_id,
                    )
                    tid = graph.add_task(tn)
                    cur_phase_task_ids.append(tid)
                prev_phase_task_ids = cur_phase_task_ids

            if worker_fn is not None:
                while not graph.is_complete():
                    ready = graph.get_ready_tasks()
                    if not ready:
                        break
                    for r_task in ready:
                        graph.mark_running(r_task.id)
                        try:
                            task_dict = r_task.model_dump() if hasattr(r_task, "model_dump") else {"name": r_task.name, "task_id": r_task.id, "payload": r_task.task_payload}
                            res = worker_fn(task_dict)
                            if inspect.isawaitable(res):
                                res = await res
                            worker_status = str(res.get("status", "")).lower() if isinstance(res, dict) else ""
                            if worker_status not in {"success", "succeeded", "completed", "verified", "recovered"}:
                                graph.mark_failed(r_task.id, "Worker did not report explicit successful execution")
                                continue
                            graph.mark_completed(r_task.id, res)
                            if isinstance(res, dict) and "findings" in res and isinstance(res["findings"], list):
                                all_findings.extend(res["findings"])
                        except Exception as exc:
                            logger.warning("orchestrator_worker_failed", task_id=r_task.id, error=str(exc))
                            graph.mark_failed(r_task.id, str(exc))

            phases_completed = self._completed_phase_names(graph, phases)

        # Evaluate findings if any were generated
        eval_decision: dict[str, Any] = {}
        if all_findings:
            eval_decision = await self.evaluate_findings(all_findings)

        results = {
            "engagement_id": engagement_id,
            "target": target,
            "plan": plan,
            "phases_completed": phases_completed,
            "findings_summary": all_findings,
            "evaluation": eval_decision,
        }

        executed = bool(worker_fn)
        self.status = "completed" if executed and phases_completed else ("planned" if not executed else "incomplete")
        return results

    async def _create_plan(self, target: str, scope: dict) -> dict[str, Any]:
        """Create an engagement plan using LLM reasoning."""
        scope_summary = json.dumps(scope, indent=2) if scope else "No specific scope provided"

        prompt = f"""Analyze this target and create a detailed engagement plan.

TARGET: {target}
SCOPE: {scope_summary}

Create a phased plan with:
1. Recon phase tasks (what to discover)
2. Analysis phase tasks (what to analyze)
3. Testing phase tasks (what to test actively)
4. Verification priorities

Return as JSON with this structure:
{{
    "target_summary": "brief description",
    "estimated_phases": 4,
    "phases": [
        {{
            "name": "phase name",
            "agent": "agent_type",
            "tasks": ["task1", "task2"],
            "priority": "high/medium/low"
        }}
    ],
    "priority_vuln_classes": ["XSS", "SQLi", ...],
    "estimated_time_minutes": 30
}}"""

        response = await self.think(prompt, task_type="planning")

        # Try to parse JSON from response
        try:
            # Extract JSON from response content
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            plan = json.loads(content)
        except (json.JSONDecodeError, IndexError):
            plan = {
                "target_summary": target,
                "estimated_phases": 1,
                "phases": [{
                    "name": "Target triage",
                    "agent": "recon",
                    "tasks": ["classify target modality and identify the next evidence-producing observation"],
                    "priority": "high",
                }],
                "priority_vuln_classes": [],
                "estimated_time_minutes": 5,
                "planning_status": "fallback_triage_only",
            }

        self.engagement_plan = plan
        self._log_action("plan_created", {"plan": plan})
        return plan

    async def create_agent_tasks(self, plan: dict[str, Any], engagement_id: str) -> list[dict]:
        """Break the plan into specific agent task assignments."""
        tasks = []
        for phase in plan.get("phases", []):
            for task_name in phase.get("tasks", []):
                tasks.append({
                    "agent_type": phase["agent"],
                    "task": task_name,
                    "priority": phase.get("priority", "medium"),
                    "engagement_id": engagement_id,
                    "phase": phase["name"],
                })
        return tasks

    @staticmethod
    def _completed_phase_names(graph: TaskGraph, phases: list[dict[str, Any]]) -> list[str]:
        """Report phases only when every phase task actually succeeded."""
        completed: list[str] = []
        for phase in phases:
            name = phase.get("name", "")
            tasks = [task for task in graph.tasks.values() if task.name.startswith(f"{name}: ")]
            if tasks and all(task.status.value == "succeeded" for task in tasks):
                completed.append(name)
        return completed
    async def evaluate_findings(self, findings: list[dict]) -> dict[str, Any]:
        """Evaluate all findings and decide next steps."""
        if not findings:
            return {"action": "continue", "reason": "No findings yet"}

        findings_summary = json.dumps(findings[:10], indent=2)  # Top 10
        prompt = f"""Evaluate these findings from the current engagement:

{findings_summary}

Based on these findings:
1. Should we continue testing? Or is the engagement complete?
2. Are there new attack vectors revealed by these findings?
3. What should be the next priority?

Return JSON: {{"action": "continue|complete|pivot", "reason": "...", "next_priorities": [...]}}"""

        response = await self.think(prompt, task_type="planning")
        try:
            content = response.content
            if "```" in content:
                content = content.split("```json")[1].split("```")[0] if "```json" in content else content.split("```")[1].split("```")[0]
            return json.loads(content)
        except Exception as e:
            logger.error("orchestrator_eval_parse_failed", error=str(e))
            return {"action": "continue", "reason": f"Unable to parse evaluation ({str(e)[:100]}), continuing"}
