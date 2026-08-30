"""
SONIC-REDA — Swarm Runner (Full System Orchestration)
========================================================
The main entrypoint that boots the entire SONIC-REDA system:
    - Initializes memory backend (Neo4j or InMemory fallback)
    - Creates LLM Model Router with configured providers
    - Spawns agent swarm with ReAct execution engines
    - Manages engagement lifecycle from target input to verified findings

This is the file that makes everything ACTUALLY work end-to-end.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from sonic.agents.base import BaseAgent
from sonic.agents.cognitive_state import EngagementBudget
from sonic.agents.director import Director
from sonic.agents.engagement import EngagementManager
from sonic.agents.hypothesis import HypothesisGenerator
from sonic.agents.orchestrator import MetaOrchestrator
from sonic.agents.react_engine import (
    ReActEngine,
    ToolRegistry,
    create_default_tool_registry,
)
from sonic.agents.recon import ReconAgent
from sonic.agents.state_store import get_state_store
from sonic.agents.static_reasoning import StaticReasoningAgent
from sonic.agents.verifier import VerifierAgent
from sonic.llm.providers.custom import CustomLLMProvider
from sonic.llm.router import ModelRouter
from sonic.logger import get_logger
from sonic.memory.inmemory import InMemoryGraph
from sonic.memory.router import get_smart_memory
from sonic.memory.schemas import (
    AssetNode,
    AssetType,
    EngagementNode,
    FindingNode,
    FindingSeverity,
    FindingStatus,
)
from sonic.observability.metrics import get_metrics
from sonic.safety.rate_limiter import get_rate_limiter
from sonic.safety.scope import ScopeChecker

logger = get_logger(__name__)


class SwarmRunner:
    """
    Main system runner that boots the full SONIC-REDA swarm.
    """

    def __init__(
        self,
        llm_base_url: str = "",
        llm_api_key: str = "",
        llm_model: str = "",
    ):
        self.llm_base_url = llm_base_url
        self.llm_api_key = llm_api_key
        self.llm_model = llm_model

        self.memory = None
        self.router = None
        self.scope_checker = None
        self.rate_limiter = None
        self.tool_registry = None
        self.react_engine = None
        self.director = None
        self.metrics = get_metrics()

        self._agents: dict[str, BaseAgent] = {}
        self._initialized = False

    async def initialize(self) -> bool:
        """Boot the full system."""
        logger.info("swarm_runner_initializing")

        # 1. Memory Backend (Neo4j or InMemory fallback)
        self.memory = await get_smart_memory()
        logger.info("memory_ready", backend=type(self.memory).__name__)

        # 2. LLM Model Router
        self.router = ModelRouter()
        if self.llm_base_url and self.llm_api_key and self.llm_model:
            provider = CustomLLMProvider(
                base_url=self.llm_base_url,
                api_key=self.llm_api_key,
                model=self.llm_model,
            )
            self.router.register_provider("custom", provider)
            logger.info("llm_provider_registered", model=self.llm_model)
        else:
            logger.warning("no_llm_configured", note="Agent reasoning is unavailable until an LLM provider is configured")

        # 3. Safety
        self.scope_checker = ScopeChecker()
        self.rate_limiter = get_rate_limiter()

        # 4. Tool Registry & ReAct Engine
        self.tool_registry = create_default_tool_registry()
        self.react_engine = ReActEngine(self.tool_registry, max_iterations=8)

        # 5. Spawn Core Agents
        agent_configs = [
            ("orchestrator", MetaOrchestrator),
            ("recon", ReconAgent),
            ("static", StaticReasoningAgent),
            ("hypothesis", HypothesisGenerator),
            ("verifier", VerifierAgent),
        ]

        for name, agent_cls in agent_configs:
            agent = agent_cls(
                model_router=self.router,
                graph_memory=self.memory,
                scope_checker=self.scope_checker,
            )
            self._agents[name] = agent
            self.metrics.active_agents += 1

        # 6. Director (Phase 5 — Event-driven orchestration)
        self.director = Director(
            model_router=self.router,
            graph_memory=self.memory,
            scope_checker=self.scope_checker,
            state_store=get_state_store(),
        )

        self._initialized = True
        logger.info("swarm_runner_ready", agents=len(self._agents), director="active")
        return True

    async def run_engagement(
        self,
        target: str,
        scope_config: dict[str, Any] | None = None,
        tenant_id: str = "",
        use_director: bool = True,
    ) -> dict[str, Any]:
        """
        Execute a full engagement against a target.

        Args:
            target: Target to assess
            scope_config: Scope configuration
            tenant_id: From authenticated request context (REQUIRED for director mode)
            use_director: If True, use Phase 5 Director. If False, use legacy flow.
        """
        if not self._initialized:
            await self.initialize()

        logger.info("engagement_started", target=target)
        self.metrics.active_engagements += 1

        # Phase 5: Use Director for event-driven orchestration
        if use_director and self.director and tenant_id:
            engagement_id = await self.director.start_engagement(
                target=target,
                scope=scope_config or {"target": target},
                tenant_id=tenant_id,
            )

            # Dispatch → worker → on_task_completed loop
            results = await self._run_dispatch_loop(engagement_id, tenant_id)

            self.metrics.active_engagements -= 1
            return {
                "engagement_id": engagement_id,
                "target": target,
                "tenant_id": tenant_id,
                "mode": "director",
                **results,
            }

        # Legacy flow (backward compatibility)
        # 1. Create Engagement in Memory
        engagement = EngagementNode(
            name=f"Assessment: {target}",
            target=target,
            scope=json.dumps(scope_config or {"target": target}),
            status="running",
        )
        engagement_id = await self.memory.create_engagement(engagement)

        results = {
            "engagement_id": engagement_id,
            "target": target,
            "phases": {},
            "findings": [],
            "assets": [],
        }

        # 2. RECON PHASE — Discovery
        logger.info("phase_recon_starting", target=target)
        recon_agent = self._agents.get("recon")
        if recon_agent:
            recon_result = await recon_agent.run({
                "target": target,
                "engagement_id": engagement_id,
                "scope": scope_config or {},
            })
            results["phases"]["recon"] = recon_result

            # Store discovered assets
            for asset_data in recon_result.get("assets", []):
                asset = AssetNode(
                    asset_type=asset_data.get("type", AssetType.DOMAIN),
                    value=asset_data.get("value", target),
                    name=asset_data.get("name", target),
                    discovered_by=recon_agent.agent_id,
                    engagement_id=engagement_id or "",
                )
                await self.memory.create_asset(asset)
                results["assets"].append(asset_data)

        # 3. HYPOTHESIS PHASE — Creative Bug Ideation
        logger.info("phase_hypothesis_starting")
        hypothesis_agent = self._agents.get("hypothesis")
        if hypothesis_agent:
            hypo_result = await hypothesis_agent.run({
                "target": target,
                "engagement_id": engagement_id,
                "recon_data": results.get("phases", {}).get("recon", {}),
            })
            results["phases"]["hypothesis"] = hypo_result

        # 4. STATIC ANALYSIS PHASE
        logger.info("phase_static_starting")
        static_agent = self._agents.get("static")
        if static_agent:
            static_result = await static_agent.run({
                "target": target,
                "engagement_id": engagement_id,
            })
            results["phases"]["static"] = static_result

        # 5. VERIFICATION PHASE
        logger.info("phase_verification_starting")
        verifier = self._agents.get("verifier")
        all_findings = []

        # Collect findings from all phases
        for phase_name, phase_data in results.get("phases", {}).items():
            if isinstance(phase_data, dict):
                for f in phase_data.get("findings", []):
                    all_findings.append(f)

        verified_findings = []
        if verifier and all_findings:
            for finding_data in all_findings:
                verify_result = await verifier.run({
                    "finding": finding_data,
                    "engagement_id": engagement_id,
                })
                if verify_result.get("verified", False):
                    verified_findings.append({
                        **finding_data,
                        "confidence": verify_result.get("confidence", 0),
                        "status": "verified",
                    })
                    self.metrics.record_finding(finding_data.get("severity", "medium"))

        results["findings"] = verified_findings
        results["summary"] = {
            "target": target,
            "total_assets": len(results["assets"]),
            "total_findings": len(verified_findings),
            "critical": sum(1 for f in verified_findings if f.get("severity") == "critical"),
            "high": sum(1 for f in verified_findings if f.get("severity") == "high"),
            "medium": sum(1 for f in verified_findings if f.get("severity") == "medium"),
            "status": "completed",
        }

        # Update engagement status
        if engagement_id:
            await self.memory.update_engagement(engagement_id, status="completed")

        self.metrics.active_engagements -= 1
        logger.info("engagement_completed", target=target, findings=len(verified_findings))
        return results

    async def _run_dispatch_loop(
        self,
        engagement_id: str,
        tenant_id: str,
        max_iterations: int = 50,
    ) -> dict[str, Any]:
        """
        Core dispatch → worker → on_task_completed loop.

        Repeatedly:
            1. Fetch dispatchable tasks from the Director.
            2. Map each task's agent_type to a swarm agent.
            3. Run the agent and collect its output.
            4. Report completion via Director.on_task_completed.
        Until the task graph is complete or the iteration budget is exhausted.
        """
        logger.info("dispatch_loop_starting", engagement_id=engagement_id)

        # agent_type → swarm agent name mapping
        agent_map = {
            "recon": "recon",
            "static": "static",
            "hypothesis": "hypothesis",
            "verifier": "verifier",
            "dynamic": "recon",       # dynamic testing falls back to recon agent
            "orchestrator": "orchestrator",
        }

        all_outputs: list[dict[str, Any]] = []
        all_findings: list[dict[str, Any]] = []
        completed = 0
        failed = 0

        for iteration in range(max_iterations):
            dispatchable = self.director.get_dispatchable_tasks(engagement_id)

            if not dispatchable:
                # Check if graph is complete
                graph = self.director._graphs.get(engagement_id)
                if graph is not None and graph.is_complete():
                    logger.info(
                        "dispatch_loop_complete",
                        engagement_id=engagement_id,
                        iterations=iteration,
                        completed=completed,
                        failed=failed,
                    )
                    break
                # No dispatchable tasks but not complete — could be running tasks
                # or blocked. Brief yield then continue.
                await asyncio.sleep(0.01)
                continue

            # Dispatch tasks concurrently (up to max_parallel handled by Director)
            tasks_to_run = []
            for task_payload in dispatchable:
                agent_type = task_payload.get("agent_type", "recon")
                agent_name = agent_map.get(agent_type, "recon")
                agent = self._agents.get(agent_name)
                if agent is None:
                    # No agent available — mark as failed
                    await self.director.on_task_completed(
                        engagement_id=engagement_id,
                        task_id=task_payload.get("task_id", ""),
                        result={"status": "failed", "error": f"No agent for type {agent_type}"},
                    )
                    failed += 1
                    continue
                tasks_to_run.append(self._execute_single_task(agent, task_payload, engagement_id))

            if tasks_to_run:
                outputs = await asyncio.gather(*tasks_to_run, return_exceptions=True)
                for out in outputs:
                    if isinstance(out, Exception):
                        logger.warning("task_execution_error", error=str(out))
                        failed += 1
                    elif isinstance(out, dict):
                        all_outputs.append(out)
                        completed += 1
                        # Collect findings
                        for f in out.get("findings", []):
                            all_findings.append(f)
                            self.metrics.record_finding(f.get("severity", "medium"))

        state = self.director.get_engagement_state(engagement_id)
        graph = self.director.get_task_graph(engagement_id)

        return {
            "dispatchable_tasks": [],
            "cognitive_state": state,
            "task_graph": graph,
            "outputs": all_outputs,
            "findings": all_findings,
            "tasks_completed": completed,
            "tasks_failed": failed,
            "summary": {
                "target": "",
                "total_findings": len(all_findings),
                "critical": sum(1 for f in all_findings if f.get("severity") == "critical"),
                "high": sum(1 for f in all_findings if f.get("severity") == "high"),
                "medium": sum(1 for f in all_findings if f.get("severity") == "medium"),
                "status": "completed",
            },
        }

    async def _execute_single_task(
        self,
        agent: BaseAgent,
        task_payload: dict[str, Any],
        engagement_id: str,
    ) -> dict[str, Any]:
        """Run a single agent task and report completion to the Director."""
        task_id = task_payload.get("task_id", "")
        try:
            result = await agent.run(task_payload)
            await self.director.on_task_completed(
                engagement_id=engagement_id,
                task_id=task_id,
                result=result,
            )
            return result
        except Exception as e:
            logger.error("single_task_failed", task_id=task_id, error=str(e))
            await self.director.on_task_completed(
                engagement_id=engagement_id,
                task_id=task_id,
                result={"status": "failed", "error": str(e)},
            )
            raise

    def get_status(self) -> dict[str, Any]:
        """Get current swarm status."""
        return {
            "initialized": self._initialized,
            "memory_backend": type(self.memory).__name__ if self.memory else "None",
            "llm_configured": bool(self.llm_base_url),
            "agents": {name: agent.get_status() for name, agent in self._agents.items()},
            "metrics": {
                "active_engagements": self.metrics.active_engagements,
                "active_agents": self.metrics.active_agents,
                "findings": self.metrics.findings_total,
                "llm_requests": self.metrics.llm_requests_total,
            },
        }


# Global singleton
_swarm_runner: Optional[SwarmRunner] = None


def get_swarm_runner() -> SwarmRunner:
    global _swarm_runner
    if _swarm_runner is None:
        _swarm_runner = SwarmRunner()
    return _swarm_runner
