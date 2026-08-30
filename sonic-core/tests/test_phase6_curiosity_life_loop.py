"""
Phase 6 — Curiosity / Life Loop tests (per PLAN Phase 6).

Proves the agent can run self-directed, novelty-driven exploration with NO
operator-issued goal, and that curiosity compounds via persistent memory:

    [x] The loop PROPOSES its own goal from the live observation + known facts
        (LLM-driven, not a fixed idle script).
    [x] As known facts grow, the proposed goal changes (novelty steers away
        from re-discovering what is already known) — curiosity is adaptive.
    [x] Information gain is measured (NoveltyEngine) and novel facts persist
        to VectorMemory, so curiosity compounds across cycles.
    [x] A dead-end (near-zero novelty vs known facts) is detected and, after a
        couple of repetitions, the loop PIVOTS to a different angle.
    [x] The proposed goal reacts to the OBSERVATION, not just a fixed string.

A stub LLM (proposing goals) + stub computer + real VectorMemory exercise the
REAL CuriosityLoop + agent pursue closure. The agent's real reasoning loop is
used to pursue each proposed goal.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from sonic.computer.models import ComputerState, FileEntry, GitStatusInfo, ScreenObservation
from sonic.computer.provider import ComputerProvider
from sonic.computer_use.agent import ComputerUseAgent, _GOAL_COMPLETE_SENTINEL
from sonic.computer_use.curiosity import CuriosityLoop
from sonic.memory.vector import VectorMemory
from sonic.sandbox.provider import ExecResult


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class _StubComputer(ComputerProvider):
    def __init__(self, visible_text="desktop with a running web app on :8080",
                 terminal_output="ps shows python and nginx"):
        self.workspace_id = "ws"
        self.visible_text = visible_text
        self.terminal_output = terminal_output

    async def create(self, tenant_id, engagement_id, **kw): return type("W", (), {"id": self.workspace_id})()
    async def destroy(self, ws): return True
    async def status(self, ws): return ComputerState(workspace_id=ws, tenant_id="t", running_processes=["sh"])
    async def screenshot(self, ws): return ScreenObservation(visible_text=self.visible_text)
    async def gui_action(self, *a, **k): return ScreenObservation()
    async def terminal(self, ws, command, timeout=60, actor="operator"):
        return ExecResult(command=command, exit_code=0, stdout=self.terminal_output, stderr="")
    async def read_file(self, ws, path): return "SRC"
    async def write_file(self, ws, path, content, actor="operator"): return True
    async def list_files(self, ws, path="."): return [FileEntry(name="app.py", path="app.py")]
    async def git_action(self, ws, action, **kw): return GitStatusInfo()
    async def process_list(self, *a, **k): raise NotImplementedError
    async def application_list(self, *a, **k): raise NotImplementedError
    async def launch_application(self, *a, **k): raise NotImplementedError
    async def close_application(self, *a, **k): raise NotImplementedError
    async def install_application(self, *a, **k): raise NotImplementedError
    async def uninstall_application(self, *a, **k): raise NotImplementedError
    async def service_action(self, *a, **k): raise NotImplementedError
    async def snapshot(self, *a, **k): raise NotImplementedError
    async def restore_snapshot(self, *a, **k): raise NotImplementedError


class _StubLLM:
    """LLM double for BOTH goal-proposal and mission action-selection.

    For curiosity proposals it returns entries from `proposals` in order.
    For mission actions it always completes immediately (GOAL_COMPLETE) — the
    pursuit outcome is the goal text itself, kept distinct per proposal.
    """
    def __init__(self, proposals: list[str]):
        self.proposals = list(proposals)
        self.received_prompts: list[str] = []
        self._prop_i = 0

    async def complete(self, request, **kw):
        prompt = "\n".join(m.content for m in request.messages)
        self.received_prompts.append(prompt)
        # Distinguish a goal-proposal request from a mission action request.
        if "GOAL:" in prompt and "RATIONALE:" in prompt:
            prop = self.proposals[self._prop_i % len(self.proposals)]
            self._prop_i += 1
            return type("R", (), {"content": f"GOAL: {prop}\nRATIONALE: it is unknown"})()
        # Mission action request -> complete immediately.
        return type("R", (), {"content": f"ACTION: GOAL_COMPLETE\nTARGET: g\nPAYLOAD: {{}}\nEXPECTED: {_GOAL_COMPLETE_SENTINEL}"})()


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# [x] The loop self-proposes a goal from the observation (not a script)
# ---------------------------------------------------------------------------

def test_curiosity_self_proposes_goal_from_observation(tmp_path):
    comp = _StubComputer(visible_text="mystery service on port 9090, unknown protocol")
    vm = VectorMemory(dim=64, db_path=str(tmp_path / "curio.db"), persist=True)
    llm = _StubLLM(proposals=["identify the protocol on port 9090"])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm)
    curiosity = CuriosityLoop(llm_router=llm, vector_memory=vm, max_cycles=1, exploration_steps=2)

    res = _run(agent.idle_cycle(comp.workspace_id, curiosity))
    # The proposal prompt embedded the live observation.
    assert "port 9090" in llm.received_prompts[0]
    assert "mystery service" in llm.received_prompts[0]
    assert res.proposed_goal == "identify the protocol on port 9090"
    assert res.cycle == 1


# ---------------------------------------------------------------------------
# [x] Proposed goal changes as known facts grow (novelty-adaptive)
# ---------------------------------------------------------------------------

def test_curiosity_avoids_rediscovering_known_facts(tmp_path):
    """As facts accumulate, the known-facts list grows; the proposal prompt
    surfaces them so the LLM is steered away — and a second distinct proposal
    is requested rather than repeating the first."""
    comp = _StubComputer()
    vm = VectorMemory(dim=64, db_path=str(tmp_path / "curio.db"), persist=True)
    llm = _StubLLM(proposals=["explore area A", "explore area B"])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm)
    curiosity = CuriosityLoop(llm_router=llm, vector_memory=vm, max_cycles=2, exploration_steps=1)

    results = _run(agent.run_curiosity_loop(comp.workspace_id, curiosity))
    assert len(results) == 2
    assert results[0].proposed_goal == "explore area A"
    assert results[1].proposed_goal == "explore area B"
    # The second proposal prompt must list the first learned area as known.
    second_proposal_prompt = [p for p in llm.received_prompts if "GOAL:" in p][1]
    assert "Already learned" in second_proposal_prompt
    assert "explore area A" in second_proposal_prompt  # prior fact surfaced to avoid re-discovery


# ---------------------------------------------------------------------------
# [x] Novel facts persist to VectorMemory (curiosity compounds)
# ---------------------------------------------------------------------------

def test_novel_facts_persist_to_vector_memory(tmp_path):
    comp = _StubComputer()
    vm = VectorMemory(dim=64, db_path=str(tmp_path / "curio.db"), persist=True)
    llm = _StubLLM(proposals=["learn fact one"])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm)
    curiosity = CuriosityLoop(llm_router=llm, vector_memory=vm, max_cycles=1, exploration_steps=1)

    res = _run(agent.idle_cycle(comp.workspace_id, curiosity))
    assert res.was_novel is True
    assert res.info_gain > curiosity.DEAD_END_NOVELTY
    # The fact was indexed in persistent vector memory and is retrievable.
    assert res.learned_fact is not None
    hits = vm.search("learn fact one", top_k=1, score_threshold=0.2)
    assert any("learn fact one" in h["text"] for h in hits), "learned fact not persisted"
    # And the curiosity state now knows it.
    assert res.learned_fact in curiosity.state.known_facts


def test_duplicate_fact_is_not_re_indexed(tmp_path):
    """Re-discovering an already-learned fact yields near-zero novelty and is
    not persisted again — curiosity stays directed at the genuinely unknown."""
    comp = _StubComputer()
    vm = VectorMemory(dim=64, db_path=str(tmp_path / "curio.db"), persist=True)
    llm = _StubLLM(proposals=["same thing", "same thing"])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm)
    curiosity = CuriosityLoop(llm_router=llm, vector_memory=vm, max_cycles=2, exploration_steps=1)

    results = _run(agent.run_curiosity_loop(comp.workspace_id, curiosity))
    # First cycle learns a novel fact; the second (identical) is not novel.
    assert results[0].was_novel is True
    assert results[1].was_novel is False
    # Vector memory holds the fact once, not twice (dedup).
    all_docs = list(vm.documents.values())
    assert len([d for d in all_docs if "same thing" in d.text]) == 1


# ---------------------------------------------------------------------------
# [x] Dead-end detection + pivot
# ---------------------------------------------------------------------------

def test_dead_end_triggers_pivot(tmp_path):
    """Several consecutive zero-novelty cycles flip the proposal prompt into a
    'pivot to a different area' instruction."""
    comp = _StubComputer()
    vm = VectorMemory(dim=64, db_path=str(tmp_path / "curio.db"), persist=True)
    # cycle1 learns "x" (novel); cycle2 + cycle3 re-discover "x" (dead-ends);
    # cycle4's proposal then carries the pivot instruction and proposes fresh.
    llm = _StubLLM(proposals=["x", "x", "x", "fresh area"])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm)
    curiosity = CuriosityLoop(llm_router=llm, vector_memory=vm, max_cycles=4, exploration_steps=1)

    results = _run(agent.run_curiosity_loop(comp.workspace_id, curiosity))
    assert len(results) == 4
    # After PIVOT_AFTER (2) consecutive dead-ends, a pivot flag is set...
    assert any(r.pivoted for r in results)
    # ...and the next proposal prompt instructs a different area.
    pivot_prompt = [p for p in llm.received_prompts if "DIFFERENT, unexplored area" in p]
    assert pivot_prompt, "pivot instruction not issued after repeated dead-ends"
    assert results[-1].proposed_goal == "fresh area"
    assert results[-1].was_novel is True  # the pivot re-discovered novelty
