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

import json
from sonic.logger import get_logger
from sonic.agents.base import BaseAgent
from sonic.llm.schemas import LLMResponse, Message, MessageRole
from sonic.memory.schemas import (
    AgentNode,
    EngagementNode,
    EngagementStatus,
)

logger = get_logger(__name__)


class MetaOrchestrator(BaseAgent):
    """
    Top-level orchestrator that plans and coordinates all other agents.
    
    Workflow:
        1. Analyze target scope
        2. Create engagement plan (which agents, what order, priorities)
        3. Dispatch tasks to specialist agents
        4. Monitor progress and adapt strategy
        5. Compile final report
    """

    def __init__(self, **kwargs: Any):
        super().__init__(name="MetaOrchestrator", **kwargs)
        self.engagement_plan: dict[str, Any] = {}
        self.phase = "planning"  # planning, recon, analysis, exploitation, verification, reporting

    def get_system_prompt(self) -> str:
        return """You are the Meta Orchestrator of SONIC — an Autonomous Self-Evolving Penetration Architect (A-SEA).

Your role is to:
1. PLAN: Analyze the target scope and create a comprehensive engagement plan
2. DECOMPOSE: Break the plan into specific tasks for specialist agents
3. COORDINATE: Manage the flow of information between agents
4. ADAPT: Adjust strategy based on findings from agents
5. REPORT: Compile all validated findings into a coherent report

You have access to these specialist agents:
- ReconAgent: Surface mapping, subdomain enumeration, tech detection
- StaticReasoningAgent: Code/config analysis, pattern matching, dataflow
- DynamicExecutionAgent: Live HTTP testing, fuzzing, in-sandbox probing
- HypothesisGenerator: Creative vulnerability ideation based on recon data
- VerifierAgent: Evidence validation, false positive filtering, confidence scoring
- Toolsmith (being-authored tools): NEW custom tools the being authors for gaps
- MethodLab (self-invented techniques): NOVEL attack methods synthesized from
  observation + failure + the known-technique ledger, confirmed only on real
  in-sandbox reproduction

Rules:
- Always prioritize based on potential impact (Critical > High > Medium > Low)
- Never skip verification — every finding MUST have evidence
- Adapt your plan if new attack surface is discovered
- Track coverage to ensure thorough testing
- When no existing tool fits a gap, route to Toolsmith/MethodLab instead of
  forcing a known-scanner that does not apply

Respond with structured JSON for plans and task assignments."""

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute the orchestration workflow."""
        self.status = "running"
        target = task.get("target", "")
        scope = task.get("scope", {})
        engagement_id = task.get("engagement_id", "")

        logger.info("orchestrator_starting", target=target, engagement_id=engagement_id)

        # Phase 1: Create engagement plan
        self.phase = "planning"
        plan = await self._create_plan(target, scope)

        # Phase 2: Execute plan phases
        results = {
            "engagement_id": engagement_id,
            "target": target,
            "plan": plan,
            "phases_completed": [],
            "findings_summary": [],
        }

        self.status = "completed"
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
                "estimated_phases": 4,
                "phases": [
                    {"name": "Recon", "agent": "recon", "tasks": ["subdomain_enum", "tech_detect", "port_scan"], "priority": "high"},
                    {"name": "Static Analysis", "agent": "static", "tasks": ["code_review", "config_analysis"], "priority": "high"},
                    {"name": "Dynamic Testing", "agent": "dynamic", "tasks": ["fuzz_endpoints", "auth_testing"], "priority": "high"},
                    {"name": "Verification", "agent": "verifier", "tasks": ["validate_findings", "score_confidence"], "priority": "critical"},
                ],
                "priority_vuln_classes": ["XSS", "SQLi", "IDOR", "SSRF", "Auth Bypass"],
                "estimated_time_minutes": 30,
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
        except Exception:
            return {"action": "continue", "reason": "Unable to parse evaluation, continuing"}
