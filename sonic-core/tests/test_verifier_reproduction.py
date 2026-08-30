"""
Tests for the Verifier Agent's real HTTP reproduction layer.

The verifier now re-fires the finding's original request and confirms the
vulnerability signal re-appears before marking a finding "verified". These
tests cover:
  * reproduction confirms a true positive → verified + strong evidence
  * reproduction fails (signal absent) → false_positive
  * reproduction blocked (out-of-scope) → rejected
  * no reproducible request → falls back to the next verification layer
  * raw HTTP request parsing → reconstructed probe
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from sonic.agents.verifier import VerifierAgent
from sonic.llm.schemas import LLMResponse, ProviderName, TokenUsage
from sonic.memory.inmemory import InMemoryGraph
from sonic.safety.scope import ScopeChecker
from sonic.tools.http_probe import ProbeResult, ProbeTest


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


def _make_verifier(scope_config=None, responder=None):
    memory = InMemoryGraph()
    memory._connected = True
    scope = ScopeChecker()
    scope._loaded = True
    agent = VerifierAgent(
        model_router=None,
        graph_memory=memory,
        scope_checker=scope,
        scope_config=scope_config or {},
    )
    import sonic.tools.http_probe as hp
    orig_init = hp.HTTPProbe.__init__

    def patched_init(self, **kwargs):
        kwargs["responder"] = responder
        orig_init(self, **kwargs)
    hp.HTTPProbe.__init__ = patched_init
    return agent, memory, (lambda: setattr(hp.HTTPProbe, "__init__", orig_init))


def _finding(**kw):
    base = {
        "uid": "fnd-1", "title": "Reflected XSS", "vulnerability_class": "XSS",
        "severity": "high",
        "url": "https://app.scope.test/search?q=<script>alert(1)</script>",
        "method": "GET",
        "poc": "<script>alert(1)</script>",
        "expected_if_vulnerable": "<script>alert(1)</script>",
        "raw_request": "GET /search?q=<script>alert(1)</script> HTTP/1.1\r\nHost: app.scope.test\r\n\r\n",
    }
    base.update(kw)
    return base


# --------------------------------------------
# Tests
# --------------------------------------------

def test_verifier_reproduces_confirms_true_positive():
    async def _run():
        restore = None
        try:
            responder = _responder(200, body="<script>alert(1)</script>")
            agent, memory, restore = _make_verifier(
                scope_config={"targets": {"domains": ["*.scope.test"], "ips": []},
                              "exclusions": {"domains": []}},
                responder=responder,
            )
            verdict = await agent._verify_finding(_finding())
            assert verdict["status"] == "verified"
            assert verdict["confidence_score"] >= 85
            assert verdict["evidence_quality"] == "strong"
            assert verdict["reproduction"]["is_vulnerable"] is True
        finally:
            if restore:
                restore()
    asyncio.run(_run())


def test_verifier_reproduction_fail_marks_false_positive():
    async def _run():
        restore = None
        try:
            # Response is clean — the signal does not re-appear.
            responder = _responder(200, body="nothing here")
            agent, memory, restore = _make_verifier(
                scope_config={"targets": {"domains": ["*.scope.test"], "ips": []},
                              "exclusions": {"domains": []}},
                responder=responder,
            )
            verdict = await agent._verify_finding(_finding())
            assert verdict["status"] == "false_positive"
            assert "signal_not_reproducible" in verdict["false_positive_indicators"]
        finally:
            if restore:
                restore()
    asyncio.run(_run())


def test_verifier_reproduction_blocked_rejects():
    async def _run():
        restore = None
        try:
            responder = _responder(200, "ok")
            agent, memory, restore = _make_verifier(
                scope_config={"targets": {"domains": ["allowed.test"], "ips": []},
                              "exclusions": {"domains": []}},
                responder=responder,
            )
            finding = _finding(url="https://evil.example.com/x")
            verdict = await agent._verify_finding(finding)
            assert verdict["status"] == "rejected"
            assert "reproduction_blocked" in verdict["false_positive_indicators"]
        finally:
            if restore:
                restore()
    asyncio.run(_run())


def test_verifier_falls_back_when_no_reproducible_request():
    """A finding with no URL and no raw_request skips HTTP repro → next layer."""
    async def _run():
        restore = None
        try:
            agent, memory, restore = _make_verifier(
                scope_config={"targets": {"domains": ["*"], "ips": []},
                              "exclusions": {"domains": []}},
                responder=_responder(200, "ok"),
            )
            # No reproducible request → skip HTTP & engines → LLM fallback path.
            agent.think = AsyncMock(return_value=_llm_resp(json.dumps({
                "status": "needs_more_evidence", "confidence_score": 40,
                "evidence_quality": "weak",
                "verification_notes": "no PoC to reproduce",
            })))
            finding = {"uid": "x", "title": "Logic flaw",
                      "vulnerability_class": "IDOR", "severity": "medium"}
            verdict = await agent._verify_finding(finding)
            # Should NOT be an HTTP reproduction verdict.
            assert "reproduction" not in verdict
            assert verdict["status"] == "needs_more_evidence"
        finally:
            if restore:
                restore()
    asyncio.run(_run())


def test_verifier_parses_raw_request_to_probe():
    """The raw-HTTP-request parser reconstructs method, url, headers, body."""
    raw = ("POST /api/login HTTP/1.1\r\n"
           "Host: app.scope.test\r\n"
           "Content-Type: application/json\r\n\r\n"
           '{"user":"admin"}')
    parsed = VerifierAgent._parse_raw_request(raw)
    assert parsed is not None
    method, url, headers, body = parsed
    assert method == "POST"
    assert url == "https://app.scope.test/api/login"
    assert headers.get("Content-Type") == "application/json"
    assert '"user":"admin"' in body


def test_verifier_lays_finding_string_response():
    async def _run():
        restore = None
        try:
            responder = _responder(500, body="you have an error in your SQL syntax")
            agent, memory, restore = _make_verifier(
                scope_config={"targets": {"domains": ["*"], "ips": []},
                              "exclusions": {"domains": []}},
                responder=responder,
            )
            finding = _finding(
                vulnerability_class="SQLi", severity="critical",
                url="https://app.scope.test/s?id=1'",
                poc="'",
                expected_if_vulnerable="sql syntax",
            )
            verdict = await agent._verify_finding(finding)
            assert verdict["status"] == "verified"
            assert "error_markers" in verdict["reproduction"]["signals"]
        finally:
            if restore:
                restore()
    asyncio.run(_run())
