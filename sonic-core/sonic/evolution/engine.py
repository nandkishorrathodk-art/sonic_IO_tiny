"""
SONIC v2 — Self-Evolution Engine
=================================
Central orchestrator for autonomous capability evolution, uniting:
1. Dynamic Strategy Adaptation (`DynamicStrategyEngine`)
2. Novel Method & Attack Hypothesis Synthesis (`MethodLab`)
3. Dynamic Tool Authoring & Confirmation (`ToolsmithLoop`)
4. Cross-Mission Procedural Learning (`LessonsLedger`)
5. Guarded Canary Pipeline (`EvolutionPipeline`)

USER DIRECTION:
"isko scripted puppet nahi banana hai, force mat karo koi bhi tool ke liye
yeh khud things develop karega."

The being is NOT a scripted puppet:
- It does not rely on static exploit libraries or hardcoded tool sequences.
- It analyzes target reality, derives tailored strategies, invents novel
  methods when blocked (e.g. 403 Forbidden, WAF blocks, filtered ports),
  and authors its own executable tools in the sandbox.
- All self-developed techniques are verified through empirical execution in
  the sandbox (no success-by-decree).
"""

from __future__ import annotations

from typing import Any

from sonic.evolution.codebase_evolver import CodebaseEvolver, EvolutionSummaryReport
from sonic.evolution.evolution_journal import EvolutionJournal
from sonic.evolution.goal_director import (
    EvolutionGoal,
    EvolutionGoalDirector,
    GoalCategory,
    GoalStatus,
)
from sonic.evolution.pipeline import EvolutionPipeline, EvolutionStage, ImprovementProposal
from sonic.evolution.strategy import (
    DynamicStrategyEngine,
    StrategicPosture,
    StrategyAdaptationPlan,
    TargetFeedbackSignal,
)
from sonic.evolution.version_tracker import VersionTracker
from sonic.logger import get_logger

logger = get_logger(__name__)

CORE_NORTH_STAR_GOAL = """
================================================================================
SONIC PRIMARY NORTH STAR MISSION & TRAINING DIRECTIVE (A-SEA)
================================================================================
1. Autonomous Mastery in CTF (Capture The Flag) Challenges:
   - Web Exploitation: SSRF, SQLi, Auth Bypass, IDOR, SSTI, Deserialization, Race Conditions.
   - Binary Exploitation & Pwn: Buffer Overflow, ROP, Format Strings, Heap, Shellcode.
   - Cryptography: Padding Oracles, Weak Primes, Keystream Reuse, PRNG flaws.
   - Forensics & PCAP: Memory Dumps, Network Captures, File Carving, Steganography.
   - Reverse Engineering: Ghidra, GDB, Decompilation, Unpacking, Patching.
2. Precision Desktop Application Control:
   - Operating Chromium, Burp Suite, Terminal, VS Code / code-server, Ghidra, and Linux GUI with high visual and semantic accuracy.
3. Fast Reaction & Sub-Second Latency Cadence:
   - Eliminating redundant polling, using native Rust perception and Cython graph traversal for fast reaction action.
4. Non-Puppet Empirical Verification:
   - No scripted puppet theater; no success-by-decree; all flags and exploits must be empirically confirmed in-sandbox.
5. Continuous Codebase Self-Evolution:
   - Continuously upgrading tools, agents, heuristics, and logic while respecting the tamper-evident safety envelope.
================================================================================
"""


