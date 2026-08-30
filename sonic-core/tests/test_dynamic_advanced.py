"""
Tests for the upgraded Dynamic Execution Agent — the autonomous pentest loop.

Verifies the agent:
  * fires REAL probes (via injected responder) instead of returning BLOCKED
  * keeps going (multi-iteration) instead of stopping after one output
  * confirms findings with concrete request+response evidence
  * chains follow-up tests produced by the LLM triage
  * records failed attempts / blocked probes
  * persists findings + evidence to graph memory
  * respects egress guards (blocked probe → recorded, not bypassed)
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from sonic.agents.dynamic_execution import DynamicExecutionAgent
from sonic.llm.schemas import LLMResponse, ProviderName, TokenUsage
from sonic.memory.inmemory import InMemoryGraph
from sonic.memory.schemas import EngagementNode
from sonic.safety.scope import ScopeChecker
from sonic.tools.http_probe import ProbeResult, ProbeTest


# --------------------------------------------
# Fixtures
# --------------------------------------------

def _llm_resp(content: str) -> LLMResponse:
    return LLMResponse(
        content=content, model="mock", provider=ProviderName.LOCAL,
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )


def _responder(status=200, body="", headers=None, elapsed=0.01):
    async def _r(test: ProbeTest):
        return ProbeResult(
            test_name=test.test_name, url=test.url, method=test.method,
            status_code=status, request=f"{test.method} {test.url} HTTP/1.1",
            response_headers=headers or {}, response_body=body,
            response_body_length=len(body), elapsed_seconds=elapsed,
        )
    return _r


def _make_agent(scope_config=None, responder=None, llm_contents=None, max_requests=40, max_iterations=8):
    memory = InMemoryGraph()
    # InMemoryGraph.connect() only flips a flag; call it directly without a loop.
    memory._connected = True
    scope = ScopeChecker()
    scope._loaded = True  # allow L0 by default; we rely on egress + scope_config
    agent = DynamicExecutionAgent(
        model_router=None,  # router None → deterministic triage fallback
        graph_memory=memory,
        scope_checker=scope,
        scope_config=scope_config or {},
        max_requests=max_requests,
        max_iterations=max_iterations,
    )
    # Inject a responder into the probe via monkeypatch of HTTPProbe construction.
    import sonic.tools.http_probe as hp

    orig_init = hp.HTTPProbe.__init__

    def patched_init(self, **kwargs):
        kwargs["responder"] = responder
        orig_init(self, **kwargs)

    hp.HTTPProbe.__init__ = patched_init
    return agent, memory, (lambda: setattr(hp.HTTPProbe, "__init__", orig_init))


def _mock_llm_agent(scope_config=None, generate=None, triage=None, max_iterations=8):
    """Agent whose think() returns scripted generate/triage JSON."""
    memory = InMemoryGraph()
    memory._connected = True
    scope = ScopeChecker()
    scope._loaded = True
    router = AsyncMock()
    agent = DynamicExecutionAgent(
        model_router=router,
        graph_memory=memory,
        scope_checker=scope,
        scope_config=scope_config or {"targets": {"domains": ["*"], "ips": []},
                                       "exclusions": {"domains": []}},
        max_iterations=max_iterations,
        max_requests=40,
    )
    agent.think = AsyncMock()
    return agent, memory


# --------------------------------------------
# Tests
# --------------------------------------------

def test_agent_does_not_return_blocked_when_probe_available():
    """The agent must execute real probes, not return the old BLOCKED stub."""
    async def _run():
        restore = None
        try:
            responder = _responder(200, body="<script>alert(1)</script>")
            agent, memory, restore = _make_agent(
                scope_config={"targets": {"domains": ["*"], "ips": []},
                              "exclusions": {"domains": []}},
                responder=responder,
            )
            result = await agent.run({
                "target": "example.com",
                "engagement_id": "eng-1",
                "task": "general_testing",
                "scope_config": {"targets": {"domains": ["*"], "ips": []},
                                "exclusions": {"domains": []}},
            })
            assert "error" not in result
            assert result["tests_executed"] >= 1
            # Must have run real probes — observations populated
            assert len(result["observations"]) >= 1
            assert result["observations"][0]["blocked"] is False
        finally:
            if restore:
                restore()
    asyncio.run(_run())


def test_agent_confirms_finding_with_evidence():
    async def _run():
        restore = None
        try:
            responder = _responder(200, body="<script>alert(1)</script>")
            agent, memory, restore = _make_agent(
                scope_config={"targets": {"domains": ["*"], "ips": []},
                              "exclusions": {"domains": []}},
                responder=responder,
            )
            # Seed the test queue directly (no LLM).
            result = await agent.run({
                "target": "example.com",
                "engagement_id": "eng-e",
                "task": "general_testing",
                "scope_config": {"targets": {"domains": ["*"], "ips": []},
                                "exclusions": {"domains": []}},
                "tests": [{
                    "test_name": "reflected_xss",
                    "vulnerability_class": "XSS",
                    "method": "GET",
                    "url": "https://example.com/q=<script>alert(1)</script>",
                    "payload": "<script>alert(1)</script>",
                    "expected_if_vulnerable": "<script>alert(1)</script>",
                    "severity_if_confirmed": "high",
                }],
            })
            assert result["vulnerabilities_found"] >= 1
            finding = result["findings"][0]
            assert "<script>alert(1)</script>" in finding["response"]
            assert finding["request"]
            assert finding["vulnerability_class"] == "XSS"
        finally:
            if restore:
                restore()
    asyncio.run(_run())


def test_agent_persists_finding_and_evidence_to_memory():
    async def _run():
        restore = None
        try:
            responder = _responder(500, body="SQL syntax error near '")
            agent, memory, restore = _make_agent(
                scope_config={"targets": {"domains": ["*"], "ips": []},
                              "exclusions": {"domains": []}},
                responder=responder,
            )
            eng = EngagementNode(name="e", target="example.com")
            eng_id = asyncio.ensure_future(memory.create_engagement(eng))
            eng_id = await eng_id
            await agent.run({
                "target": "example.com",
                "engagement_id": eng_id,
                "scope_config": {"targets": {"domains": ["*"], "ips": []},
                                "exclusions": {"domains": []}},
                "tests": [{
                    "test_name": "sqli",
                    "vulnerability_class": "SQLi",
                    "method": "GET",
                    "url": "https://example.com/s?id=1'",
                    "payload": "'",
                    "expected_if_vulnerable": "sql syntax",
                    "severity_if_confirmed": "critical",
                }],
            })
            findings = await memory.find_findings(eng_id)
            assert len(findings) >= 1
            assert findings[0]["vulnerability_class"] == "SQLi"
        finally:
            if restore:
                restore()
    asyncio.run(_run())


def test_agent_chains_follow_up_tests_from_llm_triage():
    """When LLM triage returns follow_up_tests, the loop queues & runs them too."""
    async def _run():
        agent, memory = _mock_llm_agent(
            scope_config={"targets": {"domains": ["*"], "ips": []},
                          "exclusions": {"domains": []}},
        )
        # Seed the test queue via task["tests"]; LLM (think) returns follow-ups once.
        import sonic.tools.http_probe as hp
        orig_init = hp.HTTPProbe.__init__

        call_count = {"n": 0}

        async def responder(test: ProbeTest):
            call_count["n"] += 1
            # First test reflects the payload → vulnerable; follow-ups are clean.
            if "xss" in (test.test_name or "").lower() and call_count["n"] == 1:
                body = "...<script>alert(1)</script>..."
            else:
                body = "clean response"
            return ProbeResult(
                test_name=test.test_name, url=test.url, method=test.method,
                status_code=200, request=f"GET {test.url}",
                response_body=body, response_body_length=len(body),
                elapsed_seconds=0.01,
            )

        def patched_init(self, **kwargs):
            kwargs["responder"] = responder
            orig_init(self, **kwargs)
        hp.HTTPProbe.__init__ = patched_init

        # think() is called for the chain triage after a confirmed finding.
        agent.think = AsyncMock(return_value=_llm_resp(json.dumps({
            "verdict": "confirmed",
            "confidence": 90,
            "reasoning": "chained",
            "impact": "rce",
            "adjusted_severity": "critical",
            "follow_up_tests": [{
                "test_name": "follow_up_rce",
                "vulnerability_class": "RCE",
                "method": "GET",
                "url": "https://example.com/rce?cmd=id",
                "payload": "id",
                "expected_if_vulnerable": "uid=",
                "severity_if_confirmed": "critical",
            }],
        })))
        try:
            result = await agent.run({
                "target": "example.com",
                "engagement_id": "eng-chain",
                "scope_config": {"targets": {"domains": ["*"], "ips": []},
                                "exclusions": {"domains": []}},
                "tests": [{
                    "test_name": "xss_initial",
                    "vulnerability_class": "XSS",
                    "method": "GET",
                    "url": "https://example.com/xss?q=<script>alert(1)</script>",
                    "payload": "<script>alert(1)</script>",
                    "expected_if_vulnerable": "<script>alert(1)</script>",
                    "severity_if_confirmed": "high",
                }],
                "max_iterations": 3,
                "max_requests": 10,
            })
            # The follow-up test must have been queued and executed.
            assert result["tests_executed"] >= 2
            assert result["follow_ups_generated"] >= 1
        finally:
            hp.HTTPProbe.__init__ = orig_init
    asyncio.run(_run())


def test_agent_blocks_out_of_scope_target():
    async def _run():
        restore = None
        try:
            responder = _responder(200, "ok")
            agent, memory, restore = _make_agent(
                scope_config={"targets": {"domains": ["allowed.test"], "ips": []},
                              "exclusions": {"domains": []}},
                responder=responder,
            )
            result = await agent.run({
                "target": "evil.example.com",
                "engagement_id": "eng-block",
                "scope_config": {"targets": {"domains": ["allowed.test"], "ips": []},
                                "exclusions": {"domains": []}},
                "tests": [{
                    "test_name": "oob",
                    "vulnerability_class": "XSS",
                    "method": "GET",
                    "url": "https://evil.example.com/",
                    "payload": "x",
                    "expected_if_vulnerable": "x",
                }],
            })
            # All probes blocked → recorded as failed attempts, no findings.
            assert result["vulnerabilities_found"] == 0
            assert any(a.get("reason") == "blocked" for a in result["failed_attempts"])
        finally:
            if restore:
                restore()
    asyncio.run(_run())


def test_execute_test_legacy_shape():
    """The backward-compat _execute_test entrypoint returns the legacy dict shape."""
    async def _run():
        restore = None
        try:
            responder = _responder(200, body="<script>alert(1)</script>")
            agent, memory, restore = _make_agent(
                scope_config={"targets": {"domains": ["*"], "ips": []},
                              "exclusions": {"domains": []}},
                responder=responder,
            )
            out = await agent._execute_test({
                "test_name": "t",
                "vulnerability_class": "XSS",
                "method": "GET",
                "url": "https://example.com/x?q=<script>alert(1)</script>",
                "payload": "<script>alert(1)</script>",
                "expected_if_vulnerable": "<script>alert(1)</script>",
            }, "eng-1")
            assert "is_vulnerable" in out
            assert "request" in out and "response" in out
            assert "status" in out
        finally:
            if restore:
                restore()
    asyncio.run(_run())
