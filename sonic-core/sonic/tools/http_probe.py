"""
SONIC-REDA — Real HTTP Probing Engine
=======================================
The bridge between "the AI guesses a vulnerability" and "the AI PROVES it".

HTTPProbe sends REAL HTTP requests against in-scope, egress-allowed targets,
captures the full request/response as evidence, and detects vulnerability
signals (reflection, error markers, status anomalies, header indicators,
timing side-channels). It is the hands of the Dynamic Execution Agent.

Design contract
---------------
* DEFAULT-DENY at the network edge: every request is vetted by
  ``is_target_allowed`` (egress) and ``is_target_in_scope`` (authorization)
  AND the global ``EgressRateLimiter``. A probe never fires against a
  private, loopback, metadata, or out-of-scope target.
* No hallucinated traffic: if the guards refuse, the probe returns a
  BLOCKED result with the reason — it never silently succeeds.
* Two execution backends:
    - Direct (default): ``httpx.AsyncClient`` for dev / lab runs against
      public in-scope hosts. This is safe because the egress filter already
      rejects everything internal.
    - Sandbox: when a ``ComputeProvider`` + ``workspace_id`` are attached,
      the probe runs ``curl`` *inside* the isolated container, exactly like
      ``HTTPClientAdapter``. Production deployments use this.
* Deterministic injection point for tests: ``responder`` overrides the
  transport so unit tests never touch the network.
* Non-destructive only: payload denylist (DROP/DELETE/rm -rf/...) is
  enforced so an agent can never weaponize the probe for destruction.

This is what makes the system "think like a pentester and keep going":
each probe returns a concrete observation the reasoning loop can react to.
"""

from __future__ import annotations

import asyncio
import json
import re
import shlex
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from sonic.logger import get_logger
from sonic.safety.rate_limiter import EgressRateLimiter, get_rate_limiter
from sonic.safety.scope import ScopeChecker
from sonic.sandbox.egress import is_target_allowed

logger = get_logger(__name__)


# ============================================
# Data contracts
# ============================================

@dataclass
class ProbeTest:
    """A single active test case produced by the reasoning agent."""
    test_name: str = ""
    vulnerability_class: str = "unknown"
    method: str = "GET"
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    payload: str = ""
    expected_if_vulnerable: str = ""
    severity_if_confirmed: str = "medium"
    # internal bookkeeping
    rationale: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProbeTest:
        return cls(
            test_name=str(d.get("test_name", d.get("name", ""))),
            vulnerability_class=str(d.get("vulnerability_class", "unknown")),
            method=str(d.get("method", "GET")).upper(),
            url=str(d.get("url", "")),
            headers=dict(d.get("headers", {}) or {}),
            body=str(d.get("body", "") or ""),
            payload=str(d.get("payload", "") or ""),
            expected_if_vulnerable=str(d.get("expected_if_vulnerable", "") or ""),
            severity_if_confirmed=str(d.get("severity_if_confirmed", d.get("severity", "medium"))),
            rationale=str(d.get("rationale", "")),
        )


@dataclass
class ProbeResult:
    """The concrete observation returned by a single probe."""
    test_name: str
    url: str
    method: str
    status_code: int = 0
    request: str = ""
    response_headers: dict[str, str] = field(default_factory=dict)
    response_body: str = ""
    response_body_length: int = 0
    elapsed_seconds: float = 0.0
    redirected_to: str = ""
    error: str = ""
    blocked: bool = False
    block_reason: str = ""
    signals: dict[str, Any] = field(default_factory=dict)
    is_vulnerable: bool = False
    confidence: int = 0
    verdict: str = "not_vulnerable"  # vulnerable | ambiguous | not_vulnerable | blocked | error

    def to_evidence_dict(self) -> dict[str, str]:
        return {
            "request": self.request,
            "response": self._format_response(),
            "response_status": str(self.status_code),
            "response_headers": json.dumps(self.response_headers),
        }

    def _format_response(self) -> str:
        lines = [f"HTTP {self.status_code}"]
        for k, v in self.response_headers.items():
            lines.append(f"{k}: {v}")
        lines.append("")
        lines.append(self.response_body)
        return "\n".join(lines)


