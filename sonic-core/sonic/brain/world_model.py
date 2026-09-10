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
        metadata: dict[str, Any] | None = None,
        access_rules: list[str] | None = None,
    ) -> ResourceNode:
        node = ResourceNode(
            resource_id=resource_id,
            uri=uri,
            resource_type=resource_type,
            current_state=current_state,
            sensitive=sensitive,
            metadata=metadata or {},
            access_rules=access_rules or [],
        )
        self.resources[resource_id] = node
        return node

    def ingest_asset(self, asset_data: dict[str, Any]) -> ResourceNode:
        """Ingest a directly observed target asset into the world model.
        
        Maps observed recon assets (URLs, subdomains, open ports, technologies,
        certificates, DNS records) into verified ResourceNodes with honest
        provenance, without depending on pre-canned scanner output.
        """
        asset_type = asset_data.get("type", "endpoint")
        value = str(asset_data.get("value", ""))
        name = asset_data.get("name", "")
        meta = dict(asset_data.get("metadata", {}) or {})
        
        type_mapping = {
            "url": "endpoint",
            "endpoint": "endpoint",
            "subdomain": "subdomain",
            "domain": "subdomain",
            "technology": "technology",
            "port": "service",
            "service": "service",
            "certificate": "certificate",
            "ip_address": "infrastructure",
            "dns_record": "infrastructure",
            "security_header": "security_posture",
        }
        resource_type = type_mapping.get(asset_type, asset_type)
        
        resource_id = asset_data.get("resource_id")
        if not resource_id:
            safe_val = value.replace("://", "_").replace("/", "_").replace(":", "_").strip("_")
            resource_id = f"{resource_type}_{safe_val}" if safe_val else f"{resource_type}_{len(self.resources) + 1}"
        
        is_sensitive = bool(meta.get("sensitive", False))
        val_lower = value.lower()
        if any(keyword in val_lower for keyword in ("admin", "secret", "backup", "internal", "metrics", "swagger", "openapi", ".env", ".git")):
            is_sensitive = True

        access_rules = list(meta.get("access_rules", []))
        if meta.get("disallowed_by_robots"):
            access_rules.append("disallowed_by_robots")
        if meta.get("auth_required"):
            access_rules.append("auth_required")

        if name and "name" not in meta:
            meta["name"] = name

        return self.register_resource(
            resource_id=resource_id,
            uri=value,
            resource_type=resource_type,
            current_state="discovered",
            sensitive=is_sensitive,
            metadata=meta,
            access_rules=access_rules,
        )

    def ingest_recon_assets(self, assets: list[dict[str, Any]]) -> list[ResourceNode]:
        """Batch ingest discovered target assets into the world model."""
        nodes: list[ResourceNode] = []
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            node = self.ingest_asset(asset)
            nodes.append(node)
        return nodes

    def get_attack_surface(self) -> dict[str, list[ResourceNode]]:
        """Categorize all discovered resources by surface dimension."""
        surface: dict[str, list[ResourceNode]] = {
            "endpoints": [],
            "services": [],
            "subdomains": [],
            "technologies": [],
            "certificates": [],
            "infrastructure": [],
            "security_posture": [],
            "other": [],
        }
        category_map = {
            "endpoint": "endpoints",
            "url": "endpoints",
            "subdomain": "subdomains",
            "domain": "subdomains",
            "technology": "technologies",
            "service": "services",
            "port": "services",
            "certificate": "certificates",
            "infrastructure": "infrastructure",
            "ip_address": "infrastructure",
            "dns_record": "infrastructure",
            "security_posture": "security_posture",
            "security_header": "security_posture",
        }
        for res in self.resources.values():
            cat = category_map.get(res.resource_type, "other")
            surface[cat].append(res)
        return surface

    def update_target_profile(self, profile_data: dict[str, Any]) -> None:
        """Update the live target profile (DNS, open ports, TLS, server details)."""
        if not hasattr(self, "target_profile"):
            self.target_profile: dict[str, Any] = {}
        self.target_profile.update(profile_data)

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
        """Provides a high-level cognitive snapshot with attack surface breakdown."""
        target_prof = getattr(self, "target_profile", {})
        surface = self.get_attack_surface()
        return {
            "target": self.target,
            "goal": self.goal,
            "actors_count": len(self.actors),
            "resources_count": len(self.resources),
            "endpoints_count": len(surface["endpoints"]),
            "services_count": len(surface["services"]),
            "technologies_count": len(surface["technologies"]),
            "confirmed_assets_count": sum(
                1 for r in self.resources.values() if r.metadata.get("confirmed", True) is not False
            ),
            "transitions_count": len(self.transitions),
            "unresolved_unknowns": len(self.unknowns.get_unresolved()),
            "active_hypotheses": len(self.hypotheses.get_active()),
            "verified_findings_count": len(self.verified_findings),
            "target_profile": target_prof,
        }
