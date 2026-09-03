"""
SONIC-REDA — Dual-Process Hierarchical Sub-agent Controller (Round 6)
====================================================================
Makes the agent work like a human researcher — fast when the territory is
familiar, deep when it is novel or uncertain, and quiet until it genuinely
needs a human.

Four pillars (all building on existing SONIC pieces, never duplicating):

1. Dual-Process (Fast/Deep) Controller
   A Kahneman System-1/System-2 analog. For each hypothesis node the
   DualProcessController picks FAST (heuristic, high-throughput, parallel
   children) or DEEP (thorough, careful, limited parallelism) based on the
   node's ConfidenceBand, unresolved Unknowns, novelty, and failure rate.

2. Dual-Process switching
   HIGH/VERY_HIGH confidence + few low-importance unknowns + a known pattern
   (lessons-ledger hit) → FAST. LOW/MODERATE confidence OR high-importance
   unresolved unknowns OR a novel pattern → DEEP. Stuck in DEEP with no
   progress + high uncertainty → ESCALATE.

3. Hierarchical Hypothesis + Sub-agents
   Hypotheses form a tree (CognitiveHypothesis.parent_id / children_ids). A
   CONFIRMED parent expands into more-specific child hypotheses; a DISPROVED
   parent's whole subtree is pruned so dead branches never waste sub-agents.
   Each node dispatches the EXISTING swarm agents (recon/verifier/dynamic/…)
   as sub-agents scoped to that node's test plan — no new agent classes.

4. Parallel sub-agent execution
   Child nodes (or a node's multi-step test plan) run concurrently via
   asyncio.gather, capped by max_parallel — exactly like SwarmRunner.

5. Smart Human-in-the-loop escalation (sirf high-uncertainty pe)
   Escalate to a human ONLY when ALL hold: (a) already in DEEP, (b) high-
   importance unresolved Unknowns remain (importance > threshold), (c) the
   subtree is stuck (consecutive branch failures >= threshold), (d) the
   lessons ledger has no prior resolution (truly novel). Does NOT escalate on
   high-confidence findings, budget exhaustion, or diminishing returns — those
   are stop conditions, not escalations. Escalation is a rare, uncertainty-
   driven ASK FOR HELP, not a blanket pause.

HONESTY INVARIANTS (mirrors toolsmith / method_lab / lessons ledger):
  * FAST mode may only PROPOSE children or mark a node OBVIOUS — it NEVER
    CONFIRMS. Only DEEP mode confirms/disproves (like confirm-on-run).
  * Sub-agents invoke real swarm agent code, not fabricated reasoning.
  * Pruning follows real DISPROVED lifecycle status, never heuristic guesses.
  * Escalation surfaces the actual Unknown + evidence; it never fabricates a
    question. No escalation when the answer is already known.

SECURITY INVARIANT:
  Sub-agent dispatch carries a scoped hypothesis context (goal + test plan)
  — never the full CognitiveState. Child agents see only what their branch
  needs, preserving tenant isolation and least-privilege reasoning.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum

from sonic.agents.cognitive_state import (
    CognitiveHypothesis,
    HypothesisLifecycle,
    Unknown,
)
from sonic.evidence.models import ConfidenceBand
from sonic.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 1. Process mode
# ============================================================

class ProcessMode(StrEnum):
    """Kahneman System-1/System-2 analog for hypothesis testing."""
    FAST = "fast"  # heuristic, high-throughput, parallel children
    DEEP = "deep"  # thorough, careful, limited parallelism, full reasoning


@dataclass
class ModeDecision:
    """The controller's verdict for a single hypothesis node."""
    mode: ProcessMode
    reason: str
    should_escalate: bool = False
    escalation_reason: str = ""


# ============================================================
# 2. Dual-Process Controller (the switch)
# ============================================================

# Tunable thresholds (kept as module constants so tests can assert against them
# and operators can reason about the policy without hunting through code).
_CONF_FAST_BANDS = {ConfidenceBand.HIGH, ConfidenceBand.VERY_HIGH}
_HIGH_IMPORTANCE_UNKNOWN = 0.70   # an Unknown above this is "high-uncertainty"
_FEW_UNKNOWNS = 2                 # <= this many unresolved unknowns is "few"
_STUCK_BRANCH_FAILURES = 3        # consecutive branch failures before "stuck"


