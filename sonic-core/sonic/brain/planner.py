"""
SONIC v2 — Decoupled Research Brain & Planner
=============================================
Pure reasoning and hypothesis formulation engine.

Architectural Invariant:
The Research Brain has ZERO direct execution tools, shell handles, or sockets.
It does NOT execute commands or touch sandboxes. It consumes the World Model
and produces an ExperimentPlan for the Mission Kernel and Specialist Pool.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sonic.brain.experiment import Experiment, ExperimentDesigner
from sonic.brain.hypothesis import Hypothesis, HypothesisEngine, HypothesisStatus
from sonic.brain.world_model import DynamicWorldModel


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
