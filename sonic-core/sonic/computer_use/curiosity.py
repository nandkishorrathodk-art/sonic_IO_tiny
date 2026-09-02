"""
SONIC-REDA — Curiosity / Life Loop (Phase 6)
=============================================

A self-directed cycle the agent runs when it has no operator-issued goal.
Unlike a fixed idle script, the curious goal is PROPOSED by the LLM from the
live observation plus a memory of what has already been learned, biased toward
high novelty / information gain. Each cycle:

    observe
        |
    propose curious goal  (LLM, reacting to observation + known facts + novelty)
        |
    pursue goal  (the same observe -> reason -> act loop)
        |
    measure info_gain  (NoveltyEngine: how novel was the outcome vs known?)
        |
    persist newly-learned fact  (VectorMemory — curiosity compounds across cycles)
        |
    repeat  (avoiding dead-ends, re-biasing toward the unknown)

The goal is emergent from novelty, not scripted: as the agent learns facts,
those areas become less novel, so the LLM is steered toward genuinely unknown
territory. A dead-end (repeated zero novelty) triggers a pivot.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from sonic.logger import get_logger
from sonic.researcher.anomaly_engine import NoveltyEngine

logger = get_logger(__name__)


@dataclass
class CuriosityCycleResult:
    """Outcome of one self-directed curiosity cycle."""
    proposed_goal: str
    rationale: str
    info_gain: float
    learned_fact: Optional[str]
    was_novel: bool
    pivoted: bool
    cycle: int


@dataclass
class CuriosityState:
    """Mutable state carried across curiosity cycles."""
    known_facts: list[str] = field(default_factory=list)
    cycle: int = 0
    consecutive_dead_ends: int = 0
    history: list[CuriosityCycleResult] = field(default_factory=list)


class CuriosityLoop:
    """Self-directed, novelty-driven exploration loop.

    Requires an LLM router (the goal is proposed, not scripted) and an optional
    VectorMemory so learned facts persist (Phase 1 Mind) and novelty compounds.
    """

    # A cycle is considered a dead-end if its outcome is (near) identical to
    # what is already known — i.e. negligible information gain.
    DEAD_END_NOVELTY = 0.05
    # After this many consecutive dead-ends, the loop pivots hard (asks the LLM
    # to propose something from an entirely different angle).
    PIVOT_AFTER = 2

    def __init__(
        self,
        llm_router: Any,
        vector_memory: Optional[Any] = None,
        max_cycles: int = 5,
        exploration_steps: int = 3,
    ):
        self.llm_router = llm_router
        self.vector_memory = vector_memory
        self.max_cycles = max_cycles
        self.exploration_steps = exploration_steps
        self.state = CuriosityState()

    async def propose_curious_goal(self, observation_summary: str) -> tuple[str, str]:
        """Ask the LLM to propose the most informative self-directed goal.

        The LLM sees the current observation and what is already known (with
        novelty context), so it is steered toward the unknown — not a fixed
        idle task. Returns (goal, rationale).
        """
        from sonic.llm.schemas import LLMRequest, Message, MessageRole

        known = "\n".join(f"- {f}" for f in self.state.known_facts) or "(nothing learned yet)"
        pivot_note = ""
        if self.state.consecutive_dead_ends >= self.PIVOT_AFTER:
            pivot_note = (
                "You have repeatedly learned nothing new. PROPOSE a goal from a "
                "DIFFERENT, unexplored area than your recent proposals. "
            )
        system_prompt = (
            "You are the Curiosity core of SONIC — an Autonomous Self-Evolving "
            "Penetration Architect (A-SEA) with no assigned task. Look at the current "
            "world observation and what you have ALREADY learned. Propose the single "
            "most INFORMATIVE goal to pursue next — something genuinely unknown or "
            "unverified that would maximize new information. Do NOT repeat what you "
            "already know. Prefer goals that expose a gap no existing tool or known "
            "technique covers (a candidate for the Toolsmith or Method Lab). "
            f"{pivot_note}"
            "Respond in EXACTLY this format (no markdown):\n"
            "GOAL: <one concrete, self-directed exploratory goal>\n"
            "RATIONALE: <why this is the most informative thing to learn now>"
        )
        user_prompt = (
            f"Cycle {self.state.cycle + 1}.\n"
            f"Current observation:\n{observation_summary}\n\n"
            f"Already learned (avoid re-discovering these):\n{known}\n"
        )
        request = LLMRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content=system_prompt),
                Message(role=MessageRole.USER, content=user_prompt),
            ],
            task_type="reasoning",
        )
        response = await self.llm_router.complete(request)
        return self._parse_proposal(response.content)

    @staticmethod
    def _parse_proposal(text: str) -> tuple[str, str]:
        goal, rationale = "explore the environment", ""
        for line in text.strip().splitlines():
            line = line.strip()
            if line.upper().startswith("GOAL:"):
                goal = line.split(":", 1)[1].strip() or goal
            elif line.upper().startswith("RATIONALE:"):
                rationale = line.split(":", 1)[1].strip()
        return goal, rationale

    def measure_novelty(self, outcome: str) -> float:
        """Information gain of an outcome relative to known facts (0..1)."""
        return NoveltyEngine.compute_novelty(outcome, self.state.known_facts)

    def persist_fact(self, fact: str) -> bool:
        """Record a newly-learned fact to persistent vector memory (Phase 1).

        Returns True if it was genuinely new (not a near-duplicate of an
        existing learned fact). Deduplication keeps curiosity directed at the
        genuinely unknown.
        """
        if self.vector_memory is not None:
            try:
                dup, _ = self.vector_memory.is_duplicate(fact, threshold=0.88)
                if dup:
                    return False
                doc_id = f"curiosity-{self.state.cycle}-{abs(hash(fact)) % 10**8}"
                self.vector_memory.index_document(
                    doc_id, fact, metadata={"source": "curiosity_loop", "cycle": self.state.cycle}
                )
            except Exception as e:
                logger.warning("curiosity_persist_failed", error=str(e))
        # Track in-process too (used for novelty bias even without vector memory).
        if fact not in self.state.known_facts:
            self.state.known_facts.append(fact)
            return True
        return False

    async def run_cycle(self, observation_summary: str, pursue: Any) -> CuriosityCycleResult:
        """Run one curiosity cycle.

        ``pursue`` is an async callable ``(goal: str, steps: int) -> str`` that
        pursues the proposed goal via the agent's real observe->reason->act loop
        and returns the outcome summary (what was observed/learned).
        """
        self.state.cycle += 1
        goal, rationale = await self.propose_curious_goal(observation_summary)
        outcome = await pursue(goal, self.exploration_steps)
        info_gain = self.measure_novelty(outcome)
        was_novel = info_gain >= self.DEAD_END_NOVELTY

        learned: Optional[str] = None
        if was_novel:
            learned = f"{goal}: {outcome}"
            newly = self.persist_fact(learned)
            if not newly:
                # Outcome duplicated an already-learned fact -> not genuinely novel.
                was_novel = False

        pivoted = False
        if was_novel:
            self.state.consecutive_dead_ends = 0
        else:
            self.state.consecutive_dead_ends += 1
            pivoted = self.state.consecutive_dead_ends >= self.PIVOT_AFTER

        result = CuriosityCycleResult(
            proposed_goal=goal, rationale=rationale, info_gain=round(info_gain, 4),
            learned_fact=learned if was_novel else None,
            was_novel=was_novel, pivoted=pivoted, cycle=self.state.cycle,
        )
        self.state.history.append(result)
        logger.info("curiosity_cycle", cycle=result.cycle, goal=goal,
                    info_gain=result.info_gain, novel=was_novel, pivoted=pivoted)
        return result

    async def run(self, observation_summary_fn: Any, pursue: Any) -> list[CuriosityCycleResult]:
        """Run up to max_cycles self-directed curiosity cycles.

        ``observation_summary_fn`` is an async callable ``() -> str`` returning
        the current world observation summary; ``pursue`` as in run_cycle.
        """
        for _ in range(self.max_cycles):
            obs_summary = await observation_summary_fn()
            await self.run_cycle(obs_summary, pursue)
        return list(self.state.history)