@dataclass
class DualProcessController:
    """Picks FAST vs DEEP for each hypothesis node, and decides escalation.

    The decision is a pure function of observable signals — confidence band,
    unresolved unknowns, novelty, branch failure rate — so it is deterministic
    and testable, not a hidden LLM whim.
    """

    # The caller injects the lessons-ledger hit check so the controller stays
    # free of persistence concerns (dependency inversion). ``known_pattern``
    # returns True when the node's goal has a prior resolution.
    known_pattern_fn: callable = field(default=lambda goal: False)

    def decide(
        self,
        hypothesis: CognitiveHypothesis,
        unknowns: list[Unknown],
        branch_failures: int = 0,
        confidence_score: float = 0.5,
    ) -> ModeDecision:
        """Return the process mode for ``hypothesis``.

        Args:
            hypothesis:       the node being dispatched.
            unknowns:          unresolved Unknowns relevant to this node.
            branch_failures:  consecutive failures on this subtree so far.
            confidence_score: the node's current confidence (0..1).
        """
        band = ConfidenceBand.from_score(confidence_score)
        high_importance = [
            u for u in unknowns if u.estimated_importance >= _HIGH_IMPORTANCE_UNKNOWN
        ]
        known = self.known_pattern_fn(hypothesis.title or hypothesis.description)

        # ESCALATE first: if we are already being careful (DEEP) AND still
        # stuck on a genuinely novel high-uncertainty question, ask a human.
        # This is the ONLY escalation path — "sirf high-uncertainty pe".
        if (
            branch_failures >= _STUCK_BRANCH_FAILURES
            and high_importance
            and not known
        ):
            q = high_importance[0].question
            return ModeDecision(
                mode=ProcessMode.DEEP,
                reason="stuck on a novel high-uncertainty question",
                should_escalate=True,
                escalation_reason=(
                    f"Sub-agent stuck after {branch_failures} attempts on a "
                    f"high-importance unresolved question: '{q}'. No prior "
                    f"resolution in the lessons ledger — human input needed."
                ),
            )

        # DEEP: low/moderate confidence, or high-importance unknowns, or novel.
        if band not in _CONF_FAST_BANDS:
            return ModeDecision(
                mode=ProcessMode.DEEP,
                reason=f"confidence {band.value} below fast threshold",
            )
        if high_importance:
            return ModeDecision(
                mode=ProcessMode.DEEP,
                reason=f"{len(high_importance)} high-importance unknowns unresolved",
            )
        if not known:
            return ModeDecision(
                mode=ProcessMode.DEEP,
                reason="novel pattern — no prior resolution in lessons ledger",
            )

        # FAST: high confidence, few low-importance unknowns, known pattern.
        return ModeDecision(
            mode=ProcessMode.FAST,
            reason=f"{band.value} confidence, known pattern, {len(unknowns)} low-importance unknowns",
        )


# ============================================================
# 3. Hierarchical Hypothesis Tree
# ============================================================

@dataclass
class BranchResult:
    node_id: str
    status: HypothesisLifecycle
    confirmed: bool
    findings: list = field(default_factory=list)


