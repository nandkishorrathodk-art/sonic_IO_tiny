"""
SONIC v2 — Dynamic World Model
===============================
The cognitive core of the AI Human Pentester.
Maintains continuous situational awareness of actors, permissions,
resources, states, transitions, active unknowns, and competing hypotheses.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from sonic.brain.decision import DecisionEngine
from sonic.brain.experiment import ExperimentDesigner
from sonic.brain.falsifier import FalsificationJudge
from sonic.brain.hypothesis import Hypothesis, HypothesisEngine, HypothesisStatus
from sonic.brain.unknowns import UnknownEntity, UnknownTracker


class ActorNode(BaseModel):
    """An identity, role, or security principal in the target environment."""
    actor_id: str
    role: str = "anonymous"  # "anonymous", "low_priv", "admin", "service"
    privilege_level: int = 0  # 0: public, 1: user, 2: manager, 3: admin
    tokens: dict[str, str] = Field(default_factory=dict)
    known_permissions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResourceNode(BaseModel):
    """A target asset, endpoint, object, or system component."""
    resource_id: str
    uri: str
    resource_type: str = "endpoint"  # "endpoint", "database", "object", "service"
    current_state: str = "discovered"
    access_rules: list[str] = Field(default_factory=list)
    sensitive: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class StateTransition(BaseModel):
    """Observed state progression resulting from an action."""
    source_state: str
    target_state: str
    action_taken: str
    actor_id: str
    resource_id: str
    side_effects: list[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class DynamicWorldModel:
    """The central state and reasoning fabric for the Central Research Brain."""

    def __init__(
        self,
        tenant_id: str = "default",
        target: str = "",
        goal: str = "",
    ):
        self.tenant_id = tenant_id
        self.target = target
        self.goal = goal

        # Subsystems
        self.unknowns = UnknownTracker()
        self.hypotheses = HypothesisEngine()
        self.decisions = DecisionEngine()
        self.falsifier = FalsificationJudge(self.hypotheses)
        self.designer = ExperimentDesigner()

        # Topological Entities
        self.actors: dict[str, ActorNode] = {}
        self.resources: dict[str, ResourceNode] = {}
        self.transitions: list[StateTransition] = []
        self.verified_findings: list[dict[str, Any]] = []

    def register_actor(
        self,
        actor_id: str,
        role: str = "anonymous",
        privilege_level: int = 0,
        tokens: dict[str, str] | None = None,
        permissions: list[str] | None = None,
    ) -> ActorNode:
        node = ActorNode(
            actor_id=actor_id,
            role=role,
            privilege_level=privilege_level,
            tokens=tokens or {},
            known_permissions=permissions or [],
        )
        self.actors[actor_id] = node
        return node

    def register_resource(
        self,
        resource_id: str,
        uri: str,
        resource_type: str = "endpoint",
        current_state: str = "discovered",
        sensitive: bool = False,
    ) -> ResourceNode:
        node = ResourceNode(
            resource_id=resource_id,
            uri=uri,
            resource_type=resource_type,
            current_state=current_state,
            sensitive=sensitive,
        )
        self.resources[resource_id] = node
        return node

    def record_transition(
        self,
        source_state: str,
        target_state: str,
        action_taken: str,
        actor_id: str,
        resource_id: str,
        side_effects: list[str] | None = None,
    ) -> StateTransition:
        t = StateTransition(
            source_state=source_state,
            target_state=target_state,
            action_taken=action_taken,
            actor_id=actor_id,
            resource_id=resource_id,
            side_effects=side_effects or [],
        )
        self.transitions.append(t)
        if resource_id in self.resources:
            self.resources[resource_id].current_state = target_state
        return t

    def get_summary(self) -> dict[str, Any]:
        """Provides a high-level cognitive snapshot."""
        return {
            "target": self.target,
            "goal": self.goal,
            "actors_count": len(self.actors),
            "resources_count": len(self.resources),
            "transitions_count": len(self.transitions),
            "unresolved_unknowns": len(self.unknowns.get_unresolved()),
            "active_hypotheses": len(self.hypotheses.get_active()),
            "verified_findings_count": len(self.verified_findings),
        }