class EvolutionEngine:
    """
    Coordinates closed-loop self-evolution, goal-driven upgrades,
    and target-driven strategy adaptation.
    """

    def __init__(
        self,
        pipeline: EvolutionPipeline | None = None,
        strategy_engine: DynamicStrategyEngine | None = None,
        method_lab: Any | None = None,
        toolsmith: Any | None = None,
        lessons_ledger: Any | None = None,
        codebase_evolver: CodebaseEvolver | None = None,
        version_tracker: VersionTracker | None = None,
        journal: EvolutionJournal | None = None,
        goal_director: EvolutionGoalDirector | None = None,
        north_star: str = CORE_NORTH_STAR_GOAL,
    ):
        self.north_star = north_star
        self.pipeline = pipeline if pipeline is not None else EvolutionPipeline()
        self.strategy_engine = (
            strategy_engine if strategy_engine is not None else DynamicStrategyEngine()
        )
        self.method_lab = method_lab
        self.toolsmith = toolsmith
        self.lessons_ledger = lessons_ledger
        self.codebase_evolver = (
            codebase_evolver
            if codebase_evolver is not None
            else CodebaseEvolver(lessons_ledger=self.lessons_ledger, pipeline=self.pipeline)
        )
        self.version_tracker = (
            version_tracker
            if version_tracker is not None
            else VersionTracker(repo_root=self.codebase_evolver.repo_root)
        )
        self.journal = (
            journal
            if journal is not None
            else EvolutionJournal(repo_root=self.codebase_evolver.repo_root)
        )
        self.goal_director = (
            goal_director
            if goal_director is not None
            else EvolutionGoalDirector(
                repo_root=self.codebase_evolver.repo_root,
                evolver=self.codebase_evolver,
                version_tracker=self.version_tracker,
                journal=self.journal,
                lessons_ledger=self.lessons_ledger,
            )
        )
        # NEXUS L∞ — recursive self-architecting intelligence loop. Lazy late
        # binding so the engine can be constructed without its layers present
        # (the loop self-instantiates defaults when run).
        self._recursive_intelligence: RecursiveIntelligenceLoop | None = None

    def intellect(self) -> "RecursiveIntelligenceLoop":
        """Access (and lazily instantiate) the recursive intelligence loop —
        the being's self-improvement-of-improvement surface.

        The loop is armed with the guarded CodebaseEvolver so the SelfDeveloper
        pillar can perform real, parliament-gated codebase evolution — not just
        substrate weight mutations.
        """
        if self._recursive_intelligence is None:
            self._recursive_intelligence = RecursiveIntelligenceLoop(
                codebase_evolver=self.codebase_evolver,
            )
        return self._recursive_intelligence

    async def handle_target_failure(
        self,
        raw_output: str,
        exit_code: int = 0,
        target: str = "",
        current_approach: str = "",
        goal: str = "",
        provider: Any | None = None,
        workspace_id: str = "",
    ) -> dict[str, Any]:
        """
        Handle target failure autonomously without human script intervention:
        1. Classifies target response (403, WAF, filtered port, rate limit).
        2. Formulates an adapted strategic plan (avoid directives, mutated posture).
        3. If novel method warranted and MethodLab available:
           Synthesizes a novel attack hypothesis tailored to the target,
           empirically tests it in the sandbox, and registers it if confirmed.
        4. Persists the lesson into LessonsLedger so past failures are never repeated.
        """
        # 1. Adapt strategy from feedback
        plan: StrategyAdaptationPlan = self.strategy_engine.evolve_on_failure(
            tool=current_approach,
            raw_output=raw_output,
            exit_code=exit_code,
            target=target,
            goal=goal,
            lessons_ledger=self.lessons_ledger,
        )

        result: dict[str, Any] = {
            "signal": plan.signal.value,
            "posture": plan.posture.value,
            "rationale": plan.rationale,
            "action_mutation": plan.action_mutation,
            "avoid_directive": plan.avoid_directive,
            "suggested_actions": plan.suggested_actions,
            "invented_technique": None,
            "technique_confirmed": False,
        }

        # 2. Autonomous development: synthesize novel method tailored to target
        if plan.synthesize_novel_method and self.method_lab is not None:
            try:
                technique = await self.method_lab.invent(
                    observation=raw_output or f"Target {target} in posture {plan.posture.value}",
                    failure=current_approach,
                )
                if technique is not None:
                    result["invented_technique"] = {
                        "id": technique.technique_id,
                        "name": technique.name,
                        "family": technique.family,
                        "hypothesis": technique.hypothesis,
                    }
                    if provider is not None and workspace_id:
                        confirmed = await self.method_lab.confirm(
                            technique=technique,
                            provider=provider,
                            workspace_id=workspace_id,
                            target=target,
                        )
                        result["technique_confirmed"] = confirmed.confirmed
                        result["findings"] = confirmed.findings
            except Exception as e:
                logger.warning("evolution_engine_method_invention_failed", error=str(e))

        return result

    def submit_code_improvement(
        self,
        target_component: str,
        description: str,
        code_diff: str,
    ) -> tuple[ImprovementProposal, str]:
        """
        Submits a self-improvement proposal into the guarded canary pipeline.
        Enforces safety immutability: the agent can NEVER modify the safety kernel.
        """
        return self.pipeline.submit_proposal(
            target_component=target_component,
            description=description,
            code_diff=code_diff,
        )

    def evolve_codebase(
        self,
        target_component: str,
        description: str,
        code_diff: str,
        auto_promote: bool = True,
        push: bool = False,
        test_paths: list[str] | None = None,
    ) -> EvolutionSummaryReport:
        """
        Executes end-to-end continuous codebase self-evolution:
        1. Enforces safety envelope immutability (blocks modifications to safety kernel).
        2. Validates AST / syntax pre-flight.
        3. Staged patch application with zero-corrupt atomic rollback snapshot.
        4. Runs component unit tests & security regression suite.
        5. Auto-promotes (git commit + optional git push) without human approval if tests pass 100%.
        6. Generates and returns a structured EvolutionSummaryReport.
        """
        return self.codebase_evolver.evolve(
            target_component=target_component,
            description=description,
            code_diff=code_diff,
            auto_promote=auto_promote,
            push=push,
            test_paths=test_paths,
        )

    def submit_evolution_goal(
        self,
        title: str,
        description: str,
        priority: int = 2,
        category: GoalCategory | str = GoalCategory.LOGIC_IMPROVEMENT,
        target_files: list[str] | None = None,
        max_attempts: int = 3,
    ) -> EvolutionGoal:
        """Enqueues a high-level goal into the autonomous evolution queue."""
        return self.goal_director.submit_goal(
            title=title,
            description=description,
            priority=priority,
            category=category,
            target_files=target_files,
            max_attempts=max_attempts,
        )

    def execute_evolution_goal(
        self,
        goal_id: str,
        custom_patch: str | None = None,
        auto_promote: bool = True,
        push: bool = False,
        test_paths: list[str] | None = None,
    ) -> EvolutionSummaryReport:
        """Executes an enqueued evolution goal through analysis, tests, and version bump."""
        return self.goal_director.execute_goal(
            goal_id=goal_id,
            custom_patch=custom_patch,
            auto_promote=auto_promote,
            push=push,
            test_paths=test_paths,
        )

    def run_evolution_queue(
        self,
        max_goals: int | None = None,
        push: bool = False,
    ) -> list[EvolutionSummaryReport]:
        """Runs the continuous evolution loop, draining queued goals in priority order."""
        return self.goal_director.run_continuous(max_goals=max_goals, push=push)

    def get_evolution_status(self) -> dict[str, Any]:
        """Returns comprehensive status of current version, queue depth, and journal metrics."""
        return {
            "current_version": self.version_tracker.current_version(),
            "queued_goals": len(self.goal_director.list_goals(status=GoalStatus.QUEUED)),
            "fitness_metrics": self.journal.fitness_metrics(),
            "evolution_md_path": str(self.journal.evolution_md_path),
        }




