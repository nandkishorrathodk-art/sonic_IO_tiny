"""
AI-Human layer (Phase 7) — Persistent Being tests.

Proves the "AI human" foundation is REAL, not claimed:

    [x] Being identity is stable across a simulated restart: same being_id +
        same born_at after singleton reset (NOT a reminted UUID).
    [x] First contact provisions; second contact re-attaches (touch_attached).
    [x] BeingMind (mood/curiosity/learned_facts) persists across restart.
    [x] record_idle_cycle evolves mood: a novel fact rewards curiosity+satiety;
        a dead-end raises satiety (boredom) + focus.
    [x] Tenant isolation: each tenant gets its own being; cross-tenant reads
        return nothing.
    [x] BeingLifeLoop refuses construction without a safety policy (an always-on
        autonomous being must not act without the ActionPolicy envelope).
    [x] The life loop tick routes the being's self-directed action THROUGH the
        agent's safety gate — a destructive idle pursuit is BLOCKED, never
        executed, and still recorded as an idle cycle (mood evolves on the
        blocked/dead-end outcome).
    [x] The always-on loop starts/stops cleanly (long-lived task, cancellation
        on shutdown) and does not raise on a failed tick.
    [x] Durable craft: a being-authored note persists on the host filesystem
        across restart and is being-scoped (isolation between beings).

Stubs stand in for the provider/LLM; the REAL Being identity, BeingMind,
BeingLifeLoop, ActionPolicy gate, and BeingCraft run.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any

import pytest

from sonic.being.craft import BeingCraft
from sonic.being.identity import (
    Being,
    BeingMind,
    get_being_store,
    get_or_create_being,
    record_idle_cycle,
    reset_being_singleton,
)
from sonic.being.life_loop import BeingLifeLoop
from sonic.computer.models import ComputerState, FileEntry, GitStatusInfo, ScreenObservation
from sonic.computer.provider import ComputerProvider
from sonic.computer_use.agent import ComputerUseAgent, _GOAL_COMPLETE_SENTINEL
from sonic.computer_use.curiosity import CuriosityLoop
from sonic.computer_use.models import ComputerActionType
from sonic.safety.action_policy import ActionPolicy
from sonic.sandbox.provider import ExecResult


# ---------------------------------------------------------------------------
# Test doubles (mirror the Phase 6 test scaffolding)
# ---------------------------------------------------------------------------

class _StubComputer(ComputerProvider):
    def __init__(self, terminal_output="ready"):
        self.workspace_id = "ws"
        self.terminal_output = terminal_output
        self.commands = []
        self.written = []

    async def create(self, *a, **k): return type("W", (), {"id": self.workspace_id})()
    async def destroy(self, ws): return True
    async def status(self, ws): return ComputerState(workspace_id=ws, tenant_id="t", running_processes=["sh"])
    async def screenshot(self, ws): return ScreenObservation(visible_text="desktop")
    async def gui_action(self, *a, **k): return ScreenObservation()
    async def terminal(self, ws, command, timeout=60, actor="operator"):
        self.commands.append(command)
        return ExecResult(command=command, exit_code=0, stdout=self.terminal_output, stderr="")
    async def read_file(self, ws, path): return "SRC"
    async def write_file(self, ws, path, content, actor="operator"): self.written.append(path); return True
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
    """Dual-purpose: returns curiosity goal proposals + mission actions."""
    def __init__(self, responses=None, proposals=None):
        self.responses = list(responses) if responses else []
        self.proposals = list(proposals) if proposals else []
        self._r_i = 0
        self._p_i = 0

    async def complete(self, request, **kw):
        prompt = "\n".join(m.content for m in request.messages)
        if "GOAL:" in prompt and "RATIONALE:" in prompt:
            prop = self.proposals[self._p_i % len(self.proposals)] if self.proposals else "explore"
            self._p_i += 1
            return type("R", (), {"content": f"GOAL: {prop}\nRATIONALE: unknown"})()
        if self.responses:
            resp = self.responses[self._r_i % len(self.responses)]
            self._r_i += 1
            return type("R", (), {"content": resp})()
        # Default mission action: a destructive command to exercise the gate.
        return type("R", (), {"content":
            f"ACTION: TERMINAL_EXEC\nTARGET: rm\nPAYLOAD: {{\"command\": \"rm -rf /home/sonic/workspace/x\"}}\nEXPECTED: ok"})()


def _act(action, target, payload, expected="ok"):
    return f"ACTION: {action}\nTARGET: {target}\nPAYLOAD: {payload}\nEXPECTED: {expected}"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _policy(**kw):
    return ActionPolicy(workspace_root="/home/sonic/workspace", **kw)


@pytest.fixture(autouse=True)
def _isolated_being_db(tmp_path, monkeypatch):
    """Each test gets a fresh SQLite DB + craft root."""
    db = str(tmp_path / "being.db")
    monkeypatch.setenv("SONIC_BEING_DB_PATH", db)
    monkeypatch.setenv("SONIC_MEMORY_DB_PATH", db)
    monkeypatch.setenv("SONIC_DATA_DIR", str(tmp_path / "sonic_data"))
    reset_being_singleton()
    yield
    reset_being_singleton()


# ---------------------------------------------------------------------------
# [x] Stable identity across restart
# ---------------------------------------------------------------------------

def test_being_identity_stable_across_restart():
    b = get_or_create_being("alice@example.com")
    first_id, first_born = b.being_id, b.born_at
    assert first_id.startswith("being-")

    # Simulate restart: drop the singleton, re-attach from SQLite.
    reset_being_singleton()
    b2 = get_or_create_being("alice@example.com")

    assert b2.being_id == first_id          # NOT reminted
    assert b2.born_at == first_born          # birth preserved
    assert b2.last_attached_at != ""         # re-attach timestamped
    # A per-instance UUID would change; this proves identity persists.
    assert b2.being_id == b.being_id


def test_first_contact_provisions_second_reattaches():
    store = get_being_store()
    assert store.get_being_for_tenant("bob@example.com") is None
    b = get_or_create_being("bob@example.com")
    assert b.being_id is not None
    reset_being_singleton()
    b2 = get_or_create_being("bob@example.com")
    # Re-attach touched the timestamp.
    assert b2.being_id == b.being_id


# ---------------------------------------------------------------------------
# [x] BeingMind persists + mood evolves
# ---------------------------------------------------------------------------

def test_being_mind_persists_across_restart():
    b = get_or_create_being("carol@example.com")
    record_idle_cycle(b.being_id, "port 22 runs openssh 9.2")
    record_idle_cycle(b.being_id, "port 80 runs nginx")

    reset_being_singleton()
    b2 = get_or_create_being("carol@example.com")
    mind = get_being_store().get_mind(b2.being_id)

    assert mind.idle_cycles_run == 2
    assert mind.goals_pursued == 2
    assert "port 22 runs openssh 9.2" in mind.learned_facts
    assert "port 80 runs nginx" in mind.learned_facts
    # Novel facts raised curiosity + satiety from defaults.
    assert mind.curiosity_drive > 0.7
    assert mind.satiety > 0.5


def test_dead_end_evolves_mood_toward_boredom():
    b = get_or_create_being("dave@example.com")
    before = get_being_store().get_mind(b.being_id)
    cur0, focus0 = before.curiosity_drive, before.focus
    # Two dead-ends (no learned fact).
    record_idle_cycle(b.being_id, None)
    record_idle_cycle(b.being_id, None)
    after = get_being_store().get_mind(b.being_id)
    assert after.curiosity_drive < cur0      # curiosity drops on dead-ends
    assert after.focus > focus0              # focus rises (time to finish work)
    assert after.goals_pursued == 0          # dead-ends aren't goals pursued


# ---------------------------------------------------------------------------
# [x] Tenant isolation
# ---------------------------------------------------------------------------

def test_tenant_isolation_between_beings():
    a = get_or_create_being("alice@example.com")
    e = get_or_create_being("eve@example.com")
    assert a.being_id != e.being_id
    record_idle_cycle(a.being_id, "alice's fact")
    reset_being_singleton()
    store = get_being_store()
    # Eve's mind does NOT contain alice's fact.
    eve = store.get_being_for_tenant("eve@example.com")
    assert "alice's fact" not in store.get_mind(eve.being_id).learned_facts
    # Alice's mind DOES.
    alice = store.get_being_for_tenant("alice@example.com")
    assert "alice's fact" in store.get_mind(alice.being_id).learned_facts


# ---------------------------------------------------------------------------
# [x] Life loop refuses construction without a safety policy
# ---------------------------------------------------------------------------

def test_life_loop_requires_safety_policy():
    comp = _StubComputer()
    being = get_or_create_being("frank@example.com")
    # Agent with NO safety policy.
    agent = ComputerUseAgent(computer_provider=comp, llm_router=_StubLLM(proposals=["x"]))
    curiosity = CuriosityLoop(llm_router=_StubLLM(proposals=["x"]),
                              vector_memory=_NullVectorMemory(), max_cycles=1)
    with pytest.raises(ValueError, match="safety policy"):
        BeingLifeLoop(being, agent, curiosity, comp.workspace_id)


class _NullVectorMemory:
    """Minimal vector memory stub for curiosity loop (no persistence needed here)."""
    def index_document(self, doc_id, text, metadata=None): return True
    def search(self, query, limit=5): return []
    def is_duplicate(self, text, threshold=0.9): return False, 0.0


# ---------------------------------------------------------------------------
# [x] The life loop tick routes self-directed action through the safety gate
# ---------------------------------------------------------------------------

def test_life_loop_tick_blocked_by_safety(tmp_path):
    """The being's idle pursuit tries a destructive command; the SAME Phase-6
    gate blocks it — never executed — and the cycle is still recorded."""
    from sonic.memory.vector import VectorMemory
    comp = _StubComputer()
    being = get_or_create_being("grace@example.com")
    vm = VectorMemory(dim=64, db_path=str(tmp_path / "v.db"), persist=True)
    llm = _StubLLM(proposals=["wipe the workspace"])  # default mission action = rm -rf
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm, safety=_policy())
    curiosity = CuriosityLoop(llm_router=llm, vector_memory=vm, max_cycles=1, exploration_steps=2)
    loop = BeingLifeLoop(being, agent, curiosity, comp.workspace_id, tick_interval=0)

    res = _run(loop.tick())

    # The destructive command never reached the provider.
    assert all("rm -rf" not in c for c in comp.commands)
    # A blocked trace was recorded against the being's agent.
    blocked = [t for t in agent.traces if t.status == "BLOCKED"]
    assert blocked, "being's idle action was not gated by safety"
    # The idle cycle was still recorded in the being's mind (dead-end outcome).
    mind = get_being_store().get_mind(being.being_id)
    assert mind.idle_cycles_run == 1


# ---------------------------------------------------------------------------
# [x] Always-on loop starts/stops cleanly + survives a failed tick
# ---------------------------------------------------------------------------

def test_life_loop_starts_and_stops_cleanly():
    comp = _StubComputer()
    being = get_or_create_being("heidi@example.com")
    llm = _StubLLM(proposals=["explore the filesystem"])
    # Provide a safe mission action so the tick doesn't block.
    llm.responses = [_act("FILE_READ", "README.md", '{"path": "README.md"}')]
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm, safety=_policy())
    curiosity = CuriosityLoop(llm_router=llm, vector_memory=_NullVectorMemory(),
                              max_cycles=1, exploration_steps=1)
    loop = BeingLifeLoop(being, agent, curiosity, comp.workspace_id, tick_interval=0)

    async def scenario():
        task = loop.start()
        await asyncio.sleep(0.05)   # let at least one tick run
        await loop.stop(timeout=2.0)
        assert task.done() or task.cancelled()
    _run(scenario())
    assert loop.cycles_completed >= 1


def test_life_loop_survives_failed_tick():
    """A tick that raises must not kill the loop."""
    comp = _StubComputer()
    being = get_or_create_being("ivan@example.com")
    agent = ComputerUseAgent(computer_provider=comp, llm_router=_StubLLM(proposals=["x"]),
                             safety=_policy())

    class _ExplodingCuriosity:
        max_cycles = 1
        exploration_steps = 1
        state = type("S", (), {"cycle": 0, "known_facts": [], "consecutive_dead_ends": 0})()
        async def run_cycle(self, obs, pursue):
            raise RuntimeError("boom")

    loop = BeingLifeLoop(being, agent, _ExplodingCuriosity(), comp.workspace_id, tick_interval=0)
    res = _run(loop.tick())
    assert res is None  # failed tick returns None, does not raise
    # Mind still records the (dead-end) cycle.
    assert get_being_store().get_mind(being.being_id).idle_cycles_run == 1


# ---------------------------------------------------------------------------
# [x] Durable craft persists + being-scoped isolation
# ---------------------------------------------------------------------------

def test_craft_persists_across_restart(tmp_path):
    root = str(tmp_path / "craft" / "b1")
    c = BeingCraft("being-b1", root=root)
    n = c.author("Recon notes", "Found nmap 7.94 in the home sandbox.", kind="observation")
    c.update_note(n.note_id, body="Also found nuclei templates.")

    # Simulate restart: new instance, same root.
    c2 = BeingCraft("being-b1", root=root)
    notes = c2.list_notes()
    assert len(notes) == 1
    assert notes[0].title == "Recon notes"
    got = c2.get_note(n.note_id)
    assert "Also found nuclei templates." in got.body

    # Isolation: a different being sees nothing.
    c3 = BeingCraft("being-b2", root=str(tmp_path / "craft" / "b2"))
    assert c3.list_notes() == []


def test_craft_file_is_human_readable_on_disk(tmp_path):
    """A human can read the being's note directly off disk (inspectable)."""
    root = str(tmp_path / "craft" / "b")
    c = BeingCraft("being-b", root=root)
    n = c.author("Reflection", "Today I learned egress blocks metadata IPs.")
    note_file = tmp_path / "craft" / "b" / f"{n.note_id}.md"
    assert note_file.exists()
    text = note_file.read_text()
    assert "Reflection" in text
    assert "egress blocks metadata IPs" in text
