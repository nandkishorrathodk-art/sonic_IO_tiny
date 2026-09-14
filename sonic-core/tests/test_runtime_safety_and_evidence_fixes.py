from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from sonic.agents.engagement import EngagementManager
from sonic.agents.exploit_validator import ExploitValidator
from sonic.agents.verifier import VerifierAgent
from sonic.llm.schemas import LLMResponse, ProviderName, TokenUsage
from sonic.memory.inmemory import InMemoryGraph
from sonic.safety.action_policy import ActionPolicy
from sonic.safety.runtime_stop import get_runtime_stop_state
from sonic.safety.scope import ScopeChecker


def _scope() -> ScopeChecker:
    checker = ScopeChecker()
    checker._loaded = True
    return checker


def test_runtime_stop_is_tenant_aware_and_fail_closed():
    state = get_runtime_stop_state()
    state.clear()
    try:
        policy_a = ActionPolicy(scope_checker=_scope(), tenant_id="tenant-a")
        policy_b = ActionPolicy(scope_checker=_scope(), tenant_id="tenant-b")
        state.stop("tenant-a", "incident")
        assert not policy_a.evaluate("GUI_SCREENSHOT", "", {}).allowed
        assert policy_b.evaluate("GUI_SCREENSHOT", "", {}).allowed
    finally:
        state.clear()


def test_configured_kill_switch_disabled_blocks_policy():
    checker = _scope()
    checker._rules = {"kill_switch": {"enabled": False}}
    policy = ActionPolicy(scope_checker=checker)
    verdict = policy.evaluate("GUI_SCREENSHOT", "", {})
    assert not verdict.allowed
    assert "configured kill switch" in verdict.reason


def test_llm_only_verifier_can_never_return_verified():
    memory = InMemoryGraph()
    memory._connected = True
    agent = VerifierAgent(model_router=None, graph_memory=memory, scope_checker=_scope())
    agent._http_reproduce = AsyncMock(return_value=None)
    agent._engine_verify = AsyncMock(return_value=None)
    agent._llm_verify = AsyncMock(return_value={"status": "verified", "confidence_score": 99})
    verdict = asyncio.run(agent._verify_finding({"uid": "f-1", "title": "logic flaw"}))
    assert verdict["status"] == "needs_more_evidence"
    assert verdict["confidence_score"] <= 30


def test_exploit_validator_requires_gate_and_provenance():
    validator = ExploitValidator.__new__(ExploitValidator)
    finding = {"uid": "f-1", "execution_evidence": "HTTP 200 vulnerable"}
    report = asyncio.run(validator._validate_poc(finding))
    assert report.is_confirmed is False
    assert "provenance" in report.notes


def test_engagement_computer_dynamic_binds_scope_checker_and_config(monkeypatch):
    memory = InMemoryGraph()
    memory._connected = True
    checker = _scope()
    manager = EngagementManager(model_router=None, graph_memory=memory, scope_checker=checker)
    manager.active_engagements["eng-1"] = {
        "tenant_id": "tenant-a", "scope": {"targets": {"domains": ["target.test"]}},
    }

    class Provider:
        async def get_or_create_home(self, tenant_id):
            return type("Home", (), {"id": "ws-1"})()

    manager.computer_provider = Provider()
    captured = {}

    async def fake_run(self, task=None, **kwargs):
        captured["scope_checker"] = self.safety.scope_checker
        captured["scope_config"] = self.safety.scope_config
        return {"traces": []}

    from sonic.computer_use.agent import ComputerUseAgent
    monkeypatch.setattr(ComputerUseAgent, "run_mission", fake_run)
    asyncio.run(manager._run_computer_dynamic("eng-1", "target.test", {}, {}, {}))
    assert captured["scope_checker"] is checker
    assert captured["scope_config"] == {"targets": {"domains": ["target.test"]}}
