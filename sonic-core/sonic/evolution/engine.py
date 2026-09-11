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