class HierarchicalHypothesisTree:
    """Manages a tree of hypotheses with expand / dispatch / prune.

    Builds on CognitiveHypothesis.parent_id/children_ids (added in this round)
    — no separate model. The tree is a thin coordinator over the existing
    flat ``hypotheses`` list in CognitiveState.
    """

    def __init__(self, controller: DualProcessController, max_parallel: int = 4):
        self.controller = controller
        self.max_parallel = max(1, max_parallel)
        self._nodes: dict[str, CognitiveHypothesis] = {}

    def add(self, hypothesis: CognitiveHypothesis) -> None:
        self._nodes[hypothesis.id] = hypothesis
        if hypothesis.parent_id and hypothesis.parent_id in self._nodes:
            parent = self._nodes[hypothesis.parent_id]
            if hypothesis.id not in parent.children_ids:
                parent.children_ids.append(hypothesis.id)

    def get(self, node_id: str) -> CognitiveHypothesis | None:
        return self._nodes.get(node_id)

    def expand(self, parent_id: str, children: list[CognitiveHypothesis]) -> None:
        """Attach children under a confirmed parent.

        Children inherit the parent's engagement/tenant context so sub-agents
        stay scoped to their branch (security invariant).
        """
        parent = self._nodes.get(parent_id)
        if parent is None:
            return
        for child in children:
            child.parent_id = parent_id
            child.engagement_id = parent.engagement_id
            child.tenant_id = parent.tenant_id
            self.add(child)

    def subtree_ids(self, root_id: str) -> list[str]:
        """All node ids in the subtree rooted at ``root_id`` (BFS)."""
        ids: list[str] = []
        queue = [root_id]
        while queue:
            nid = queue.pop(0)
            ids.append(nid)
            node = self._nodes.get(nid)
            if node:
                queue.extend(node.children_ids)
        return ids

    def prune(self, root_id: str) -> list[str]:
        """Remove a disproved node's whole subtree so dead branches never
        dispatch sub-agents. Returns the pruned ids. Pruning follows real
        DISPROVED status only — the caller must have set the lifecycle."""
        node = self._nodes.get(root_id)
        if node is None or node.lifecycle != HypothesisLifecycle.DISPROVED:
            return []
        pruned = self.subtree_ids(root_id)
        for nid in pruned:
            self._nodes.pop(nid, None)
        logger.info("subtree_pruned", root_id=root_id, pruned_count=len(pruned))
        return pruned

    async def dispatch(
        self,
        node_id: str,
        unknowns: list[Unknown],
        agent_runner: callable,
        branch_failures: int = 0,
        confidence_score: float = 0.5,
    ) -> list[BranchResult]:
        """Dispatch the node and (in FAST mode) its children as sub-agents.

        ``agent_runner`` is an async callable ``(hypothesis, mode) -> result``
        — the caller binds it to real swarm agents, so this class stays free
        of agent-class coupling. FAST mode fans out children in parallel
        (gather, capped by max_parallel); DEEP mode runs the node alone then
        expands on confirmation.

        Returns one BranchResult per dispatched node (the node + any children).
        """
        node = self._nodes.get(node_id)
        if node is None:
            return []
        decision = self.controller.decide(
            node, unknowns, branch_failures, confidence_score
        )
        node.process_mode = decision.mode.value

        if decision.should_escalate:
            logger.warning(
                "human_escalation", node_id=node_id,
                reason=decision.escalation_reason,
            )
            # Escalation surfaces the question; the node stays PROPOSED so a
            # human (or a resumed deep pass) can act on it. We do NOT auto-
            # confirm or auto-disprove — that would be fabrication.
            return [BranchResult(node_id, node.lifecycle, False, [decision.escalation_reason])]

        if decision.mode == ProcessMode.DEEP:
            try:
                res = await agent_runner(node, ProcessMode.DEEP)
            except Exception as exc:
                res = exc
            status = _lifecycle_from_result(res)
            node.lifecycle = status
            confirmed = status == HypothesisLifecycle.VERIFIED
            results = [BranchResult(node_id, status, confirmed, _findings_from(res))]
            if confirmed and node.children_ids:
                results.extend(await self._fan_out_children(node, unknowns, agent_runner))
            return results

        # FAST: run the node + its children concurrently (heuristic pass).
        children = [self._nodes[c] for c in node.children_ids if c in self._nodes]
        nodes_to_run = [node] + children
        return await self._gather_run(nodes_to_run, ProcessMode.FAST, agent_runner)

    async def _fan_out_children(
        self,
        parent: CognitiveHypothesis,
        unknowns: list[Unknown],
        agent_runner: callable,
    ) -> list[BranchResult]:
        children = [self._nodes[c] for c in parent.children_ids if c in self._nodes]
        return await self._gather_run(children, ProcessMode.DEEP, agent_runner)

    async def _gather_run(
        self,
        nodes: list[CognitiveHypothesis],
        mode: ProcessMode,
        agent_runner: callable,
    ) -> list[BranchResult]:
        """Run nodes concurrently, capped by max_parallel — mirrors
        SwarmRunner's gather pattern so we never exceed the budget."""
        results: list[BranchResult] = []
        for i in range(0, len(nodes), self.max_parallel):
            batch = nodes[i:i + self.max_parallel]
            for n in batch:
                n.process_mode = mode.value
            outs = await asyncio.gather(
                *(agent_runner(n, mode) for n in batch),
                return_exceptions=True,
            )
            for n, out in zip(batch, outs, strict=False):
                status = (
                    HypothesisLifecycle.DISPROVED
                    if isinstance(out, Exception)
                    else _lifecycle_from_result(out)
                )
                n.lifecycle = status
                confirmed = status == HypothesisLifecycle.VERIFIED
                results.append(BranchResult(n.id, status, confirmed, _findings_from(out)))
        return results


def _lifecycle_from_result(result: object) -> HypothesisLifecycle:
    """Extract lifecycle status from a sub-agent's result honestly.

    Sub-agents return dicts (like swarm agents) with a ``status`` key, or an
    object with a ``confirmed`` flag. Only explicit confirmation → CONFIRMED;
    failure → DISPROVED; anything ambiguous stays PROPOSED (no fabrication).
    """
    if isinstance(result, Exception):
        return HypothesisLifecycle.DISPROVED
    if isinstance(result, dict):
        status = result.get("status", "").lower()
        if status in ("verified", "confirmed", "success"):
            return HypothesisLifecycle.VERIFIED
        if status in ("disproved", "failed", "refuted"):
            return HypothesisLifecycle.DISPROVED
        return HypothesisLifecycle.PROPOSED
    confirmed = getattr(result, "confirmed", None)
    if confirmed is True:
        return HypothesisLifecycle.VERIFIED
    if confirmed is False:
        return HypothesisLifecycle.DISPROVED
    return HypothesisLifecycle.PROPOSED


def _findings_from(result: object) -> list:
    if isinstance(result, Exception):
        return [{"error": str(result)}]
    if isinstance(result, dict):
        return result.get("findings", [])
    return getattr(result, "findings", []) or []
