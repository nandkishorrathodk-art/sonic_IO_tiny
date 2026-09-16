"""
SONIC-REDA ??? Engagement Manager
===================================
Manages the full lifecycle of a security engagement.
Coordinates agents, manages state, and produces reports.

Lifecycle:
    1. CREATE: Initialize engagement with target + scope
    2. RECON: Run Recon Agent ??? discover attack surface
    3. HYPOTHESIZE: Run Hypothesis Generator ??? creative ideation
    4. ANALYZE: Run Static Reasoning ??? code/config analysis
    5. TEST: Run Dynamic Execution ??? active testing
    6. VERIFY: Run Verifier ??? validate findings
    7. REPORT: Compile results ??? generate report
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sonic.logger import get_logger
from sonic.sandbox.egress import is_target_allowed

logger = get_logger(__name__)

from sonic.agents.dynamic_execution import DynamicExecutionAgent
from sonic.agents.exploit_chain import ExploitChainEngine
from sonic.agents.hypothesis import HypothesisGenerator
from sonic.agents.recon import ReconAgent
from sonic.agents.static_reasoning import StaticReasoningAgent
from sonic.agents.verifier import VerifierAgent
from sonic.evidence.independent_verifier import AdversarialReviewer, IndependentVerifier
from sonic.evidence.reproduction_engine import ReproductionEngine
from sonic.llm.router import ModelRouter
from sonic.memory.graph import GraphMemory
from sonic.memory.schemas import (
    AgentNode,
    EngagementNode,
    EngagementStatus,
    FindingStatus,
)
from sonic.safety.scope import ScopeChecker
from sonic.sandbox.provider import ComputeProvider


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
        compute_provider: Any = None,
        *,
        sandbox_provider: Any = None,
        computer_provider: Any = None,
        reproduction_engine: Any = None,
        bug_bounty_client: Any = None,
        bugbounty_client: Any = None,
        **kwargs: Any,
    ):
        self.router = model_router
        self.memory = graph_memory
        self.scope = scope_checker
        self.sandbox_provider = sandbox_provider if sandbox_provider is not None else compute_provider
        self.provider = self.sandbox_provider
        # GUI-capable computer body (ComputerProvider: screenshot/gui_action/
        # launch_application/terminal). Falls back to the sandbox provider when
        # no explicit computer provider is wired so existing call sites keep
        # working, but _run_computer_dynamic is what actually drives the
        # ComputerUseAgent and it now prefers this GUI body.
        self.computer_provider = computer_provider if computer_provider is not None else self.provider
        self.reproduction_engine = reproduction_engine
        self.bug_bounty_client = bug_bounty_client if bug_bounty_client is not None else bugbounty_client
        self.bugbounty_client = self.bug_bounty_client

        self.active_engagements: dict[str, dict] = {}
        self.agents: dict[str, Any] = {}
        # engagement_id -> sandbox workspace_id (provisioned lazily per tenant).
        self._workspaces: dict[str, str] = {}

    async def ensure_sandbox(self, provider_factory: Any = None) -> None:
        """Attach (or build) the sandbox provider + reproduction engine.

        Idempotent: a no-op once a provider is attached. ``provider_factory`` is
        an awaitable returning a ComputeProvider (e.g. ``get_sandbox_provider``
        or ``get_compute_provider`` wrapped to async). When a provider is built,
        a ReproductionEngine is bound to it unless one was already supplied.
        """
        if self.sandbox_provider is not None:
            return
        if provider_factory is None:
            return
        provider = provider_factory
        # Support both an awaitable factory and a sync callable.
        if callable(provider_factory):
            maybe = provider_factory()
            provider = await maybe if hasattr(maybe, "__await__") else maybe
        if provider is None:
            return
        self.sandbox_provider = provider
        if self.reproduction_engine is None:
            try:
                from sonic.evidence.reproduction_engine import ReproductionEngine
                self.reproduction_engine = ReproductionEngine(compute_provider=provider)
            except Exception as e:  # import wiring, never fatal to the run
                logger.warning("reproduction_engine_build_failed", error=str(e))

    async def _workspace_for(self, engagement_id: str, tenant_id: str = "default") -> str:
        """Return a sandbox workspace_id for the engagement, provisioning once.

        Returns "" when no provider is attached (legacy host-probe path).
        """
        if self.sandbox_provider is None:
            return ""
        cached = self._workspaces.get(engagement_id)
        if cached:
            return cached
        workspace_id = ""
        provider = self.sandbox_provider
        try:
            # A long-lived per-tenant home is preferred over a throwaway workspace.
            if hasattr(provider, "get_or_create_home"):
                home = await provider.get_or_create_home(tenant_id)
                workspace_id = getattr(home, "id", "") or ""
            if not workspace_id and hasattr(provider, "create_workspace"):
                from sonic.sandbox.provider import WorkspaceConfig
                ws_id = f"eng-{engagement_id[:8] or tenant_id}"
                await provider.create_workspace(WorkspaceConfig(workspace_id=ws_id))
                workspace_id = ws_id
        except Exception as e:
            logger.warning("engagement_workspace_provision_failed", error=str(e))
        self._workspaces[engagement_id] = workspace_id
        return workspace_id

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
        # Egress / scope guard: refuse to create an engagement whose target
        # resolves to a private, loopback, or cloud-metadata address. This
        # prevents an agent from being pointed at internal infrastructure.
        # Unresolvable-at-creation domains are allowed (an operator explicitly
        # authorizes the target; execution-time egress enforcement still applies).
        allowed, reason = is_target_allowed(target, allow_unresolvable=True)
        if not allowed:
            logger.warning("engagement_target_egress_denied", target=target, reason=reason)
            return ""

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
            "created_at": datetime.now(UTC).isoformat(),
        }

        logger.info("engagement_created", uid=uid, name=name, target=target, tenant_id=tenant_id)
        return uid


    async def run_engagement(
        self,
        engagement_id: str,
        phases: list[str] | None = None,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Run a full engagement pipeline.

        Default phases: recon ??? hypothesis ??? static ??? dynamic ??? verify ??? report
        """
        eng = self.active_engagements.get(engagement_id)
        if not eng:
            return {"error": f"Engagement {engagement_id} not found"}

        # Tenant ownership check: refuse to run another tenant's engagement.
        if tenant_id and eng.get("tenant_id") != tenant_id:
            logger.warning(
                "cross_tenant_run_denied",
                engagement_id=engagement_id,
                requesting_tenant=tenant_id,
                owner_tenant=eng.get("tenant_id"),
            )
            return {"error": "Engagement not found or unauthorized"}

        target = eng["target"]
        scope = eng["scope"]

        # Update status
        eng["status"] = EngagementStatus.RUNNING
        await self.memory.update_engagement(engagement_id, status=EngagementStatus.RUNNING)

        default_phases = [
            "recon", "hypothesis", "research", "static", "dynamic",
            "computer_dynamic", "verify", "chain", "report", "submit",
        ]
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

                elif phase == "research":
                    results["research"] = await self._run_research(
                        engagement_id, target, results.get("hypothesis", {}),
                        results.get("recon", {}),
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

                elif phase == "computer_dynamic":
                    results["computer_dynamic"] = await self._run_computer_dynamic(
                        engagement_id, target,
                        results.get("hypothesis", {}),
                        results.get("recon", {}),
                        results.get("dynamic", {}),
                    )

                elif phase == "verify":
                    results["verify"] = await self._run_verify(engagement_id)

                elif phase == "chain":
                    results["chain"] = await self._run_chain(
                        engagement_id, results,
                    )

                elif phase == "report":
                    results["report"] = await self._run_report(engagement_id, target, results)

                elif phase == "submit":
                    results["submit"] = await self._run_submit(engagement_id, results)

                logger.info("phase_complete", engagement=engagement_id, phase=phase)

            # Collect findings produced across phases for the summary.
            all_findings = self._collect_findings(results)
            results["findings"] = all_findings
            results["summary"] = self._build_summary(target, all_findings, results)

            phase_states = [v.get("status") for v in results.values() if isinstance(v, dict) and "status" in v]
            final_status = EngagementStatus.FAILED if any(status in {"FAILED", "NOT_EXECUTED"} for status in phase_states) else EngagementStatus.COMPLETED
            eng["status"] = final_status
            eng["results"] = results
            await self.memory.update_engagement(engagement_id, status=final_status)

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
        """Run the autonomous dynamic pentest loop.

        When a sandbox provider is attached the probe runs INSIDE the sandbox
        (curl in the container) instead of from the host, so active testing
        happens through the isolated compute substrate the user provisioned.
        """
        eng = self.active_engagements.get(engagement_id, {})
        scope_config = eng.get("scope") or {}
        tenant_id = eng.get("tenant_id", "default")
        workspace_id = await self._workspace_for(engagement_id, tenant_id)

        agent = self._create_agent(
            DynamicExecutionAgent,
            sandbox_provider=self.sandbox_provider,
            workspace_id=workspace_id,
            scope_config=scope_config,
        )
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
            "scope_config": scope_config,
        })
        return result

    async def _run_verify(self, engagement_id: str) -> dict:
        """Run verification phase on all unverified findings.

        When a reproduction engine is attached (or a sandbox provider is available),
        the Verifier reproduces each finding's PoC inside the sandbox (real execution)
        instead of only re-firing the HTTP request or LLM-guessing.
        """
        eng = self.active_engagements.get(engagement_id, {})
        reproduction_engine = self.reproduction_engine
        if reproduction_engine is None and self.provider is not None:
            reproduction_engine = ReproductionEngine(compute_provider=self.provider)

        extra_kwargs: dict[str, Any] = {}
        if reproduction_engine is not None:
            extra_kwargs["reproduction_engine"] = reproduction_engine
            extra_kwargs["independent_verifier"] = IndependentVerifier()
            extra_kwargs["adversarial_reviewer"] = AdversarialReviewer()

        agent = self._create_agent(
            VerifierAgent,
            scope_config=eng.get("scope") or {},
            **extra_kwargs,
        )
        self.active_engagements[engagement_id]["agents_used"].append(agent.agent_id)

        await self.memory.register_agent(AgentNode(
            agent_id=agent.agent_id,
            agent_type="verifier",
            name=agent.name,
            engagement_id=engagement_id,
        ))

        result = await agent.run({
            "engagement_id": engagement_id,
            "scope_config": eng.get("scope") or {},
        })
        return result

    # ---- NEW PHASES (Gap fixes) ----

    async def _run_research(
        self, engagement_id: str, target: str,
        hypothesis_results: dict, recon_results: dict,
    ) -> dict:
        """Run autonomous research phase using ResearchManager (Gap #6).

        Seeds research questions from recon assets and hypotheses,
        runs investigation tracks, and returns structured findings.
        Gracefully degrades if ResearchManager dependencies are unavailable.
        """
        try:
            from sonic.researcher.manager import ResearchManager
            from sonic.researcher.models import ResearchMode

            eng = self.active_engagements.get(engagement_id, {})
            tenant_id = eng.get("tenant_id", "default")

            mgr = ResearchManager(
                mission_id=engagement_id,
                tenant_id=tenant_id,
                goal=f"Security assessment of {target}",
                mode=ResearchMode.AUTONOMOUS,
            )

            # Seed with recon facts
            assets = recon_results.get("assets", [])
            initial_facts = [
                f"Discovered asset: {a.get('type', '')} = {a.get('value', '')}"
                for a in assets[:20]
            ]
            mgr.add_initial_facts(initial_facts)

            # Convert hypotheses to research questions
            for h in hypothesis_results.get("hypotheses", [])[:10]:
                title = h.get("title", "") or h.get("statement", "")
                if title:
                    mgr.add_question(
                        question=f"Is this vulnerability exploitable: {title}?",
                        importance=0.8,
                    )
                    # Also propose as a hypothesis in the research portfolio
                    mgr.propose_hypothesis(
                        statement=title,
                        confidence=float(h.get("confidence", 0.5)),
                    )

            # Generate research report
            report = mgr.generate_report()
            logger.info("research_phase_complete",
                        engagement=engagement_id,
                        questions=len(mgr.questions),
                        hypotheses=len(mgr.portfolio.hypotheses))
            return {
                "status": "COMPLETED", "executed": True,
                "questions": len(mgr.questions),
                "hypotheses": len(mgr.portfolio.hypotheses),
                "report_summary": report.summary if hasattr(report, "summary") else str(report),
                "initial_facts": initial_facts,
            }
        except Exception as e:
            logger.warning("research_phase_failed", error=str(e))
            return {"status": "FAILED", "executed": False, "reason": str(e)}

    async def _run_computer_dynamic(
        self, engagement_id: str, target: str,
        hypothesis_results: dict, recon_results: dict,
        http_dynamic_results: dict,
    ) -> dict:
        """Run REAL dynamic testing via ComputerUseAgent in sandbox (Gaps #1, #2, #5).

        This is the core gap fix: the engagement pipeline now routes through
        ComputerUseAgent with target-first dynamic inspection, browser automation,
        native network probes, and autonomous Toolsmith + MethodLab capabilities.

        The HTTP-probe dynamic phase (previous step) gives fast initial coverage.
        This phase runs deeper scans inside the sandbox.
        """
        provider = self.computer_provider or self.provider
        if provider is None:
            logger.info("computer_dynamic_skipped_no_provider",
                        engagement=engagement_id)
            return {
                "status": "NOT_EXECUTED",
                "executed": False,
                "skipped": True,
                "reason": "No ComputeProvider available ??? GUI desktop/sandbox required for real tool execution",
            }

        try:
            from sonic.computer_use.agent import ComputerUseAgent
            from sonic.safety.sealed import seal_default

            eng = self.active_engagements.get(engagement_id, {})
            tenant_id = eng.get("tenant_id", "default")
            scope_config = eng.get("scope") or {}
            safety = seal_default(workspace_root="/home/sonic/workspace", scope_checker=self.scope, scope_config=scope_config, tenant_id=tenant_id)

            # Optionally wire Toolsmith + MethodLab for self-evolution during engagement
            extra_agent_kwargs: dict[str, Any] = {}
            try:
                from sonic.being.craft import BeingCraft
                from sonic.being.method_lab import MethodLab
                from sonic.being.toolsmith import ToolsmithLoop
                from sonic.memory.vector import get_vector_memory

                toolsmith = ToolsmithLoop(
                    craft=BeingCraft(being_id=f"engagement-{engagement_id}"),
                    llm=self.router,
                    registry=None,
                )
                method_lab = MethodLab(
                    llm=self.router,
                    vector_memory=get_vector_memory(),
                    toolsmith=toolsmith,
                )
                extra_agent_kwargs["toolsmith"] = toolsmith
                extra_agent_kwargs["method_lab"] = method_lab
                logger.info("toolsmith_method_lab_wired", engagement=engagement_id)
            except Exception as e:
                logger.debug("toolsmith_wiring_skipped", error=str(e))

            # Dual-Plane Operational Model (Rule 5): both Graphical Desktop (GUI) and
            # Dedicated Headless Terminal/Tool plane remain concurrently active.
            gui_only = False

            eng = self.active_engagements.get(engagement_id, {})
            tenant_id = eng.get("tenant_id", "default")

            # Create the agent with direct reasoning and sealed safety boundary.
            # Uses the GUI-capable computer_provider (DockerComputerProvider/
            # DaytonaComputerProvider) where screenshot/gui_action/launch_application
            # all route to the real desktop, while terminal commands run in the sandbox.
            agent = ComputerUseAgent(
                computer_provider=provider,
                safety=safety,
                browser=None,
                gui_only=False,
                observe_desktop=True,
                tenant_id=tenant_id,
                **extra_agent_kwargs,
            )

            # Build the goal from engagement context
            hypotheses_summary = ", ".join(
                h.get("title", "")[:60]
                for h in hypothesis_results.get("hypotheses", [])[:5]
            )
            http_findings = (http_dynamic_results or {}).get("findings", [])
            http_summary = ", ".join(
                f.get("title", "")[:40] for f in http_findings[:5]
            )
            goal = (
                f"Perform comprehensive security assessment of {target}. "
                f"Test hypotheses: {hypotheses_summary or 'general security testing'}. "
                f"HTTP probe found: {http_summary or 'no initial findings'}. "
                f"Autonomously assess target security posture, investigate attack surface, and report findings."
            )

            # Create a workspace and run the mission. The GUI computer body has
            # its own workspace id (container name); the sandbox provider's
            # workspace is ONLY a fallback when no GUI computer is wired.
            ws_id = getattr(provider, "_default_workspace_id", None)
            if not isinstance(ws_id, str) or not ws_id.strip() or ws_id == "None":
                ws_id = await self._workspace_for(engagement_id, tenant_id=tenant_id) or f"eng-{engagement_id[:12]}"

            traces = await agent.run_mission(
                workspace_id=ws_id,
                goal=goal,
                steps=getattr(agent, "max_actions", 25),
            )

            # Extract findings from traces and persist to memory so Verifier can inspect them
            findings = []
            for trace in (traces or []):
                obs = getattr(trace, "actual_observation", "") or getattr(trace, "observation", "")
                if obs and isinstance(obs, str) and any(kw in obs.lower() for kw in
                    ["open", "vuln", "found", "critical", "high", "medium",
                     "cve-", "exposed", "injection", "xss"]):
                    action_name = getattr(trace.action_type, "value", str(trace.action_type))
                    target_res = getattr(trace, "target_resource", target) or target
                    title = f"Security finding from {action_name}: {target_res}"
                    desc = obs[:500]
                    finding_dict = {
                        "title": title,
                        "description": desc,
                        "severity": "medium",
                        "vulnerability_class": "dynamic_scan",
                        "source": "computer_dynamic",
                        "target": target,
                    }
                    findings.append(finding_dict)
                    if self.memory:
                        try:
                            from sonic.memory.schemas import FindingNode, FindingSeverity, FindingStatus
                            await self.memory.create_finding(FindingNode(
                                title=title,
                                description=desc,
                                vulnerability_class="dynamic_scan",
                                severity=FindingSeverity.MEDIUM,
                                status=FindingStatus.NEEDS_VERIFICATION,
                                target_asset=target,
                                engagement_id=engagement_id,
                                found_by=getattr(agent, "agent_id", "computer_dynamic"),
                            ))
                        except Exception as mem_err:
                            logger.debug("engagement_finding_persist_failed", error=str(mem_err))

            logger.info("computer_dynamic_complete",
                        engagement=engagement_id,
                        traces=len(traces or []),
                        findings=len(findings))

            return {
                "traces": len(traces or []),
                "findings": findings,
                "tools_used": list(agent.security_tools.keys()),
                "goal": goal,
            }
        except Exception as e:
            logger.warning("computer_dynamic_failed", error=str(e),
                          engagement=engagement_id)
            return {"status": "FAILED", "executed": False, "reason": str(e)}

    async def _run_chain(self, engagement_id: str, results: dict) -> dict:
        """Run exploit chaining analysis on verified findings (Gap #8).

        Analyzes verified findings for opportunities to chain multiple
        vulnerabilities into higher-impact exploits.
        """
        all_findings = self._collect_findings(results)
        if len(all_findings) < 2:
            return {"chains": [], "reason": "Need at least 2 findings to chain"}

        eng = self.active_engagements.get(engagement_id, {})
        target = eng.get("target", "")

        engine = ExploitChainEngine(model_router=self.router)
        chains = await engine.analyze_chains(all_findings, target=target)

        chain_dicts = []
        for chain in chains:
            chain_dicts.append({
                "chain_id": chain.chain_id,
                "title": chain.title,
                "combined_severity": chain.combined_severity,
                "combined_impact": chain.combined_impact,
                "steps": chain.chain_steps,
                "confidence": chain.confidence,
                "original_severities": chain.original_severities,
                "finding_count": len(chain.findings),
            })

        logger.info("exploit_chain_analysis_complete",
                    engagement=engagement_id,
                    chains_found=len(chains))
        return {"chains": chain_dicts}

    async def _run_submit(self, engagement_id: str, results: dict) -> dict:
        """Auto-format and optionally submit findings to bug bounty platforms (Gap #4).

        When a BugBountyClient is configured, formats verified findings
        as platform-ready draft reports. Does NOT auto-submit without
        explicit confirmation ??? generates drafts for operator review.
        """
        client = self.bug_bounty_client or self.bugbounty_client
        if client is None:
            return {"skipped": True, "reason": "No BugBountyClient configured"}

        all_findings = self._collect_findings(results)
        reportable = [
            f for f in all_findings
            if (f.get("severity", "").lower() in ("critical", "high"))
        ]
        if not reportable:
            return {"drafts": [], "reason": "No high/critical findings to report"}

        drafts = []
        for finding in reportable:
            try:
                draft = client.format_report(finding)
                drafts.append({
                    "title": finding.get("title", ""),
                    "severity": finding.get("severity", ""),
                    "draft": draft if isinstance(draft, dict) else str(draft),
                })
            except Exception as e:
                logger.warning("bugbounty_format_failed",
                             title=finding.get("title", ""), error=str(e))

        logger.info("bugbounty_drafts_generated",
                    engagement=engagement_id,
                    drafts=len(drafts))
        return {"drafts": drafts, "auto_submitted": False}

    async def _run_report(self, engagement_id: str, target: str, results: dict) -> dict:
        """Compile a final report from all verified findings."""
        report = await self.get_findings_report(engagement_id)
        dynamic = results.get("dynamic", {}) or {}
        report["engagement"] = {
            "engagement_id": engagement_id,
            "target": target,
            "phases_run": [k for k in results if k not in ("findings", "summary", "error")],
            "tests_executed": dynamic.get("tests_executed", 0),
            "failed_attempts": len(dynamic.get("failed_attempts", []) or []),
            "observations": len(dynamic.get("observations", []) or []),
            "generated_at": datetime.now(UTC).isoformat(),
        }
        return report

    def _collect_findings(self, results: dict) -> list[dict]:
        """Gather findings produced by every phase into one list."""
        collected: list[dict] = []
        for phase_name, phase_data in results.items():
            if phase_name in ("findings", "summary", "report", "error"):
                continue
            if not isinstance(phase_data, dict):
                continue
            for key in ("findings",):
                for f in phase_data.get(key, []) or []:
                    if isinstance(f, dict) and f.get("status") != "candidate":
                        collected.append(f)
        # De-duplicate by title+url
        seen = set()
        unique = []
        for f in collected:
            sig = (f.get("title", ""), f.get("url", ""))
            if sig in seen:
                continue
            seen.add(sig)
            unique.append(f)
        return unique

    def _build_summary(self, target: str, findings: list[dict], results: dict) -> dict:
        by_sev = dict.fromkeys(["critical", "high", "medium", "low", "info"], 0)
        for f in findings:
            sev = (f.get("severity") or "info").lower()
            if sev in by_sev:
                by_sev[sev] += 1
        dynamic = results.get("dynamic", {}) or {}
        return {
            "target": target,
            "total_findings": len(findings),
            "by_severity": by_sev,
            "tests_executed": dynamic.get("tests_executed", 0),
            "status": "completed",
        }

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


    async def get_findings_report(self, engagement_id: str, tenant_id: str | None = None) -> dict:
        """Get all verified findings for reporting, scoped by tenant_id."""
        findings = await self.memory.find_findings(
            engagement_id,
            status=FindingStatus.VERIFIED,
            tenant_id=tenant_id,
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
            "generated_at": datetime.now(UTC).isoformat(),
        }

    async def prepare_bug_bounty_reports(
        self, engagement_id: str, platform: str = "hackerone",
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Render every VERIFIED finding into a platform-ready draft report.

        This wires the (previously dead) BugBountyClient into the engagement
        pipeline: verified findings no longer sit idle in graph memory, they
        become submission-ready reports. Returns the reports without submitting
        them anywhere ??? submission to HackerOne/Bugcrowd still requires API
        keys and an explicit operator action.
        """
        report = await self.get_findings_report(engagement_id, tenant_id=tenant_id)
        findings = report.get("findings", [])

        client = self.bug_bounty_client
        if client is None:
            from sonic.integrations.bugbounty import BugBountyClient
            client = BugBountyClient()

        drafts = []
        for finding in findings:
            try:
                drafts.append(client.format_report(finding, platform=platform))
            except Exception as e:
                logger.warning("bugbounty_report_failed", finding=finding.get("uid", ""), error=str(e))

        logger.info(
            "bugbounty_reports_prepared",
            engagement_id=engagement_id, verified=len(findings), drafts=len(drafts),
        )
        return {
            "engagement_id": engagement_id,
            "platform": platform,
            "total_verified": len(findings),
            "draft_reports": [
                {
                    "title": d.title,
                    "severity": d.severity,
                    "vulnerability_type": d.vulnerability_type,
                    "description": d.description,
                    "poc": d.poc,
                }
                for d in drafts
            ],
        }

    def list_agents(self) -> list[dict]:
        """List all agents and their status."""
        return [agent.get_status() for agent in self.agents.values()]

    async def kill_all(self, tenant_id: str | None = None) -> dict:
        """Emergency stop, optionally restricted to one tenant."""
        for agent in self.agents.values():
            if tenant_id is None or getattr(agent, "tenant_id", None) == tenant_id:
                agent.status = "killed"

        for eng_id, eng in self.active_engagements.items():
            if (
                eng["status"] == EngagementStatus.RUNNING
                and (tenant_id is None or eng.get("tenant_id") == tenant_id)
            ):
                eng["status"] = EngagementStatus.FAILED
                await self.memory.update_engagement(eng_id, status=EngagementStatus.FAILED)

        logger.warning("kill_all_executed", agents=len(self.agents))
        return {"killed_agents": len(self.agents), "status": "all_stopped", "tenant_id": tenant_id}
