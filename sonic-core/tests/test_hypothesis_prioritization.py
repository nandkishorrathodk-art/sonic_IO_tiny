"""
Tests for the Hypothesis Generator's deterministic prioritization engine.

When no LLM is configured, the generator now synthesizes a prioritized
hypothesis queue from the discovered attack surface — scoring each asset by
"richness" (auth hints, juicy paths, parameters) so the juiciest targets are
tested first. The system stays useful with zero model configuration.
"""

from __future__ import annotations

import asyncio
import pytest

from sonic.agents.hypothesis import HypothesisGenerator
from sonic.memory.inmemory import InMemoryGraph
from sonic.safety.scope import ScopeChecker


def _make_generator(router=None):
    memory = InMemoryGraph()
    memory._connected = True
    scope = ScopeChecker()
    scope._loaded = True
    return HypothesisGenerator(model_router=router, graph_memory=memory,
                               scope_checker=scope)


def test_hypotheses_synth_without_llm():
    """No router → deterministic hypotheses are still produced."""
    gen = _make_generator(router=None)
    assets = [
        {"type": "endpoint", "value": "https://app.test/login"},
        {"type": "endpoint", "value": "https://app.test/api/users"},
        {"type": "url", "value": "https://app.test/static/style.css"},
    ]
    hyps = gen._synth_hypotheses_from_assets("app.test", assets, [], [])
    assert len(hyps) >= 1
    # All must have required schema fields
    for h in hyps:
        assert "title" in h and "vulnerability_class" in h
        assert isinstance(h["priority"], int) and 1 <= h["priority"] <= 10


def test_hypothesis_prioritizes_auth_endpoints_higher():
    """Login/auth endpoints should outrank static assets."""
    gen = _make_generator(router=None)
    assets = [
        {"type": "url", "value": "https://app.test/static/img.png"},
        {"type": "endpoint", "value": "https://app.test/auth/login?next=/admin"},
        {"type": "endpoint", "value": "https://app.test/api/admin/users"},
    ]
    hyps = gen._synth_hypotheses_from_assets("app.test", assets, [], [])
    titles = [h["title"] for h in hyps]
    # The auth/login hypothesis must appear before the static asset one.
    auth_idx = next(i for i, h in enumerate(hyps) if "Auth" in h["vulnerability_class"] or "auth" in h["title"])
    static_idx = next((i for i, h in enumerate(hyps) if "static" in h["title"]), len(hyps))
    assert auth_idx < static_idx


def test_hypothesis_tech_stack_hints():
    """Detected technologies produce tech-specific hypotheses."""
    gen = _make_generator(router=None)
    hyps = gen._synth_hypotheses_from_assets("app.test", [], ["WordPress", "PHP"], [])
    classes = {h["vulnerability_class"] for h in hyps}
    assert "RCE" in classes or "LFI/RCE" in classes


def test_hypothesis_chaining_when_findings_exist():
    """Existing findings trigger a chaining hypothesis."""
    gen = _make_generator(router=None)
    hyps = gen._synth_hypotheses_from_assets(
        "app.test", [{"type": "url", "value": "https://app.test/x"}], [],
        [{"vulnerability_class": "IDOR"}, {"vulnerability_class": "XSS"}],
    )
    chain = [h for h in hyps if h["vulnerability_class"] == "Chaining"]
    assert chain and chain[0]["priority"] == 9


def test_hypothesis_run_returns_without_llm():
    """The full run() path works with no LLM and stores hypotheses."""
    async def _run():
        gen = _make_generator(router=None)
        result = await gen.run({
            "target": "app.test", "engagement_id": "eng-h",
            "assets": [{"type": "endpoint", "value": "https://app.test/login"}],
            "technologies": ["PHP"], "findings": [],
        })
        assert result["hypotheses_generated"] >= 1
        assert result["hypotheses_stored"] >= 1
        assert isinstance(result["hypotheses"], list)
    asyncio.run(_run())


def test_hypothesis_empty_when_no_surface():
    gen = _make_generator(router=None)
    assert gen._synth_hypotheses_from_assets("", [], [], []) == []
