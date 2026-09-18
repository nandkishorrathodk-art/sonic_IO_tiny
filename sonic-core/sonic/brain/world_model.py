"""
SONIC v2 — Dynamic World Model + NEXUS L3 World-Twin + L4 Cross-Domain Abstraction
==================================================================================
The cognitive core of the AI Human Pentester.
Maintains continuous situational awareness of actors, permissions,
resources, states, transitions, active unknowns, and competing hypotheses.

NEXUS L3 — Predictive World-Twin
--------------------------------
Replaces pure observe→react with model-based cognition. Each target is mirrored
as a digitized state-machine twin (endpoints, transitions, auth boundaries,
timing). `roll_forward()` simulates a planned action sequence and returns the
expected information gain, cost, and projected states — the agent "thinks
against its own simulation before touching reality." Predictions are explicitly
labeled `predicted` and carry observation-depth confidence.

NEXUS L4 — Cross-Domain Abstraction Graph
-----------------------------------------
Lifts domain-specific techniques into higher-order abstract concepts (e.g.
crypto:side_channel ≡ web:timing_attack ≡ web:race_condition), then computes
cross-domain transfer suggestions so a technique known in one domain transfers
to another sharing the same concept. Nothing is invented: the seed mapping is
explicit prior art; new techniques must be registered by evidence-producing
callers.

Both layers are pure reasoning/store — zero tool handles and zero live infra.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from sonic.brain.decision import DecisionEngine
from sonic.brain.experiment import ExperimentDesigner
from sonic.brain.falsifier import FalsificationJudge
from sonic.brain.hypothesis import HypothesisEngine
from sonic.brain.unknowns import UnknownTracker
from sonic.logger import get_logger

logger = get_logger(__name__)


def _world_db_path() -> str:
    from sonic.memory.sqlite_graph import _default_db_path as _g
    return os.environ.get("SONIC_WORLD_DB_PATH") or os.environ.get("SONIC_MEMORY_DB_PATH") or _g()


def _now() -> str:
    return datetime.now(UTC).isoformat()


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

# ---------------------------------------------------------------------------
# NEXUS L3 -- Predictive World-Twin
# ---------------------------------------------------------------------------

@dataclass
class TwinState:
    """A node (state/endpoint) in the world twin."""
    state_id: str
    uri: str = ""
    state_type: str = "endpoint"        # endpoint | auth_boundary | resource | service
    observed_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TwinTransition:
    """An observed or simulated edge between twin states."""
    from_state: str
    to_state: str
    action: str
    observed_count: int = 0
    success_rate: float = 1.0
    mean_latency_ms: float = 0.0
    info_gain: float = 0.0


@dataclass
class RollForwardResult:
    """Prediction of executing a planned action sequence against the twin."""
    plan_id: str
    actions: list[str]
    expected_info_gain: float
    expected_cost: float
    projected_states: list[str]
    confidence: float
    predicted: bool = True
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "actions": self.actions,
            "expected_info_gain": self.expected_info_gain,
            "expected_cost": self.expected_cost,
            "projected_states": self.projected_states,
            "confidence": self.confidence,
            "predicted": self.predicted,
            "timestamp": self.timestamp,
        }


class WorldTwin:
    """A persistent, evidence-derived digital twin of the target.

    Methods:
        observe_state / observe_transition: feed real observed events in.
        roll_forward(actions): simulate a plan, returning expected gain/cost.
        info_gain_of(actions): convenience ranking used by plan selection.

    The twin is honest: every node/edge is created from an observed event and
    roll_forward only simulates. Its predictions are labeled `predicted`.
    """

    _INFO_GAIN_PRIOR = 0.7          # smoothing prior for limited observations
    _LATENCY_PENALTY = 0.01         # ms -> normalized cost weight

    def __init__(self, target: str = "", twin_id: str | None = None, db_path: str | None = None) -> None:
        self.twin_id = twin_id or f"twin-{uuid.uuid4().hex[:12]}"
        self.target = target
        self.db_path = db_path or _world_db_path()
        self._states: dict[str, TwinState] = {}
        self._transitions: dict[tuple[str, str, str], TwinTransition] = {}
        self._init_db()
        self._hydrate()

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS twin_states (
                    twin_id TEXT, state_id TEXT, uri TEXT, state_type TEXT,
                    observed_count INTEGER, metadata_json TEXT,
                    PRIMARY KEY (twin_id, state_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS twin_transitions (
                    twin_id TEXT, from_state TEXT, to_state TEXT, action TEXT,
                    observed_count INTEGER, success_rate REAL, mean_latency_ms REAL,
                    info_gain REAL,
                    PRIMARY KEY (twin_id, from_state, to_state, action)
                )
                """
            )

    def _hydrate(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT twin_id, state_id, uri, state_type, observed_count, metadata_json "
                    "FROM twin_states WHERE twin_id = ?",
                    (self.twin_id,),
                ).fetchall()
                for _, sid, uri, stype, cnt, meta in rows:
                    self._states[sid] = TwinState(
                        state_id=sid, uri=uri or "", state_type=stype,
                        observed_count=cnt,
                        metadata=json.loads(meta) if meta else {},
                    )
                trows = conn.execute(
                    "SELECT from_state, to_state, action, observed_count, success_rate, "
                    "mean_latency_ms, info_gain FROM twin_transitions WHERE twin_id = ?",
                    (self.twin_id,),
                ).fetchall()
                for f, t, a, cnt, sr, lat, ig in trows:
                    self._transitions[(f, t, a)] = TwinTransition(
                        from_state=f, to_state=t, action=a,
                        observed_count=cnt, success_rate=sr,
                        mean_latency_ms=lat, info_gain=ig,
                    )
        except sqlite3.Error as e:
            logger.warning("twin_hydrate_failed", error=str(e))

    def observe_state(self, state_id: str, uri: str = "", state_type: str = "endpoint", metadata: dict[str, Any] | None = None) -> TwinState:
        existing = self._states.get(state_id)
        if existing:
            existing.observed_count += 1
            state = existing
        else:
            state = TwinState(state_id=state_id, uri=uri, state_type=state_type, observed_count=1)
            if metadata:
                state.metadata.update(metadata)
            self._states[state_id] = state
        self._write_state(state)
        return state

    def observe_transition(
        self,
        from_state: str,
        to_state: str,
        action: str,
        success: bool = True,
        latency_ms: float = 0.0,
        info_gain: float = 0.0,
    ) -> TwinTransition:
        """Record a REAL observed transition (probe response / trace step)."""
        key = (from_state, to_state, action)
        existing = self._transitions.get(key)
        if existing:
            n = existing.observed_count
            p = existing.success_rate
            existing.observed_count += 1
            existing.success_rate = (p * n + (1.0 if success else 0.0)) / (n + 1)
            existing.mean_latency_ms = (existing.mean_latency_ms * n + latency_ms) / (n + 1)
            existing.info_gain = max(existing.info_gain, info_gain)
            trans = existing
        else:
            trans = TwinTransition(
                from_state=from_state, to_state=to_state, action=action,
                observed_count=1, success_rate=1.0 if success else 0.0,
                mean_latency_ms=latency_ms, info_gain=info_gain,
            )
            self._transitions[key] = trans
        self._write_transition(trans)
        return trans

    def _edges_from(self, state_id: str) -> list[TwinTransition]:
        return [t for (f, _, _), t in self._transitions.items() if f == state_id]

    def roll_forward(self, actions: list[str], from_state: str = "") -> RollForwardResult:
        """Simulate executing `actions` against the twin's observed model.

        Deterministic; confidence scales with observation depth. The result is
        explicitly labeled `predicted`.

        Transition selection stays in Python (graph-aware). For long action
        sequences the gain/cost aggregation is offloaded to the native Rust
        NEXUS World-Twin scorer (nexus_world_twin_roll_forward) when the kernel
        binary is available; otherwise the same loop accumulates in Python.
        """
        cur = from_state or (list(self._states)[0] if self._states else "start")
        projected = [cur]
        depth = 0
        native_steps: list[dict[str, Any]] = []
        for action in actions:
            candidates = [t for t in self._edges_from(cur) if t.action == action]
            if not candidates:
                candidates = self._edges_from(cur)
            if candidates:
                trans = max(candidates, key=lambda t: t.info_gain)
                native_steps.append({
                    "action": action,
                    "expected_info_gain": float(self._info_gain_of(trans)),
                    "cost": float(self._cost_of(trans)),
                })
                depth += trans.observed_count
                cur = trans.to_state
            else:
                native_steps.append({
                    "action": action,
                    "expected_info_gain": 0.0,
                    "cost": 1.0,
                })
                cur = f"unknown-{action!r}"
            projected.append(cur)

        total_gain, total_cost = self._native_aggregate(native_steps)

        confidence = depth / (depth + self._INFO_GAIN_PRIOR) if depth else 0.0
        return RollForwardResult(
            plan_id=f"plan-{uuid.uuid4().hex[:10]}",
            actions=actions,
            expected_info_gain=total_gain,
            expected_cost=total_cost,
            projected_states=projected,
            confidence=confidence,
        )

    @staticmethod
    def _native_aggregate(steps: list[dict[str, Any]]) -> tuple[float, float]:
        """Aggregate (gain, cost) natively via the Rust NEXUS World-Twin scorer;
        fall back to a Python fold when the kernel binary is unavailable."""
        try:
            from sonic.kernel.native_bridge import NativeKernelClient
            client = NativeKernelClient()
            if client.is_available():
                res = client.nexus_world_twin_roll_forward(steps)
                if res and "total_gain" in res:
                    return float(res["total_gain"]), float(res["total_cost"])
        except Exception:
            logger.debug("native_world_twin_aggregate_unavailable", exc_info=True)

        return (
            sum(s.get("expected_info_gain", 0.0) for s in steps),
            sum(s.get("cost", 0.0) for s in steps),
        )

    def _info_gain_of(self, trans: TwinTransition) -> float:
        return trans.info_gain

    def _cost_of(self, trans: TwinTransition) -> float:
        return self._LATENCY_PENALTY * trans.mean_latency_ms + (0.0 if trans.success_rate > 0.5 else 1.0)

    def info_gain_of(self, actions: list[str], from_state: str = "") -> float:
        """Ranking helper: expected total info gain for an action sequence."""
        return self.roll_forward(actions, from_state).expected_info_gain

    def states(self) -> list[TwinState]:
        return list(self._states.values())

    def transition_count(self) -> int:
        return len(self._transitions)

    def _write_state(self, state: TwinState) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO twin_states VALUES (?,?,?,?,?,?)",
                    (
                        self.twin_id, state.state_id, state.uri, state.state_type,
                        state.observed_count, json.dumps(state.metadata),
                    ),
                )
        except sqlite3.Error as e:
            logger.warning("twin_state_write_failed", error=str(e))

    def _write_transition(self, trans: TwinTransition) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO twin_transitions VALUES (?,?,?,?,?,?,?,?)",
                    (
                        self.twin_id, trans.from_state, trans.to_state, trans.action,
                        trans.observed_count, trans.success_rate,
                        trans.mean_latency_ms, trans.info_gain,
                    ),
                )
        except sqlite3.Error as e:
            logger.warning("twin_transition_write_failed", error=str(e))


