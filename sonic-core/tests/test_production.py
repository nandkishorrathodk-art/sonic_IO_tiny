"""
Unit tests for Phase 4 Production Components:
- ExploitValidator & CodeFixAgent
- EgressRateLimiter & Anti-DoS
- Observability & Prometheus Metrics
"""

import asyncio
from unittest.mock import AsyncMock
import pytest

from sonic.agents.codefix import CodeFixAgent
from sonic.agents.exploit_validator import ExploitValidator
from sonic.llm.schemas import LLMResponse, ProviderName, TokenUsage
from sonic.observability.metrics import SwarmMetrics
from sonic.safety.rate_limiter import EgressRateLimiter


def test_exploit_validator_evaluation():
    async def _run():
        validator = ExploitValidator()
        # Mock think response with valid ProviderName
        validator.think = AsyncMock(return_value=LLMResponse(
            content='{"is_confirmed": true, "blast_radius": "tenant_wide", "confidence_score": 95, "execution_proof": "Confirmed", "notes": "Verified"}',
            model="mock-model",
            provider=ProviderName.LOCAL,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        ))

        finding = {
            "uid": "fnd-99",
            "title": "IDOR on token endpoint",
            "vulnerability_class": "IDOR",
            "poc": "GET /api/user/10/tokens HTTP/1.1",
            # Production contract: empirical confirmation requires real sandbox
            # execution evidence (model-only confirmation is disabled by the
            # P0 security hardening), so supply evidence + a sandbox-derived
            # confidence/blast radius.
            "execution_evidence": "HTTP/1.1 200 OK\n{\"tokens\":[...]}  (sandbox reproduction confirmed unauthorized access to user 10 tokens)",
            "evidence_provenance": {"execution_id": "exec-99", "sandbox_id": "sandbox-99", "source_agent": "verifier-99", "gate_passed": True},
            "confidence_score": 90,
            "blast_radius": "tenant_wide",
        }
        res = await validator._validate_poc(finding)
        assert res.is_confirmed is True
        assert res.confidence_score >= 80
        assert res.blast_radius in ["account_scoped", "tenant_wide", "infrastructure_wide"]

    asyncio.run(_run())


def test_codefix_agent_remediation_generation():
    async def _run():
        agent = CodeFixAgent()
        # Mock think response with valid ProviderName
        agent.think = AsyncMock(return_value=LLMResponse(
            content='{"patch_diff": "diff --git a/file b/file\\n+ fix", "regression_tests": "def test_fix(): pass", "pr_title": "Fix: SQLi in search", "pr_description": "Fixed SQL injection", "remediation_summary": "Applied parameterized query"}',
            model="mock-model",
            provider=ProviderName.LOCAL,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        ))

        finding = {
            "uid": "fnd-99",
            "title": "SQL Injection in User Search",
            "vulnerability_class": "SQLi",
            "description": "Unescaped search query in database lookup",
            "poc": "GET /search?q=1' OR '1'='1",
        }
        pkg = await agent._generate_fix(finding, "const query = `SELECT * FROM users WHERE name = '${req.query.q}'`;")
        assert pkg.finding_id == "fnd-99"
        assert len(pkg.patch_diff) > 0
        assert len(pkg.regression_tests) > 0
        assert "Fix" in pkg.pr_title or "Security" in pkg.pr_title

    asyncio.run(_run())


def test_egress_rate_limiter_and_backoff():
    async def _run():
        limiter = EgressRateLimiter(default_rps=20.0, default_burst=5.0, max_concurrent=2)

        # Acquire tokens
        await limiter.acquire("api.target.com", tokens_needed=1.0)
        bucket = limiter._get_bucket("api.target.com")
        assert bucket.active_connections == 1

        # Release with standard 200 OK
        await limiter.release("api.target.com", status_code=200)
        assert bucket.active_connections == 0
        assert bucket.backoff_multiplier == 1.0

        # Trigger 429 Too Many Requests -> backoff multiplier should increase
        await limiter.release("api.target.com", status_code=429)
        assert bucket.backoff_multiplier > 1.0

    asyncio.run(_run())


def test_swarm_observability_metrics():
    metrics = SwarmMetrics()
    metrics.active_engagements = 2
    metrics.active_agents = 6
    metrics.record_finding("critical")
    metrics.record_finding("high")
    metrics.record_llm_usage(tokens=1500, cost_usd=0.015)
    metrics.record_egress()
    metrics.record_safety_blocked()

    assert metrics.findings_total["critical"] == 1
    assert metrics.findings_total["high"] == 1
    assert metrics.llm_requests_total == 1
    assert metrics.llm_tokens_total == 1500
    assert metrics.safety_violations_blocked == 1

    # Test Prometheus exposition text
    prom_text = metrics.export_prometheus()
    assert "sonic_active_engagements 2" in prom_text
    assert "sonic_active_agents 6" in prom_text
    assert 'sonic_findings_total{severity="critical"} 1' in prom_text
    assert "sonic_safety_blocked_total 1" in prom_text
