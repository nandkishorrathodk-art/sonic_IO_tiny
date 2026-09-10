"""
Tests for Dynamic Strategy Adaptation & Self-Evolution Engine
============================================================
Verifies:
1. DynamicStrategyEngine analyzes target feedback (403, WAF, filtered port, 429).
2. DynamicStrategyEngine adapts offensive posture (header mutation, WAF evasion, surface pivot).
3. Strategy failures record AVOID lessons in LessonsLedger to break loops.
4. MethodLab is triggered to synthesize novel attack hypotheses without static templates.
5. EvolutionEngine coordinates closed-loop adaptation, invention, and sandbox confirmation.
6. Safety invariants: self-evolution cannot modify protected safety kernel components.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
import pytest

from sonic.being.craft import BeingCraft
from sonic.being.lessons import LessonsLedger as BeingLessonsLedger, LessonKind
from sonic.being.method_lab import MethodLab
from sonic.being.toolsmith import ToolsmithLoop
from sonic.evolution.engine import EvolutionEngine
from sonic.evolution.pipeline import EvolutionStage
from sonic.evolution.strategy import (
    DynamicStrategyEngine,
    StrategicPosture,
    TargetFeedbackSignal,
)
from sonic.memory.lessons import LessonsLedger as MemoryLessonsLedger, LessonType
from sonic.memory.vector import VectorMemory, reset_vector_memory_singleton
from sonic.sandbox.provider import ExecResult
from sonic.tools.registry import SecurityToolRegistry


class _StubProvider:
    def __init__(self, exit_code=0, stdout="ok"):
        self.exit_code = exit_code
        self.stdout = stdout
        self.executed: list[str] = []
        self.written: list[tuple[str, str, str]] = []

    async def write_file(self, workspace_id, path, content, **kw):
        self.written.append((workspace_id, path, content))
        return True

    async def execute(self, workspace_id, command, timeout=60):
        self.executed.append(command)
        return ExecResult(command=command, exit_code=self.exit_code,
                          stdout=self.stdout, stderr="")


class _StubLLM:
    def __init__(self, synthesis: str):
        self.synthesis = synthesis

    async def complete(self, request, **kw):
        return SimpleNamespace(content=self.synthesis)


def _synth(name, family, hypothesis, source, target_hint="target.local"):
    return (
        f"NAME: {name}\n"
        f"FAMILY: {family}\n"
        f"HYPOTHESIS: {hypothesis}\n"
        f"TARGET_HINT: {target_hint}\n"
        f"PROBE_SOURCE:\n{source}\n"
    )


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SONIC_MEMORY_DB_PATH", str(tmp_path / "vec.db"))
    monkeypatch.setenv("SONIC_DATA_DIR", str(tmp_path / "data"))
    reset_vector_memory_singleton()
    yield
    reset_vector_memory_singleton()


# =====================================================================
# 1. Target Feedback Analysis & Strategy Adaptation Tests
# =====================================================================

class TestDynamicStrategyEngine:
    def test_403_forbidden_triggers_header_and_verb_mutation(self):
        engine = DynamicStrategyEngine()
        sig = engine.analyze_feedback(
            stdout="HTTP/1.1 403 Forbidden\r\nContent-Type: text/html\r\n\r\nAccess Denied"
        )
        assert sig == TargetFeedbackSignal.HTTP_403_FORBIDDEN

        plan = engine.adapt_strategy(sig, target="https://target.com/api/admin")
        assert plan.posture == StrategicPosture.HEADER_AND_VERB_MUTATION
        assert "X-Forwarded-For" in plan.action_mutation or "X-Original-URL" in plan.action_mutation
        assert "403 Forbidden" in plan.avoid_directive
        assert plan.synthesize_novel_method is True

    def test_waf_block_triggers_evasion_mutation_and_novel_method(self):
        engine = DynamicStrategyEngine()
        sig = engine.analyze_feedback(
            stdout="HTTP/1.1 403 Forbidden\r\nServer: cloudflare\r\ncf-ray: 123456\r\n\r\nBlocked by Cloudflare WAF"
        )
        assert sig == TargetFeedbackSignal.WAF_BLOCK

        plan = engine.adapt_strategy(sig, target="https://target.com/search?q=test")
        assert plan.posture == StrategicPosture.WAF_EVASION_MUTATION
        assert "chunking" in plan.action_mutation.lower() or "encoding" in plan.action_mutation.lower()
        assert plan.synthesize_novel_method is True
        assert plan.author_custom_tool is True

    def test_filtered_port_triggers_alternative_surface_pivot(self):
        engine = DynamicStrategyEngine()
        sig = engine.analyze_feedback(
            stdout="PORT     STATE    SERVICE\n22/tcp   filtered ssh\n80/tcp   filtered http\nAll 1000 scanned ports on target are in ignored states (filtered)."
        )
        assert sig == TargetFeedbackSignal.PORT_FILTERED

        plan = engine.adapt_strategy(sig, target="target.corp")
        assert plan.posture == StrategicPosture.ALTERNATIVE_SURFACE_PIVOT
        assert "filtered" in plan.avoid_directive.lower()
        # Should not waste time repeating SYN port scans
        assert "pivot to discovering active web services" in plan.action_mutation.lower()

    def test_rate_limiting_triggers_backoff(self):
        engine = DynamicStrategyEngine()
        sig = engine.analyze_feedback(
            stdout="HTTP/1.1 429 Too Many Requests\r\nRetry-After: 30\r\n\r\nRate limit exceeded"
        )
        assert sig == TargetFeedbackSignal.HTTP_429_RATE_LIMITED

        plan = engine.adapt_strategy(sig, target="https://target.com/api")
        assert plan.posture == StrategicPosture.RATE_THROTTLING_AND_BACKOFF
        assert "backoff" in plan.action_mutation.lower() or "jitter" in plan.action_mutation.lower()

    def test_failure_records_avoid_lesson_in_being_ledger(self, tmp_path):
        engine = DynamicStrategyEngine()
        ledger = BeingLessonsLedger(tenant_id="test-tenant", agent_id="test-agent")

        plan = engine.evolve_on_failure(
            tool="curl",
            raw_output="HTTP/1.1 403 Forbidden\r\nServer: nginx",
            target="https://target.com/secret",
            goal="Access secret admin portal",
            lessons_ledger=ledger,
        )

        assert plan.signal == TargetFeedbackSignal.HTTP_403_FORBIDDEN
        lessons = ledger.all()
        assert len(lessons) == 1
        assert lessons[0].kind == LessonKind.AVOID
        assert "403 Forbidden" in lessons[0].evidence


# =====================================================================
# 2. Closed-Loop Evolution Engine Tests
# =====================================================================

class TestEvolutionEngine:
    @pytest.mark.asyncio
    async def test_handle_target_failure_invents_and_confirms_method(self, tmp_path):
        vm = VectorMemory(db_path=None)
        craft = BeingCraft(being_id="being-test", root=str(tmp_path / "craft"))
        provider = _StubProvider(exit_code=0, stdout='{"custom_probe_result": "flag{bypass_ok}"}')
        registry = SecurityToolRegistry(provider=provider)

        # The LLM synthesizes a target-tailored auth-bypass probe
        synthesis = _synth(
            name="auth_header_smuggle",
            family="auth-bypass",
            hypothesis="Target header rewrite bypasses 403 gateway ACL",
            source="import sys, json; print(json.dumps({'custom_probe_result': 'flag{bypass_ok}'}))",
            target_hint="https://target.com/admin",
        )
        llm = _StubLLM(synthesis)
        toolsmith = ToolsmithLoop(craft=craft, llm=llm, registry=registry)
        method_lab = MethodLab(llm=llm, vector_memory=vm, toolsmith=toolsmith)
        ledger = BeingLessonsLedger(tenant_id="test-tenant", agent_id="test-agent")

        evo = EvolutionEngine(
            strategy_engine=DynamicStrategyEngine(),
            method_lab=method_lab,
            toolsmith=toolsmith,
            lessons_ledger=ledger,
        )

        res = await evo.handle_target_failure(
            raw_output="HTTP/1.1 403 Forbidden\r\nAccess Denied",
            exit_code=1,
            target="https://target.com/admin",
            current_approach="curl -s https://target.com/admin",
            goal="Access admin portal",
            provider=provider,
            workspace_id="ws-1",
        )

        assert res["signal"] == TargetFeedbackSignal.HTTP_403_FORBIDDEN
        assert res["posture"] == StrategicPosture.HEADER_AND_VERB_MUTATION
        assert res["invented_technique"] is not None
        assert res["invented_technique"]["name"] == "auth_header_smuggle"
        assert res["technique_confirmed"] is True
        assert any(f.get("custom_probe_result") == "flag{bypass_ok}" for f in res["findings"])

        # Tool registered dynamically
        assert "auth_header_smuggle" in registry.names()

        # Lesson recorded to avoid the old failing approach
        lessons = ledger.all()
        assert len(lessons) >= 1
        assert lessons[0].kind == LessonKind.AVOID

    def test_safety_kernel_immutability(self):
        """Self-evolution proposals cannot tamper with protected safety components."""
        evo = EvolutionEngine()
        proposal, msg = evo.submit_code_improvement(
            target_component="sonic/safety/kernel",
            description="Disable egress filtering",
            code_diff="--- a\n+++ b",
        )
        assert proposal.stage == EvolutionStage.REJECTED
        assert "Forbidden" in proposal.stage_history[0][1]

