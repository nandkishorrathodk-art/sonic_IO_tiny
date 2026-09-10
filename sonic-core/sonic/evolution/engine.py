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

from sonic.evolution.pipeline import EvolutionPipeline, EvolutionStage, ImprovementProposal
from sonic.evolution.strategy import (
    DynamicStrategyEngine,
    StrategicPosture,
    StrategyAdaptationPlan,
    TargetFeedbackSignal,
)
from sonic.logger import get_logger

logger = get_logger(__name__)


class EvolutionEngine:
    """
    Coordinates closed-loop self-evolution and target-driven strategy adaptation.
    """

    def __init__(
        self,
        pipeline: EvolutionPipeline | None = None,
        strategy_engine: DynamicStrategyEngine | None = None,
        method_lab: Any | None = None,
        toolsmith: Any | None = None,
        lessons_ledger: Any | None = None,
    ):
        self.pipeline = pipeline if pipeline is not None else EvolutionPipeline()
        self.strategy_engine = (
            strategy_engine if strategy_engine is not None else DynamicStrategyEngine()
        )
        self.method_lab = method_lab
        self.toolsmith = toolsmith
        self.lessons_ledger = lessons_ledger

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

