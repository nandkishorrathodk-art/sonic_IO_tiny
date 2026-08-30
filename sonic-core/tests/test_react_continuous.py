"""
Tests for the ReAct engine's continuous (sustained) execution mode.

The continuous loop does NOT stop at the first Final Answer — it feeds each
round's partial result back into the next round so the agent keeps probing,
pivoting, and chaining until a stop condition is met or max_rounds is hit.
"""

from __future__ import annotations

import asyncio
import pytest

from sonic.agents.react_engine import (
    ReActEngine, create_default_tool_registry,
)


def test_continuous_runs_multiple_rounds_not_one():
    """Without a stop condition the engine runs all max_rounds, not 1."""
    async def _run():
        registry = create_default_tool_registry()
        engine = ReActEngine(registry, max_iterations=2)

        call_count = {"n": 0}

        async def mock_think(prompt: str) -> str:
            call_count["n"] += 1
            # Always produce a final answer quickly so each round is short.
            return 'Thought: done.\nFinal Answer: {"round": %d}' % call_count["n"]

        result = await engine.execute_continuous(
            task="Test target", think_fn=mock_think, max_rounds=3,
        )
        assert result["rounds_run"] == 3
        assert result["success"] is True
        assert result["total_steps"] >= 3
        # Every round produced a final answer, but the loop kept going.
        assert all(r["success"] for r in result["rounds"])
    asyncio.run(_run())


def test_continuous_stop_when_terminates_early():
    async def _run():
        registry = create_default_tool_registry()
        engine = ReActEngine(registry, max_iterations=2)

        async def mock_think(prompt: str) -> str:
            return 'Thought: done.\nFinal Answer: {"confirmed": true}'

        def stop_when(idx, result):
            # Stop once a confirmed finding appears.
            return "confirmed" in result.get("answer", "")

        result = await engine.execute_continuous(
            task="Exploit", think_fn=mock_think, max_rounds=5,
            stop_when=stop_when,
        )
        assert result["rounds_run"] == 1
        assert "confirmed" in result["answer"]
    asyncio.run(_run())


def test_continuous_on_round_chains_new_task():
    async def _run():
        registry = create_default_tool_registry()
        engine = ReActEngine(registry, max_iterations=2)

        tasks_seen: list[str] = []

        async def mock_think(prompt: str) -> str:
            return 'Thought: done.\nFinal Answer: {"ok": true}'

        def on_round(idx, result):
            tasks_seen.append(f"round-{idx}")
            # Continue for two rounds, then stop by returning empty.
            return f"Next pivot task {idx}" if idx < 2 else ""

        result = await engine.execute_continuous(
            task="Initial", think_fn=mock_think, max_rounds=10,
            on_round=on_round,
        )
        assert result["rounds_run"] == 2
        assert tasks_seen == ["round-1", "round-2"]
    asyncio.run(_run())


def test_continuous_feeds_previous_answer_as_context():
    """When no on_round hook is set, the previous answer becomes next context."""
    async def _run():
        registry = create_default_tool_registry()
        engine = ReActEngine(registry, max_iterations=2)

        seen_contexts: list[str] = []

        async def mock_think(prompt: str) -> str:
            # Capture the context portion of the prompt.
            if "Previous round produced" in prompt:
                # extract a marker
                seen_contexts.append("fed_back")
                return 'Thought: chaining.\nFinal Answer: {"chain": true}'
            return 'Thought: start.\nFinal Answer: {"chain": false}'

        result = await engine.execute_continuous(
            task="Engage", think_fn=mock_think, max_rounds=2,
        )
        assert result["rounds_run"] == 2
        assert seen_contexts  # second round saw the fed-back context
    asyncio.run(_run())


def test_continuous_max_iterations_per_round_respected():
    """Each round is still bounded by max_iterations (no infinite spin)."""
    async def _run():
        registry = create_default_tool_registry()
        engine = ReActEngine(registry, max_iterations=2)

        async def always_act(prompt: str) -> str:
            return "Thought: keep going.\nAction: nmap[-sV target.com]"

        result = await engine.execute_continuous(
            task="Recon", think_fn=always_act, max_rounds=2,
        )
        # No round succeeded (all hit max iterations), but the loop ran 2 rounds.
        assert result["rounds_run"] == 2
        assert result["success"] is False
        assert result["total_steps"] == 4  # 2 iters * 2 rounds
    asyncio.run(_run())
