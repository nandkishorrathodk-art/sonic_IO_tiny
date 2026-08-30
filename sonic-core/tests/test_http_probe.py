"""
Tests for the real HTTP probing engine (sonic.tools.http_probe).

These verify that the probe:
  * default-denies private / loopback / metadata / out-of-scope targets
  * blocks destructive payloads
  * executes against allowed targets via an injected responder (no network)
  * detects vulnerability signals (reflection, errors, status, timing, CORS)
  * respects the rate limiter
"""

from __future__ import annotations

import asyncio
import pytest

from sonic.safety.scope import ScopeChecker, get_scope_checker
from sonic.safety.rate_limiter import EgressRateLimiter
from sonic.tools.http_probe import HTTPProbe, ProbeTest, detect_signals


# --------------------------------------------
# Helpers
# --------------------------------------------

def _test(url: str, **kw) -> ProbeTest:
    base = {"test_name": "t", "vulnerability_class": "XSS", "method": "GET",
            "url": url, "payload": "", "expected_if_vulnerable": ""}
    base.update(kw)
    return ProbeTest.from_dict(base)


def _responder_factory(status: int = 200, body: str = "", headers: dict | None = None,
                       elapsed: float = 0.01):
    async def _r(test: ProbeTest):
        from sonic.tools.http_probe import ProbeResult
        return ProbeResult(
            test_name=test.test_name, url=test.url, method=test.method,
            status_code=status, request="GET / HTTP/1.1",
            response_headers=headers or {}, response_body=body,
            response_body_length=len(body), elapsed_seconds=elapsed,
        )
    return _r


# --------------------------------------------
# Egress / scope / destructive guards
# --------------------------------------------

def test_probe_blocks_private_target():
    async def _run():
        async with HTTPProbe(responder=_responder_factory()) as probe:
            res = await probe.run(_test("http://10.0.0.5/admin"))
        assert res.blocked is True
        assert "egress denied" in res.block_reason
        assert res.verdict == "blocked"
    asyncio.run(_run())


def test_probe_blocks_metadata_target():
    async def _run():
        async with HTTPProbe(responder=_responder_factory()) as probe:
            res = await probe.run(_test("http://169.254.169.254/latest/meta-data/"))
        assert res.blocked is True
    asyncio.run(_run())


def test_probe_blocks_destructive_payload():
    async def _run():
        async with HTTPProbe(responder=_responder_factory()) as probe:
            res = await probe.run(_test("https://example.com/", payload="'; DROP TABLE users; --"))
        assert res.blocked is True
        assert "destructive" in res.block_reason
    asyncio.run(_run())


def test_probe_blocks_out_of_scope():
    async def _run():
        scope = get_scope_checker()
        scope_config = {"targets": {"domains": ["*.scope.test"], "ips": []},
                         "exclusions": {"domains": []}}
        async with HTTPProbe(
            scope_checker=scope, scope_config=scope_config,
            responder=_responder_factory(),
        ) as probe:
            res = await probe.run(_test("https://evil.example.com/"))
        assert res.blocked is True
        assert "out of scope" in res.block_reason
    asyncio.run(_run())


def test_probe_allows_in_scope_public():
    async def _run():
        scope = get_scope_checker()
        scope_config = {"targets": {"domains": ["*.scope.test"], "ips": []},
                         "exclusions": {"domains": []}}
        async with HTTPProbe(
            scope_checker=scope, scope_config=scope_config,
            responder=_responder_factory(200, "ok"),
        ) as probe:
            res = await probe.run(_test("https://app.scope.test/"))
        assert res.blocked is False
        assert res.status_code == 200
    asyncio.run(_run())


# --------------------------------------------
# Signal detection
# --------------------------------------------

def test_signal_reflection_detects_xss():
    test = _test("https://app.scope.test/", payload="<script>alert(1)</script>",
                 vulnerability_class="XSS")
    res = _responder_factory(200, body="...<script>alert(1)</script>...")
    # need to run through the probe to populate result, but detect_signals is pure
    from sonic.tools.http_probe import ProbeResult
    pr = ProbeResult(test_name="t", url=test.url, method="GET", status_code=200,
                     response_body="...<script>alert(1)</script>...", elapsed_seconds=0.01)
    signals, is_vuln, conf = detect_signals(test, pr)
    assert is_vuln is True
    assert "payload_reflected" in signals
    assert "executable_markup_reflected" in signals
    assert conf >= 40


def test_signal_error_marker_detects_sqli():
    test = _test("https://app.scope.test/", payload="'",
                 vulnerability_class="SQLi", expected_if_vulnerable="sql syntax")
    from sonic.tools.http_probe import ProbeResult
    pr = ProbeResult(test_name="t", url=test.url, method="GET", status_code=500,
                     response_body="You have an error in your SQL syntax near '")
    signals, is_vuln, _ = detect_signals(test, pr)
    assert is_vuln is True
    assert "expected_text_present" in signals
    assert "error_markers" in signals


def test_signal_status_code_match():
    test = _test("https://app.scope.test/", expected_if_vulnerable="status 500")
    from sonic.tools.http_probe import ProbeResult
    pr = ProbeResult(test_name="t", url=test.url, method="GET", status_code=500,
                     response_body="err")
    signals, is_vuln, _ = detect_signals(test, pr)
    assert "status_code_match" in signals
    assert is_vuln is True


def test_signal_clean_response_not_vulnerable():
    test = _test("https://app.scope.test/", payload="x", expected_if_vulnerable="reflected x")
    from sonic.tools.http_probe import ProbeResult
    pr = ProbeResult(test_name="t", url=test.url, method="GET", status_code=200,
                     response_body="nothing here")
    signals, is_vuln, conf = detect_signals(test, pr)
    assert is_vuln is False
    assert conf < 40


# --------------------------------------------
# End-to-end probe via responder
# --------------------------------------------

def test_probe_run_batch_confirms_finding():
    async def _run():
        async with HTTPProbe(
            responder=_responder_factory(200, body="<script>alert(1)</script>"),
        ) as probe:
            tests = [
                {"test_name": "xss1", "vulnerability_class": "XSS", "method": "GET",
                 "url": "https://example.com/q?x=<script>alert(1)</script>",
                 "payload": "<script>alert(1)</script>"},
                {"test_name": "clean", "vulnerability_class": "XSS", "method": "GET",
                 "url": "https://example.com/safe",
                 "payload": "probe", "expected_if_vulnerable": "reflected probe"},
            ]
            results = await probe.run_batch(tests)
        assert len(results) == 2
        assert results[0].is_vulnerable is True
        assert results[0].verdict == "vulnerable"
        assert results[1].is_vulnerable is False
        # evidence captured
        assert "GET" in results[0].request
        assert "<script>alert(1)</script>" in results[0].response_body
    asyncio.run(_run())


def test_probe_respects_rate_limiter():
    """The probe must call acquire/release on the rate limiter per host."""
    async def _run():
        limiter = EgressRateLimiter(default_rps=100, default_burst=100)
        async with HTTPProbe(
            rate_limiter=limiter, responder=_responder_factory(200, "ok"),
        ) as probe:
            await probe.run(_test("https://example.com/"))
        bucket = limiter._get_bucket("example.com")
        # released after the request
        assert bucket.active_connections == 0
    asyncio.run(_run())


def test_probe_error_handled_without_crash():
    async def boom(test: ProbeTest):
        raise RuntimeError("network exploded")

    async def _run():
        async with HTTPProbe(responder=boom) as probe:
            res = await probe.run(_test("https://example.com/"))
        assert res.verdict == "error"
        assert "network exploded" in res.error
    asyncio.run(_run())
