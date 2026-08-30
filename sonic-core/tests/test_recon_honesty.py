"""
Recon honesty — done-gate tests.

Closes the PLAN.md audit item: the recon agent IMAGINED subdomains by asking
the LLM "what subdomains likely exist? (api., admin., staging., dev., mail.)"
and presented those guesses as discovered assets. That is hallucinated attack
surface. Now real subdomains come from Certificate Transparency logs
(``discovered_by: "certificate_transparency"``), and LLM-suggested candidates
are clearly labeled ``discovered_by: "llm_hypothesis"`` with
``confirmed: False`` — never presented as observed truth.

    [x] real CT subdomains (when the source is reachable) are returned with
        discovered_by = certificate_transparency.
    [x] LLM-suggested assets are labeled discovered_by = llm_hypothesis and
        confirmed = False (NOT presented as observed).
    [x] an LLM-suggested subdomain already found via CT is deduped (kept as
        the real, confirmed one).
    [x] when the CT source is blocked (private), no real subdomains are
        invented; the method returns [] rather than hallucinating.
    [x] with no router, only real CT assets (if any) are returned — no
        imagined fallback.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from sonic.agents.recon import ReconAgent
import sonic.tools.http_probe as http_probe


class _FakeRouter:
    """Returns a canned JSON asset list for the LLM hypothesis step."""
    def __init__(self, content: str):
        self._content = content
    async def complete(self, request, task_type=None, **kw):
        return type("R", (), {"content": self._content})()


def _llm_router(assets):
    return _FakeRouter(json.dumps(list(assets)))


def _ct_result(names):
    """Build a fake crt.sh JSON body (list of {name_value})."""
    return json.dumps([{"name_value": n} for n in names])


class _FakeProbe:
    """Async-context-manager probe returning a canned ProbeResult-like."""
    def __init__(self, result):
        self._result = result
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return None
    async def run(self, test):
        return self._result


def _patch_probe(result):
    """Patch the lazy `from sonic.tools.http_probe import HTTPProbe, ProbeTest`
    by replacing both names on the source module (the import reads them at
    call time, so the patched values are picked up)."""
    from unittest.mock import patch
    return (
        patch.object(http_probe, "HTTPProbe", return_value=_FakeProbe(result)),
        patch.object(http_probe, "ProbeTest", http_probe.ProbeTest),
    )


def _res(body, blocked=False, error=""):
    return type("Res", (), {
        "blocked": blocked, "error": error, "response_body": body,
    })()


def test_real_ct_subdomains_labeled_certificate_transparency():
    router = _llm_router([{"type": "subdomain", "value": "api.example.com",
                           "name": "x", "metadata": {}}])
    agent = ReconAgent(model_router=router)
    p_http, p_test = _patch_probe(_res(_ct_result(
        ["api.example.com", "staging.example.com", "*.example.com"])))
    with p_http, p_test:
        assets = asyncio.run(agent._discover_assets("example.com", "full_recon", "eng-1"))
    real = [a for a in assets if a["metadata"].get("discovered_by") == "certificate_transparency"]
    assert {a["value"] for a in real} == {"api.example.com", "staging.example.com"}
    # Wildcards stripped, no bare apex, no duplicates.
    assert all(a["metadata"].get("confirmed", True) for a in real)


def test_llm_assets_labeled_hypothesis_not_observed():
    router = _llm_router([
        {"type": "technology", "value": "nginx", "name": "x", "metadata": {"version": "1.0"}},
        {"type": "subdomain", "value": "admin.example.com", "name": "x", "metadata": {}},
    ])
    agent = ReconAgent(model_router=router)
    # CT source blocked (private) so no real subdomains; only LLM hypotheses.
    p_http, p_test = _patch_probe(_res("", blocked=True, error="egress_blocked"))
    with p_http, p_test:
        assets = asyncio.run(agent._discover_assets("example.com", "full_recon", "eng-1"))
    hyp = [a for a in assets if a["metadata"].get("discovered_by") == "llm_hypothesis"]
    assert {a["value"] for a in hyp} == {"nginx", "admin.example.com"}
    assert all(a["metadata"].get("confirmed") is False for a in hyp)


def test_llm_subdomain_deduped_against_real_ct():
    # CT finds api.example.com; LLM ALSO suggests api.example.com (hypothesis).
    router = _llm_router([{"type": "subdomain", "value": "api.example.com",
                           "name": "x", "metadata": {}}])
    agent = ReconAgent(model_router=router)
    p_http, p_test = _patch_probe(_res(_ct_result(["api.example.com"])))
    with p_http, p_test:
        assets = asyncio.run(agent._discover_assets("example.com", "full_recon", "eng-1"))
    # Only ONE api.example.com — the real (CT) one, not a duplicate hypothesis.
    api = [a for a in assets if a["value"] == "api.example.com"]
    assert len(api) == 1
    assert api[0]["metadata"]["discovered_by"] == "certificate_transparency"


def test_ct_source_blocked_returns_no_real_subdomains():
    router = _llm_router([])  # empty LLM response
    agent = ReconAgent(model_router=router)
    p_http, p_test = _patch_probe(_res("", blocked=True, error="private_network"))
    with p_http, p_test:
        assets = asyncio.run(agent._discover_assets("example.com", "full_recon", "eng-1"))
    real = [a for a in assets if a["metadata"].get("discovered_by") == "certificate_transparency"]
    assert real == []  # never invents subdomains when CT is unavailable


def test_no_router_returns_only_real_ct_assets():
    agent = ReconAgent(model_router=None)
    p_http, p_test = _patch_probe(_res(_ct_result(["dev.example.com"])))
    with p_http, p_test:
        assets = asyncio.run(agent._discover_assets("example.com", "full_recon", "eng-1"))
    # No router → no LLM hypotheses; only the real CT subdomain.
    assert len(assets) == 1
    assert assets[0]["value"] == "dev.example.com"
    assert assets[0]["metadata"]["discovered_by"] == "certificate_transparency"