# ============================================
# Signal detection
# ============================================

_ERROR_MARKERS = [
    "sql syntax", "you have an error in your sql", "mysql_fetch", "ORA-",
    "psql:error", "pg::error", "unterminated string literal",
    "traceback (most recent call last)", "exception in", "undefined index",
    "warning: ", "fatal error", "stack trace", "system.invalidoperationexception",
    "<b>warning</b>", "mysqli_", "odbc_", "sqlstate",
]

_REFLECTION_PATTERNS = [
    re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),
]

_DESTRUCTIVE_PATTERNS = [
    re.compile(r"\bdrop\s+table\b", re.IGNORECASE),
    re.compile(r"\bdelete\s+from\b", re.IGNORECASE),
    re.compile(r"\btruncate\b", re.IGNORECASE),
    re.compile(r"\brm\s+-rf?\b", re.IGNORECASE),
    re.compile(r"\bshutdown\b", re.IGNORECASE),
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    re.compile(r":\(\)\s*\{", re.IGNORECASE),  # bash fork bomb
]


def _is_destructive(payload: str) -> bool:
    return any(p.search(payload) for p in _DESTRUCTIVE_PATTERNS)


def detect_signals(test: ProbeTest, result: ProbeResult) -> tuple[dict[str, Any], bool, int]:
    """
    Compare the real response against the test's expected indicators.

    Returns (signals, is_vulnerable, confidence). Multiple independent
    signal types are checked so the reasoning loop gets rich feedback.
    """
    signals: dict[str, Any] = {}
    body = result.response_body or ""
    headers = result.response_headers or {}
    expected = (test.expected_if_vulnerable or "").strip().lower()
    score = 0
    hits = 0

    # 1. Expected-text substring match (agent-specified oracle)
    if expected:
        if expected in body.lower():
            signals["expected_text_present"] = expected
            hits += 1
            score += 35
        elif expected in json.dumps(headers).lower():
            signals["expected_text_in_headers"] = expected
            hits += 1
            score += 25

    # 2. Status-code oracle ("status 500", "302", "403")
    status_match = re.search(r"\b(\d{3})\b", expected or "")
    if status_match:
        want = int(status_match.group(1))
        if result.status_code == want:
            signals["status_code_match"] = want
            hits += 1
            score += 45
        elif result.status_code and result.status_code != 200:
            signals["status_code_anomaly"] = result.status_code

    # 3. Payload reflection (XSS / SSTI / open redirect)
    payload = (test.payload or "").strip()
    if payload and payload in body:
        signals["payload_reflected"] = payload[:80]
        hits += 1
        score += 30
        # Stronger XSS signal: reflected with executable markup
        if any(p.search(body) for p in _REFLECTION_PATTERNS) and test.vulnerability_class.upper() in {
            "XSS", "SSTI", "HTMLI"
        }:
            signals["executable_markup_reflected"] = True
            score += 15

    # 4. Error-based markers (SQLi / RCE / debug disclosure)
    body_low = body.lower()
    err_hits = [m for m in _ERROR_MARKERS if m in body_low]
    if err_hits:
        signals["error_markers"] = err_hits
        hits += 1
        score += 30

    # 5. Timing side-channel (time-based blind SQLi / SSRF)
    time_match = re.search(r"(\d+(?:\.\d+)?)\s*(ms|s|seconds?)", expected or "")
    if time_match:
        try:
            unit = time_match.group(2)
            value = float(time_match.group(1))
            threshold = value if unit.startswith("s") else value / 1000.0
            if result.elapsed_seconds >= threshold:
                signals["timing_anomaly"] = round(result.elapsed_seconds, 3)
                hits += 1
                score += 25
        except (ValueError, IndexError):
            pass
    elif result.elapsed_seconds >= 5.0:
        signals["slow_response"] = round(result.elapsed_seconds, 3)
        score += 10

    # 6. Header indicators (CORS, CRLF, open redirect via Location)
    loc = headers.get("location") or headers.get("Location")
    if loc and test.vulnerability_class.upper() in {"OPEN_REDIRECT", "REDIRECT", "SSRF"}:
        if payload and payload in loc:
            signals["redirect_contains_payload"] = loc
            hits += 1
            score += 30
    acao = headers.get("access-control-allow-origin") or headers.get("Access-Control-Allow-Origin")
    if acao and acao != "" and test.vulnerability_class.upper() == "CORS":
        if acao == "*" or (acao != "null" and payload and payload in acao):
            signals["cors_reflects_origin"] = acao
            hits += 1
            score += 25

    is_vulnerable = hits >= 1 and score >= 40
    confidence = min(100, score)
    return signals, is_vulnerable, confidence