# ---------------------------------------------------------------------------
# NEXUS L4 -- Cross-Domain Abstraction Graph
# ---------------------------------------------------------------------------

# Canonical abstract concepts and the domain techniques that instantiate them.
# This is the *seed* of prior art -- never fabricated, always expandable via
# register_concept()/register_technique().
SEED_ABSTRACTIONS: dict[str, list[str]] = {
    "information_leakage_via_differential_response": [
        "crypto:side_channel",
        "web:timing_attack",
        "web:race_condition",
    ],
    "oracle_by_differential_behavior": [
        "crypto:padding_oracle",
        "web:boolean_blind_sqli",
        "web:ssti_boolean_probe",
    ],
    "state_reuse": [
        "crypto:keystream_reuse",
        "web:session_token_reuse",
        "pwn:heap_reuse",
    ],
    "untrusted_input_as_code": [
        "web:ssti",
        "pwn:format_string",
        "web:prototype_pollution",
        "web:deserialization",
        "api:mass_assignment",
    ],
    "boundary_escape": [
        "web:path_traversal",
        "pwn:buffer_overflow",
        "network:asn_hopping",
        "web:ssrf",
    ],
    "falsifiable_oracle": [
        "crypto:hashing_oracle",
        "web:auth_bypass_boolean",
    ],
}


