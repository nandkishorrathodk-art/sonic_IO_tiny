"""
SONIC-REDA — Engagement Manager
===================================
Manages the full lifecycle of a security engagement.
Coordinates agents, manages state, and produces reports.

Lifecycle:
    1. CREATE: Initialize engagement with target + scope
    2. RECON: Run Recon Agent → discover attack surface
    3. HYPOTHESIZE: Run Hypothesis Generator → creative ideation
    4. ANALYZE: Run Static Reasoning → code/config analysis
    5. TEST: Run Dynamic Execution → active testing
    6. VERIFY: Run Verifier → validate findings
    7. REPORT: Compile results → generate report
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from sonic.logger import get_logger

logger = get_logger(__name__)

from sonic.agents.orchestrator import MetaOrchestrator
from sonic.agents.recon import ReconAgent
from sonic.agents.static_reasoning import StaticReasoningAgent
from sonic.agents.dynamic_execution import DynamicExecutionAgent
from sonic.agents.hypothesis import HypothesisGenerator
from sonic.agents.verifier import VerifierAgent
from sonic.llm.router import ModelRouter
from sonic.memory.graph import GraphMemory
from sonic.memory.schemas import (
    EngagementNode,
    EngagementStatus,
    AgentNode,
    FindingStatus,
)
from sonic.safety.scope import ScopeChecker


class EngagementManager:
    """
    Central coordinator for security engagements.
    Creates agents, runs the pipeline, and tracks state.
    """

    def __init__(
        self,
        model_router: ModelRouter,
        graph_memory: GraphMemory,
        scope_checker: ScopeChecker,
    ):
        self.router = model_router
        self.memory = graph_memory
        self.scope = scope_checker

        self.active_engagements: dict[str, dict] = {}
        self.agents: dict[str, Any] = {}

    def _create_agent(self, agent_class: type, **kwargs: Any) -> Any:
        """Create an agent with shared resources injected."""
        agent = agent_class(
            model_router=self.router,
            graph_memory=self.memory,
            scope_checker=self.scope,
            **kwargs,
        )
        self.agents[agent.agent_id] = agent
        return agent

    # ============================================
    # Engagement Lifecycle
    # ============================================

    async def create_engagement(
        self,
        name: str,
        target: str,
        scope_config: dict | None = None,
        created_by: str = "",
        tenant_id: str = "default",
    ) -> str:
        """Create a new engagement partitioned by tenant and return its ID."""
        engagement = EngagementNode(
            name=name,
            target_summary=target,
            created_by=created_by,
            tenant_id=tenant_id,
            scope_config=json.dumps(scope_config or {}),
        )

        # Store in Graph Memory
        uid = await self.memory.create_engagement(engagement)
        if not uid:
            uid = engagement.uid

        # Initialize schema if not done
        await self.memory.init_schema()

        self.active_engagements[uid] = {
            "id": uid,
            "name": name,
            "target": target,
            "tenant_id": tenant_id,
            "status": EngagementStatus.CREATED,
            "scope": scope_config or {},
            "results": {},
            "agents_used": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info("engagement_created", uid=uid, name=name, target=target, tenant_id=tenant_id)
        return uid


    async def run_engagement(
        self,
        engagement_id: str,
        phases: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Run a full engagement pipeline.
        
        Default phases: recon → hypothesis → static → dynamic → verify → report
        """
        eng = self.active_engagements.get(engagement_id)
        if not eng:
            return {"error": f"Engagement {engagement_id} not found"}

        target = eng["target"]
        scope = eng["scope"]

        # Update status
        eng["status"] = EngagementStatus.RUNNING
        await self.memory.update_engagement(engagement_id, status=EngagementStatus.RUNNING)

        default_phases = ["recon", "hypothesis", "static", "dynamic", "verify"]
        run_phases = phases or default_phases
        results: dict[str, Any] = {}

        logger.info("engagement_running", id=engagement_id, phases=run_phases)

        try:
            for phase in run_phases:
                logger.info("phase_starting", engagement=engagement_id, phase=phase)

                if phase == "recon":
                    results["recon"] = await self._run_recon(engagement_id, target, scope)

                elif phase == "hypothesis":
                    results["hypothesis"] = await self._run_hypothesis(
                        engagement_id, target, results.get("recon", {})
                    )

                elif phase == "static":
                    results["static"] = await self._run_static(
                        engagement_id, target, results.get("recon", {})
                    )

                elif phase == "dynamic":
                    results["dynamic"] = await self._run_dynamic(
                        engagement_id, target,
                        results.get("hypothesis", {}),
                        results.get("recon", {}),
                    )

                elif phase == "verify":
                    results["verify"] = await self._run_verify(engagement_id)

                logger.info("phase_complete", engagement=engagement_id, phase=phase)

            # Mark complete
            eng["status"] = EngagementStatus.COMPLETED
            eng["results"] = results
            await self.memory.update_engagement(
                engagement_id, status=EngagementStatus.COMPLETED
            )

        except Exception as e:
            logger.error("engagement_failed", id=engagement_id, error=str(e))
            eng["status"] = EngagementStatus.FAILED
            await self.memory.update_engagement(
                engagement_id, status=EngagementStatus.FAILED
            )
            results["error"] = str(e)

        return results

    # ============================================
    # Phase Runners
    # ============================================

    async def _run_recon(self, engagement_id: str, target: str, scope: dict) -> dict:
        """Run reconnaissance phase."""
        agent = self._create_agent(ReconAgent)
        self.active_engagements[engagement_id]["agents_used"].append(agent.agent_id)

        # Register agent in graph
        await self.memory.register_agent(AgentNode(
            agent_id=agent.agent_id,
            agent_type="recon",
            name=agent.name,
            engagement_id=engagement_id,
        ))

        result = await agent.run({
            "target": target,
            "engagement_id": engagement_id,
            "task": "full_recon",
        })
        return result

    async def _run_hypothesis(
        self, engagement_id: str, target: str, recon_results: dict
    ) -> dict:
        """Run hypothesis generation phase."""
        agent = self._create_agent(HypothesisGenerator)
        self.active_engagements[engagement_id]["agents_used"].append(agent.agent_id)

        await self.memory.register_agent(AgentNode(
            agent_id=agent.agent_id,
            agent_type="hypothesis",
            name=agent.name,
            engagement_id=engagement_id,
        ))

        assets = recon_results.get("assets", [])
        technologies = [
            a["value"] for a in assets
            if a.get("type") == "technology"
        ]

        result = await agent.run({
            "target": target,
            "engagement_id": engagement_id,
            "assets": assets,
            "technologies": technologies,
        })
        return result

    async def _run_static(
        self, engagement_id: str, target: str, recon_results: dict
    ) -> dict:
        """Run static analysis phase."""
        agent = self._create_agent(StaticReasoningAgent)
        self.active_engagements[engagement_id]["agents_used"].append(agent.agent_id)

        await self.memory.register_agent(AgentNode(
            agent_id=agent.agent_id,
            agent_type="static",
            name=agent.name,
            engagement_id=engagement_id,
        ))

        result = await agent.run({
            "target": target,
            "engagement_id": engagement_id,
            "assets": recon_results.get("assets", []),
            "task": "full_analysis",
        })
        return result

    async def _run_dynamic(
        self, engagement_id: str, target: str,
        hypothesis_results: dict, recon_results: dict
    ) -> dict:
        """Run dynamic testing phase."""
        agent = self._create_agent(DynamicExecutionAgent)
        self.active_engagements[engagement_id]["agents_used"].append(agent.agent_id)

        await self.memory.register_agent(AgentNode(
            agent_id=agent.agent_id,
            agent_type="dynamic",
            name=agent.name,
            engagement_id=engagement_id,
        ))

        result = await agent.run({
            "target": target,
            "engagement_id": engagement_id,
            "hypotheses": hypothesis_results.get("hypotheses", []),
            "assets": recon_results.get("assets", []),
            "task": "general_testing",
        })
        return result

    async def _run_verify(self, engagement_id: str) -> dict:
        """Run verification phase on all unverified findings."""
        agent = self._create_agent(VerifierAgent)
        self.active_engagements[engagement_id]["agents_used"].append(agent.agent_id)

        await self.memory.register_agent(AgentNode(
            agent_id=agent.agent_id,
            agent_type="verifier",
            name=agent.name,
            engagement_id=engagement_id,
        ))

        result = await agent.run({
            "engagement_id": engagement_id,
        })
        return result

    # ============================================
    # Status & Reports
    # ============================================

    async def get_engagement_status(self, engagement_id: str, tenant_id: str | None = None) -> dict:
        """Get current engagement status with tenant isolation."""
        eng = self.active_engagements.get(engagement_id)
        if eng:
            if tenant_id and eng.get("tenant_id") != tenant_id:
                return {"error": "Engagement not found or unauthorized"}
            summary = await self.memory.get_engagement_summary(engagement_id, tenant_id=tenant_id)
            return {
                **eng,
                "graph_summary": summary,
            }

        # Try loading from graph
        graph_eng = await self.memory.get_engagement(engagement_id, tenant_id=tenant_id)
        if graph_eng:
            if tenant_id and graph_eng.get("tenant_id") != tenant_id:
                return {"error": "Engagement not found or unauthorized"}
            summary = await self.memory.get_engagement_summary(engagement_id, tenant_id=tenant_id)
            return {
                **graph_eng,
                "graph_summary": summary,
            }
        return {"error": "Engagement not found"}


    async def get_findings_report(self, engagement_id: str) -> dict:
        """Get all verified findings for reporting."""
        findings = await self.memory.find_findings(
            engagement_id,
            status=FindingStatus.VERIFIED,
        )

        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        findings.sort(key=lambda f: severity_order.get(f.get("severity", "info"), 5))

        return {
            "engagement_id": engagement_id,
            "total_findings": len(findings),
            "by_severity": {
                sev: len([f for f in findings if f.get("severity") == sev])
                for sev in ["critical", "high", "medium", "low", "info"]
            },
            "findings": findings,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def list_agents(self) -> list[dict]:
        """List all agents and their status."""
        return [agent.get_status() for agent in self.agents.values()]

    async def kill_all(self) -> dict:
        """Emergency stop — halt all agents."""
        for agent in self.agents.values():
            agent.status = "killed"

        for eng_id, eng in self.active_engagements.items():
            if eng["status"] == EngagementStatus.RUNNING:
                eng["status"] = EngagementStatus.FAILED
                await self.memory.update_engagement(eng_id, status=EngagementStatus.FAILED)

        logger.warning("kill_all_executed", agents=len(self.agents))
        return {"killed_agents": len(self.agents), "status": "all_stopped"}