# ---------------------------------------------------------------------------
# NEXUS L∞ -- Recursive Intelligence Loop (self-improvement self-architecting)
# ---------------------------------------------------------------------------

class RecursiveIntelligenceLoop:
    """The closing loop of the NEXUS substrate: cognition that improves its own
    architecture.

    Each generation:
        1. ingests event-bus frontier + current champion substrate variant
        2. consults the temporal governor for thinking depth allocation
        3. convenes the parliament to approve the next strategic motion
        4. rolls the world twin forward to weigh expected information gain
        5. gates the resulting action through the risk portfolio governor
        6. produces a NEW substrate variant (offspring) by mutating the
           champion's layer weights -- the self-architecting step
        7. records growth metrics + curriculum signal from the cycle

    The offspring is NOT adopted blindly: the SubstrateSearchLab benchmark
    must score it above the champion before promotion. This is improvement of
    the improve-set itself -- the being composes its own next mind, measured
    empirically, never by decree.
    """

    def __init__(
        self,
        parliament: Any | None = None,
        world_twin: Any | None = None,
        abstraction: Any | None = None,
        substrate: Any | None = None,
        curriculum: Any | None = None,
        offense_generator: Any | None = None,
        arena: Any | None = None,
        event_bus: Any | None = None,
        risk_governor: Any | None = None,
        temporal_governor: Any | None = None,
        growth_tracker: Any | None = None,
        codebase_evolver: Any | None = None,
        generation_label: str = "G0",
    ) -> None:
        # Lazy imports keep the loop dependency-free when layers are absent.
        from sonic.brain.decision import MultiMindParliament
        from sonic.brain.planner import TemporalStackingGovernor
        from sonic.brain.world_model import CrossDomainAbstractionGraph, WorldTwin
        from sonic.meta.benchmark import CapabilityGrowthTracker, SubstrateSearchLab
        from sonic.being.lessons import SelfCurriculum
        from sonic.being.method_lab import AdversarialArena, OffenseGenerator
        from sonic.being.life_loop import EventBus
        from sonic.safety.action_policy import RiskPortfolioGovernor

        self.parliament = parliament if parliament is not None else MultiMindParliament()
        self.world_twin = world_twin if world_twin is not None else WorldTwin()
        self.abstraction = abstraction if abstraction is not None else CrossDomainAbstractionGraph()
        self.substrate = substrate if substrate is not None else SubstrateSearchLab()
        self.curriculum = curriculum if curriculum is not None else SelfCurriculum()
        self.offense_generator = offense_generator if offense_generator is not None else OffenseGenerator()
        self.arena = arena if arena is not None else AdversarialArena()
        self.event_bus = event_bus if event_bus is not None else EventBus()
        self.risk_governor = risk_governor if risk_governor is not None else RiskPortfolioGovernor()
        self.temporal = temporal_governor if temporal_governor is not None else TemporalStackingGovernor()
        self.growth = growth_tracker if growth_tracker is not None else CapabilityGrowthTracker()
        # SelfDeveloper pillar: real codebase evolution gated by parliament +
        # risk governor. None = the loop breeds substrate variants only (the
        # default in tests / headless boots, preserving existing behavior).
        self.codebase_evolver = codebase_evolver

        self.generation = generation_label
        self.cycle_count = 0
        self.cycles: list[dict[str, Any]] = []

    def run_cycle(self, motion: str = "advance_research", context: str = "") -> dict[str, Any]:
        """Run one self-improvement generation cycle."""
        self.cycle_count += 1

        # 0. Look at what's alive on the bus right now.
        frontier_topics = self.event_bus.frontier_topics()

        # 1. Temporal governor decides how deep to think about this.
        uncertainty = 0.3 + (0.1 * (self.cycle_count % 5))
        depth = self.temporal.decide(
            uncertainty=uncertainty,
            stakes=0.4 if self.cycle_count % 2 else 0.6,
            novelty=0.2 + (0.1 * (self.cycle_count % 4)),
        )

        # 2. Parliament vets the proposed motion for this generation.
        decision = self.parliament.convene(
            proposal=f"generation-{self.generation}-cycle-{self.cycle_count}",
            motion=motion,
            context=context or f"bus:{','.join(frontier_topics) or 'idle'}",
        )

        # 3. World twin: estimate info gain if we push the motion forward.
        plan = self.world_twin.roll_forward([motion, "verify"], from_state="start")
        info_gain = plan.expected_info_gain

        # 4. Risk governor gates the action portfolio for this generation.
        risk = self.risk_governor.assess(
            action=f"{self.generation}:{motion}",
            severity="medium" if decision.outcome == "approve" else "low",
        )

        # 5. Self-architecturing offspring: mutate the champion's layer weights.
        offspring = self._breed_next_substrate()

        # 5.5 SelfDeveloper pillar: when parliament approves AND the risk
        # governor allows, actually evolve a real code component (with its own
        # safety-invariant, AST, unit-test, and security-regression gates).
        # auto_promote=False keeps operator approval in the loop — the being
        # cannot promote its own code changes by decree.
        evolution_report = self._maybe_evolve_codebase(
            motion=motion,
            decision=decision,
            risk=risk,
        )

        # 6. Generate fresh offense hypotheses + run a self-play arena round.
        fresh_hypotheses = self.offense_generator.generate(limit=2, families=["auth_bypass", "crypto_flaw"])
        arena_round = self.arena.play_round(
            attack_technique=f"novel chained {motion} hypothesis",
            defense_model="segmentation canary rate-limit allowlist",
        )

        # 7. Growth metrics + curriculum signal.
        approved = float(decision.outcome == "approve")
        self.growth.record_cycle(approved + (0.05 * info_gain), "self")
        if decision.outcome == "approve" and offspring is not None:
            self.curriculum.record(
                action=f"{motion} (gen {self.generation})",
                rationale=decision.dissent_record[0]["rationale"]
                if decision.dissent_record
                else decision.votes and decision.votes[0].rationale or "approved by parliament",
                outcome=f"offspring substrate {offspring.name} bred",
                status="verified",
                domain="self_improvement",
            )

        dedup_skip = evolution_report is False  # no evolver wired -> no report field
        cycle_record = {
            "generation": self.generation,
            "cycle": self.cycle_count,
            "tier": depth.tier.value,
            "parliament_outcome": decision.outcome,
            "consensus": decision.consensus_credibility,
            "info_gain": round(info_gain, 4),
            "risk_allowed": risk.allowed,
            "offspring": offspring.to_dict() if offspring else None,
            "arena_signal": arena_round.counterfactual_signal,
            "fresh_hypotheses": len(fresh_hypotheses),
        }
        if not dedup_skip and evolution_report is not None:
            if isinstance(evolution_report, dict):
                cycle_record["codebase_evolution"] = dict(evolution_report)
            elif hasattr(evolution_report, "to_dict"):
                cycle_record["codebase_evolution"] = evolution_report.to_dict()
            elif isinstance(evolution_report, str):
                cycle_record["codebase_evolution"] = {"report": evolution_report}
            else:
                try:
                    cycle_record["codebase_evolution"] = vars(evolution_report)
                except TypeError:
                    cycle_record["codebase_evolution"] = {"report": str(evolution_report)}
        self.cycles.append(cycle_record)

        # Advance the being's generation label after each cycle so the next
        # generation self-architects from a slightly evolved platform.
        self.generation = f"G{self.cycle_count}"
        return cycle_record

    def _breed_next_substrate(self) -> Any | None:
        """Construct an offspring substrate variant by mutating the current
        champion's layer weights. The offspring must outscore the champion in
        the SubstrateSearchLab benchmark before it is adopted."""
        champion = self.substrate.champion()
        if champion is None:
            return None

        layers = dict(champion.layers)
        # deterministic small mutation upward/downward around the champion
        for layer, weight in layers.items():
            delta = 0.05 * (1 if (self.cycle_count + len(layer)) % 2 else -1)
            layers[layer] = max(0.0, round(weight + delta, 3))

        offspring = self.substrate.register_variant(
            name=f"offspring-{self.generation}",
            layers=layers,
            rationale=f"Mutated from champion '{champion.name}' at generation {self.generation}.",
        )
        promoted = self.substrate.promote_if_better()
        return offspring if promoted is not None else champion

    def _maybe_evolve_codebase(
        self,
        motion: str,
        decision: Any,
        risk: Any,
        target_component: str = "",
        code_diff: str = "",
    ) -> Any | None | bool:
        """SelfDeveloper pillar: evolve a real component when the parliament
        approves the motion, the risk governor allows the draw, and a guarded
        CodebaseEvolver has been wired in.

        When `code_diff` is empty, the write path is NOT executed — the intent
        is recorded only (returning the gate decision dict). This keeps the
        loop honest: it never fabricates or truncates code it doesn't have; a
        real diff is produced upstream (LLM/offense generator) and injected.

        Returns the EvolutionSummaryReport from the guarded evolve() call,
        a gate-decision dict, None when the gates block it, or False when no
        evolver is wired (callers use that to drop the report field).
        """
        if self.codebase_evolver is None:
            return False
        if decision.outcome != "approve" or not risk.allowed:
            logger.info(
                "selfdev_skipped",
                parliament=decision.outcome,
                risk_allowed=risk.allowed,
                reason="parliament/risk gate not satisfied",
            )
            return None
        if not code_diff:
            return {
                "gate": "approved",
                "action": "propose_only",
                "target_component": target_component or "none",
                "reason": "no code_diff supplied; write path skipped (no fabrication)",
            }
        try:
            # auto_promote=False: promotion still requires the operator
            # (EvolutionPipeline.promote_with_approval).
            report = self.codebase_evolver.evolve(
                target_component=target_component,
                description=f"NEXUS generation {self.generation}: self-improvement for '{motion}'.",
                code_diff=code_diff,
                auto_promote=False,
                push=False,
            )
            return report
        except Exception as e:
            logger.warning("selfdev_evolve_failed", generation=self.generation, error=str(e))
            return None

    def status(self) -> dict[str, Any]:
        """Human-readable status of the recursive cognition loop."""
        return {
            "generation": self.generation,
            "cycles_completed": self.cycle_count,
            "growth": self.growth.summary(),
            "arena_rounds": self.arena.round_count(),
            "parliament_decision_log": self.parliament.list_decisions(limit=3),
            "last_cycle": self.cycles[-1] if self.cycles else None,
        }