@dataclass
class AbstractionConcept:
    """A higher-order concept that several domain techniques instantiate."""
    concept_id: str
    name: str
    description: str = ""
    techniques: list[str] = field(default_factory=list)
    transfer_score: float = 0.5


@dataclass
class TransferSuggestion:
    """A suggested cross-domain transfer between two techniques."""
    source_technique: str
    target_domain: str
    shared_concepts: list[str]
    transfer_score: float
    rationale: str


class CrossDomainAbstractionGraph:
    """Lifts domain techniques into shared concepts and computes transfers."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or _world_db_path()
        self._concepts: dict[str, AbstractionConcept] = {}
        self._technique_concepts: dict[str, list[str]] = defaultdict(list)
        self._init_db()
        self._hydrate()
        if not self._concepts:
            self._seed()

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS abstraction_concepts (
                    concept_id TEXT PRIMARY KEY,
                    name TEXT,
                    description TEXT,
                    techniques_json TEXT,
                    transfer_score REAL
                )
                """
            )

    def _hydrate(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT concept_id, name, description, techniques_json, transfer_score "
                    "FROM abstraction_concepts"
                ).fetchall()
            self._concepts = {}
            self._technique_concepts = defaultdict(list)
            for cid, name, desc, tjson, score in rows:
                techniques = json.loads(tjson) if tjson else []
                self._concepts[cid] = AbstractionConcept(
                    concept_id=cid, name=name, description=desc or "",
                    techniques=techniques, transfer_score=score,
                )
                for t in techniques:
                    self._technique_concepts[t].append(cid)
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.warning("abstraction_hydrate_failed", error=str(e))

    def _seed(self) -> None:
        for i, (name, techniques) in enumerate(SEED_ABSTRACTIONS.items(), start=1):
            self.register_concept(
                concept_id=f"concept-{i:02d}",
                name=name,
                description=name.replace("_", " "),
                techniques=techniques,
            )

    def register_concept(
        self,
        concept_id: str,
        name: str,
        description: str,
        techniques: list[str],
        transfer_score: float = 0.5,
    ) -> AbstractionConcept:
        concept = AbstractionConcept(
            concept_id=concept_id, name=name, description=description,
            techniques=techniques, transfer_score=transfer_score,
        )
        self._concepts[concept_id] = concept
        for t in techniques:
            self._technique_concepts[t].append(concept_id)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO abstraction_concepts VALUES (?,?,?,?,?)",
                (concept_id, name, description, json.dumps(techniques), transfer_score),
            )
        return concept

    def register_technique(self, technique: str, concept_ids: list[str]) -> None:
        """Attach a (potentially new, evidence-verified) technique to concepts."""
        for cid in concept_ids:
            concept = self._concepts.get(cid)
            if concept and technique not in concept.techniques:
                concept.techniques.append(technique)
                self._technique_concepts[technique].append(cid)
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "UPDATE abstraction_concepts SET techniques_json = ? WHERE concept_id = ?",
                        (json.dumps(concept.techniques), cid),
                    )

    def domain_of(self, technique: str) -> str:
        return technique.split(":", 1)[0] if ":" in technique else "unknown"

    def concepts_for(self, technique: str) -> list[str]:
        return list(self._technique_concepts.get(technique, []))

    def transfer_suggestions(self, technique: str) -> list[TransferSuggestion]:
        """For a known technique, find other-domain techniques sharing a concept."""
        concepts = self.concepts_for(technique)
        source_domain = self.domain_of(technique)
        scored: dict[str, tuple[list[str], float]] = {}
        for cid in concepts:
            concept = self._concepts.get(cid)
            if not concept:
                continue
            for other in concept.techniques:
                if other == technique or self.domain_of(other) == source_domain:
                    continue
                shared, cur_score = scored.get(other, ([], 0.0))
                new_shared = list(shared) + [cid]
                scored[other] = (new_shared, cur_score + concept.transfer_score)
        return [
            TransferSuggestion(
                source_technique=technique,
                target_domain=self.domain_of(other),
                shared_concepts=shared,
                transfer_score=min(1.0, score),
                rationale=f"Shares concept(s): {', '.join(shared)}",
            )
            for other, (shared, score) in scored.items()
        ]

    def highest_value_transfer(self, technique: str) -> TransferSuggestion | None:
        suggestions = self.transfer_suggestions(technique)
        return max(suggestions, key=lambda s: s.transfer_score) if suggestions else None

    def concept_count(self) -> int:
        return len(self._concepts)

    def technique_count(self) -> int:
        return len(self._technique_concepts)
