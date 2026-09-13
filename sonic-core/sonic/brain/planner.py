"""
SONIC v2 — Decoupled Research Brain, Planner & NEXUS L8 Temporal Stacking
========================================================================
Pure reasoning and hypothesis formulation engine.

Architectural Invariant:
The Research Brain has ZERO direct execution tools, shell handles, or sockets.
It does NOT execute commands or touch sandboxes. It consumes the World Model
and produces an ExperimentPlan for the Mission Kernel and Specialist Pool.

NEXUS L8 — Temporal Stacking / Cognitive Governor
-------------------------------------------------
Scales thinking depth by situation instead of running one uniform loop.
For every decision input, the governor selects a thinking tier:
    * reflex      — sub-millisecond mechanical (delegated to the native Rust kernel)
    * intuitive   — fast one-shot reasoning
    * deliberative — multi-step chain-of-thought
    * deep_research — hours-long autonomous cognition spawning sub-cognition loops
More compute = deeper thinking. The governor is deterministic and pure-reasoning.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sonic.brain.experiment import Experiment, ExperimentDesigner
from sonic.brain.hypothesis import Hypothesis, HypothesisEngine, HypothesisStatus
from sonic.brain.world_model import DynamicWorldModel


class ThinkingTier(StrEnum):
    REFLEX = "reflex"                     # sub-millisecond mechanical (native kernel)
    INTUITIVE = "intuitive"               # fast one-shot reasoning
    DELIBERATIVE = "deliberative"         # multi-step chain-of-thought
    DEEP_RESEARCH = "deep_research"       # hours-long autonomous cognition


@dataclass
class ThinkingTierDecision:
    """The cognitive governor's allocation of thinking depth for an input."""
    tier: ThinkingTier
    reason: str
    context_budget: int = 0
    sub_loops: int = 0
    max_reasoning_steps: int = 1
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier.value,
            "reason": self.reason,
            "context_budget": self.context_budget,
            "sub_loops": self.sub_loops,
            "max_reasoning_steps": self.max_reasoning_steps,
            "timestamp": self.timestamp,
        }


class TemporalStackingGovernor:
    """Selects the appropriate cognitive tier for a situation.

    Pure, deterministic policy:
        * critical safety edge        -> REFLEX (native kernel pre-screen first)
        * low-uncertainty, low-stakes -> INTUITIVE
        * medium uncertainty          -> DELIBERATIVE
        * high uncertainty / high stakes / novel domain -> DEEP_RESEARCH
    """

    def __init__(self) -> None:
        self._decisions: list[ThinkingTierDecision] = []

    def decide(
        self,
        uncertainty: float = 0.0,
        stakes: float = 0.0,
        is_safety_edge: bool = False,
        novelty: float = 0.0,
        context_budget: int = 0,
    ) -> ThinkingTierDecision:
        if is_safety_edge:
            tier = ThinkingTier.REFLEX
            reason = "Safety-critical edge: delegate to native sub-millisecond pre-screen."
            sub_loops, steps = 0, 1
        elif novelty >= 0.8 or (uncertainty >= 0.7 and stakes >= 0.6):
            tier = ThinkingTier.DEEP_RESEARCH
            reason = "High uncertainty + high stakes or novel domain: deep-research cognition."
            sub_loops, steps = 6, 64
        elif uncertainty >= 0.4 or stakes >= 0.5:
            tier = ThinkingTier.DELIBERATIVE
            reason = "Moderate uncertainty/stakes: multi-step deliberative reasoning."
            sub_loops, steps = 2, 12
        else:
            tier = ThinkingTier.INTUITIVE
            reason = "Low uncertainty/stakes: fast one-shot reasoning."
            sub_loops, steps = 0, 1

        decision = ThinkingTierDecision(
            tier=tier, reason=reason, context_budget=context_budget,
            sub_loops=sub_loops, max_reasoning_steps=steps,
        )
        self._decisions.append(decision)
        return decision

    def decisions(self) -> list[ThinkingTierDecision]:
        return list(self._decisions)


@dataclass
class ExperimentPlan:
    """Action plan formulated by the Brain without executing tools."""
    plan_id: str
    selected_hypothesis: Hypothesis | None
    experiment: Experiment | None
    specialist_type: str
    rationale: str
    goal_satisfied: bool = False
    stopping_reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class ResearchBrain:
    """Pure reasoning unit for the AI Human Pentester."""

    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id

    def plan_next_step(
        self,
        world_model: DynamicWorldModel,
        budget_exhausted: bool = False,
    ) -> ExperimentPlan:
        """Evaluates world model state and plans the highest-value experiment.
        
        Pure function: Has NO access to tools or execution providers.
        """
        plan_id = f"plan-{uuid.uuid4().hex[:8]}"

        # 1. Check if budget exhausted or stop condition met
        if budget_exhausted:
            return ExperimentPlan(
                plan_id=plan_id,
                selected_hypothesis=None,
                experiment=None,
                specialist_type="none",
                rationale="Mission budget exhausted; terminating experiment generation.",
                goal_satisfied=True,
                stopping_reason="budget_exhausted",
            )

        # 2. Check if verified findings satisfy mission goal
        if len(world_model.verified_findings) >= 3:
            return ExperimentPlan(
                plan_id=plan_id,
                selected_hypothesis=None,
                experiment=None,
                specialist_type="none",
                rationale="Sufficient verified findings collected to demonstrate exploitability.",
                goal_satisfied=True,
                stopping_reason="sufficient_findings",
            )

        # 3. Formulate hypotheses from unresolved unknowns if none active
        active_hypotheses = world_model.hypotheses.rank_by_value()
        if not active_hypotheses:
            unknowns = world_model.unknowns.get_top_priority_unknowns(limit=1)
            if unknowns:
                unk = unknowns[0]
                h_prim, _ = world_model.hypotheses.create_hypothesis_pair(
                    statement=f"Exploit potential identified for unknown: {unk.description}",
                    vulnerability_class=unk.domain.value,
                    target_asset=world_model.target,
                    claim_type="vulnerability",
                    expected_information_gain=unk.priority,
                )
                active_hypotheses = [h_prim]
            else:
                # No remaining unknowns or hypotheses
                return ExperimentPlan(
                    plan_id=plan_id,
                    selected_hypothesis=None,
                    experiment=None,
                    specialist_type="none",
                    rationale="All unknowns resolved and active hypotheses evaluated.",
                    goal_satisfied=True,
                    stopping_reason="epistemic_saturation",
                )

        # 4. Select highest value hypothesis and design experiment
        chosen_hyp = active_hypotheses[0]
        experiment = world_model.designer.design_for_hypothesis(
            hypothesis=chosen_hyp,
            context={"target": world_model.target, "goal": world_model.goal},
        )

        return ExperimentPlan(
            plan_id=plan_id,
            selected_hypothesis=chosen_hyp,
            experiment=experiment,
            specialist_type=experiment.specialist_type,
            rationale=f"Selected highest information-gain hypothesis '{chosen_hyp.statement}' (gain={chosen_hyp.expected_information_gain}, uncertainty={chosen_hyp.uncertainty:.2f})",
            goal_satisfied=False,
        )
