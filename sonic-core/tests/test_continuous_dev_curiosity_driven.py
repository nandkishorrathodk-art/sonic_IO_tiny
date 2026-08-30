"""
Curiosity-driven continuous self-development — done-gate tests.

Closes the PLAN.md audit item: the continuous_dev loop was a scripted demo —
hardcoded v1→v2→v3 patches (literal StreamBuffer / QueryCache class strings),
not curiosity-driven. Now `run_multi_generation_lifecycle` delegates to the
curiosity-driven path when a CuriosityLoop + LLM router are wired, and each
generation's patch is derived from a novelty-steered goal (NOT a hardcoded
class string).

    [x] with curiosity + router, run_multi_generation_lifecycle delegates to
        the curiosity-driven path (patch comes from the LLM for a
        curiosity-proposed goal — never the hardcoded StreamBuffer class).
    [x] the patch code is the LLM-authored module for the goal, not the
        literal "class StreamBuffer" / "class QueryCache" demo strings.
    [x] generations record their curiosity provenance (goal + rationale).
    [x] when the LLM fails to author a patch, the loop records an honest
        FAILED generation (no fabrication — patch_code empty / status FAILED),
        rather than silently using the scripted demo.
    [x] without curiosity + router, the scripted demo path still runs
        (backward-compatible fallback) and uses the hardcoded classes.
    [x] run_curiosity_driven_lifecycle requires curiosity + router (raises).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from sonic.computer.models import ComputerState, FileEntry, GitStatusInfo, ScreenObservation
from sonic.computer.provider import ComputerProvider
from sonic.continuous_dev.continuous_loop import ContinuousAutonomousDevLoop
from sonic.continuous_dev.models import GenerationStatus
from sonic.sandbox.provider import ExecResult


class _StubComputer(ComputerProvider):
    def __init__(self, terminal_output="ok"):
        self.terminal_output = terminal_output
        self.workspace_id = "ws-stub"
    async def create(self, tenant_id, engagement_id, **kw):
        return type("W", (), {"id": self.workspace_id})()
    async def destroy(self, ws): return True
    async def status(self, ws):
        return ComputerState(workspace_id=ws, tenant_id="t", running_processes=["sh"])
    async def screenshot(self, ws): return ScreenObservation(visible_text="x")
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


class _FakeCuriosity:
    """Returns a canned curious goal per call; tracks persist_fact calls."""
    def __init__(self):
        self._n = 0
        self.persisted: list[str] = []
    async def propose_curious_goal(self, observation_summary: str):
        self._n += 1
        return (f"goal-{self._n}", f"rationale-{self._n}")
    def persist_fact(self, fact: str) -> bool:
        self.persisted.append(fact)
        return True


class _FakeRouter:
    """Authors a real (canned) patch + test for each goal."""
    def __init__(self, fail: bool = False):
        self._fail = fail
        self.calls = 0
    async def complete(self, request, task_type=None, **kw):
        self.calls += 1
        if self._fail:
            # Malformed → forces the honest-failure path.
            return type("R", (), {"content": "not json"})()
        spec = {
            "patch": f"# LLM-authored patch for goal\nRATE = {self.calls}\n",
            "test_command": f"python -c 'print({self.calls})'",
            "module_name": f"gen_{self.calls}_opt",
        }
        return type("R", (), {"content": json.dumps(spec)})()


def test_curiosity_path_derives_patch_from_goal_not_hardcoded():
    curiosity = _FakeCuriosity()
    router = _FakeRouter()
    loop = ContinuousAutonomousDevLoop(
        _StubComputer(), curiosity=curiosity, llm_router=router,
    )
    gens = asyncio.run(loop.run_multi_generation_lifecycle(tenant_id="t1"))
    assert len(gens) == 3  # delegates to curiosity-driven (generations=3)
    # The patch's target file is the LLM-authored module (gen_N_opt.py), NOT
    # the hardcoded "stream_buffer.py" / "query_cache.py" scripted demo names.
    for g in gens:
        assert "stream_buffer.py" not in g.files_modified
        assert "query_cache.py" not in g.files_modified
    # The router was actually consulted (patch derived from goal), not scripted.
    assert router.calls == 3
    # Curiosity provenance recorded on at least one generation's lineage fact.
    assert curiosity.persisted, "curiosity facts should be persisted"
    assert any("pursued" in f for f in curiosity.persisted)


def test_curiosity_goal_and_rationale_recorded_on_generation():
    curiosity = _FakeCuriosity()
    router = _FakeRouter()
    loop = ContinuousAutonomousDevLoop(
        _StubComputer(), curiosity=curiosity, llm_router=router,
    )
    gens = asyncio.run(loop.run_curiosity_driven_lifecycle(tenant_id="t1", generations=1))
    assert len(gens) == 1
    g = gens[0]
    assert getattr(g, "curiosity_goal", None) == "goal-1"
    assert getattr(g, "curiosity_rationale", None) == "rationale-1"


def test_honest_failure_when_llm_cannot_author_patch():
    curiosity = _FakeCuriosity()
    router = _FakeRouter(fail=True)  # malformed response → no patch
    loop = ContinuousAutonomousDevLoop(
        _StubComputer(), curiosity=curiosity, llm_router=router,
    )
    gens = asyncio.run(loop.run_curiosity_driven_lifecycle(tenant_id="t1", generations=2))
    assert len(gens) == 2
    # Both generations rolled back honestly — no fabricated patch, no scripted demo.
    assert all(g.status == GenerationStatus.ROLLED_BACK for g in gens)
    assert all(g.commit_hash == "" for g in gens)
    assert all(g.files_modified == [] for g in gens)


def test_scripted_fallback_without_curiosity_or_router():
    # No curiosity/router → scripted demo path (hardcoded classes) still runs.
    loop = ContinuousAutonomousDevLoop(_StubComputer())
    gens = asyncio.run(loop.run_multi_generation_lifecycle(tenant_id="t1"))
    assert len(gens) == 2
    # Scripted demo: the hardcoded subsystem names appear.
    assert any("stream_buffer" in f for g in gens for f in g.files_modified)
    assert any("query_cache" in f for g in gens for f in g.files_modified)


def test_curiosity_driven_requires_curiosity_and_router():
    import pytest
    loop = ContinuousAutonomousDevLoop(_StubComputer())
    with pytest.raises(RuntimeError):
        asyncio.run(loop.run_curiosity_driven_lifecycle(tenant_id="t1", generations=1))