# ============================================
# Probe engine
# ============================================

ResponderFn = Callable[[ProbeTest], Awaitable["ProbeResult"]]


class HTTPProbe:
    """
    Sends real, safety-vetted HTTP requests and turns responses into
    evidence-backed observations for the reasoning loop.
    """

    def __init__(
        self,
        *,
        scope_checker: ScopeChecker | None = None,
        rate_limiter: EgressRateLimiter | None = None,
        sandbox_provider: Any = None,
        workspace_id: str = "",
        responder: ResponderFn | None = None,
        scope_config: dict | None = None,
        timeout: float = 15.0,
        max_body_capture: int = 16384,
    ):
        self.scope = scope_checker
        self.rate_limiter = rate_limiter or get_rate_limiter()
        self.sandbox = sandbox_provider
        self.workspace_id = workspace_id
        self.responder = responder  # test injection point
        self.scope_config = scope_config or {}
        self.timeout = timeout
        self.max_body_capture = max_body_capture
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> HTTPProbe:
        if self.responder is None and self.sandbox is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=False,
                verify=False,
            )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # --------------------------------------------
    # Public API
    # --------------------------------------------

    async def run(self, test: ProbeTest | dict[str, Any]) -> ProbeResult:
        """Execute one test case and return a concrete observation."""
        if isinstance(test, dict):
            test = ProbeTest.from_dict(test)
        return await self._run_one(test)

    async def run_batch(self, tests: list[dict[str, Any]]) -> list[ProbeResult]:
        """Execute many tests, each independently safety-checked."""
        probe_tests = [ProbeTest.from_dict(t) if isinstance(t, dict) else t for t in tests]
        return await asyncio.gather(*[self._run_one(t) for t in probe_tests])

    # --------------------------------------------
    # Guards
    # --------------------------------------------

    def _guard(self, test: ProbeTest) -> str | None:
        """Return a block reason, or None if allowed."""
        url = (test.url or "").strip()
        if not url:
            return "empty URL"

        if _is_destructive(test.payload or "") or _is_destructive(test.body or ""):
            return "destructive payload blocked"

        host = urlparse(url).hostname or ""
        if not host:
            return "unparseable URL"

        allowed, reason = is_target_allowed(url)
        if not allowed:
            return f"egress denied: {reason}"

        if self.scope is not None and self.scope_config:
            if not self.scope.is_target_in_scope(host, self.scope_config):
                return f"out of scope: {host}"
        return None

    # --------------------------------------------
    # Execution backends
    # --------------------------------------------

    async def _run_one(self, test: ProbeTest) -> ProbeResult:
        base = ProbeResult(
            test_name=test.test_name or test.url,
            url=test.url,
            method=test.method,
        )

        # 1. Safety guard
        block = self._guard(test)
        if block:
            base.blocked = True
            base.block_reason = block
            base.verdict = "blocked"
            logger.info("probe_blocked", test=test.test_name, reason=block)
            return base

        # 2. Rate limit
        host = urlparse(test.url).hostname or ""
        acquired = False
        try:
            await self.rate_limiter.acquire(host)
            acquired = True
        except Exception as e:  # never let the limiter crash a probe
            logger.warning("rate_limiter_failed", host=host, error=str(e))

        try:
            if self.responder is not None:
                res = await self.responder(test)
            elif self.sandbox is not None and self.workspace_id:
                res = await self._run_via_sandbox(test)
            else:
                res = await self._run_via_httpx(test)
        except Exception as e:  # noqa: BLE001 — network is unpredictable
            res = base
            res.error = f"{type(e).__name__}: {e}"
            res.verdict = "error"
            if acquired:
                await self.rate_limiter.release(host)
            return res

        # Every backend returns a populated ProbeResult; release the limiter
        # here so responder/sandbox/httpx paths are treated uniformly.
        if acquired:
            await self.rate_limiter.release(host, status_code=res.status_code or None)

        # 3. Signal detection
        res.signals, res.is_vulnerable, res.confidence = detect_signals(test, res)
        res.verdict = (
            "vulnerable" if res.is_vulnerable
            else ("ambiguous" if res.signals else "not_vulnerable")
        )
        return res

    async def _run_via_httpx(self, test: ProbeTest) -> ProbeResult:
        assert self._client is not None, "use `async with HTTPProbe(...) as probe:`"
        started = time.monotonic()
        resp = await self._client.request(
            method=test.method,
            url=test.url,
            headers=test.headers or None,
            content=test.body or None,
        )
        elapsed = time.monotonic() - started
        return self._build_from_httpx(test, resp, elapsed)

    def _build_from_httpx(self, test: ProbeTest, resp: httpx.Response, elapsed: float) -> ProbeResult:
        body = resp.text or ""
        captured = body[: self.max_body_capture]
        # request reconstruction (evidence)
        req_lines = [f"{test.method} {resp.request.url.path}?{resp.request.url.query} HTTP/1.1"]
        req_lines.append(f"Host: {resp.request.url.host}")
        for k, v in (test.headers or {}).items():
            req_lines.append(f"{k}: {v}")
        if test.body:
            req_lines.append("")
            req_lines.append(test.body)
        request_str = "\n".join(req_lines)

        headers = dict(resp.headers.items())
        return ProbeResult(
            test_name=test.test_name or test.url,
            url=str(resp.request.url),
            method=test.method,
            status_code=resp.status_code,
            request=request_str,
            response_headers=headers,
            response_body=captured,
            response_body_length=len(body),
            elapsed_seconds=round(elapsed, 3),
            redirected_to=str(resp.headers.get("location", "")),
        )

    async def _run_via_sandbox(self, test: ProbeTest) -> ProbeResult:
        """Execute through the isolated ComputeProvider (curl inside container)."""
        cmd = self._build_curl_command(test)
        started = time.monotonic()
        exec_res = await self.sandbox.execute(
            workspace_id=self.workspace_id,
            command=cmd,
            timeout=int(self.timeout),
        )
        elapsed = time.monotonic() - started
        return self._parse_curl_output(test, exec_res, elapsed)

    def _build_curl_command(self, test: ProbeTest) -> str:
        parts = ["curl", "-s", "-i", "--max-time", str(int(self.timeout)), "-X", test.method]
        for k, v in (test.headers or {}).items():
            parts += ["-H", shlex.quote(f"{k}: {v}")]
        if test.body:
            parts += ["--data-raw", shlex.quote(test.body)]
        parts.append(shlex.quote(test.url))
        return " ".join(parts)

    def _parse_curl_output(self, test: ProbeTest, exec_res: Any, elapsed: float) -> ProbeResult:
        raw = exec_res.stdout or ""
        status_code = 0
        headers: dict[str, str] = {}
        body = raw
        if "\r\n\r\n" in raw:
            head, body = raw.split("\r\n\r\n", 1)
        elif "\n\n" in raw:
            head, body = raw.split("\n\n", 1)
        else:
            head = raw
        for i, line in enumerate(head.splitlines()):
            if i == 0 and "HTTP/" in line:
                try:
                    status_code = int(line.split()[1])
                except (IndexError, ValueError):
                    pass
            elif ": " in line:
                k, v = line.split(": ", 1)
                headers[k.strip()] = v.strip()
        return ProbeResult(
            test_name=test.test_name or test.url,
            url=test.url,
            method=test.method,
            status_code=status_code,
            request=self._build_curl_command(test),
            response_headers=headers,
            response_body=body[: self.max_body_capture],
            response_body_length=len(body),
            elapsed_seconds=round(elapsed, 3),
            redirected_to=headers.get("location", headers.get("Location", "")),
            error=(exec_res.stderr or "") if exec_res.exit_code != 0 else "",
        )
