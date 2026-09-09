"""
SONIC-REDA — Dynamic Execution Agent (Autonomous Pentest Loop)
================================================================
The agent that actually TESTS the target instead of guessing.

It runs a real Observe→Think→Act→Re-probe loop (a ReAct-style attack loop):

    generate initial test queue
      → fire REAL HTTP probes (HTTPProbe) against in-scope targets
      → capture concrete request/response as evidence
      → LLM triages each observation: confirmed? ambiguous? follow-up test?
      → confirmed signals become findings WITH evidence
      → ambiguous/failed observations spawn new tests (chaining / re-attempts)
      → repeat until exploitation confirmed, budget exhausted, or queue drained

This is what makes SONIC-REDA "think like a pentester": it does NOT stop after
one output. It keeps probing, reacting to real responses, pivoting, and
chaining findings until the kill-chain is established or the budget runs out.

Capabilities:
    - Live HTTP testing via the isolated probe (egress + scope + rate-limited)
    - Vulnerability signal detection (reflection, errors, status, timing, CORS)
    - Autonomous test chaining and re-attempts on failure
    - Evidence-backed findings (request + response attached for the Verifier)
    - Failed-method tracking for the replanner
"""

from __future__ import annotations

import json
from typing import Any

from sonic.agents.base import BaseAgent
from sonic.llm.prompts import DYNAMIC_EXECUTION_SYSTEM
from sonic.logger import get_logger
from sonic.memory.schemas import (
    EvidenceNode,
    FindingNode,
    FindingSeverity,
    FindingStatus,
)
from sonic.safety.rate_limiter import get_rate_limiter
from sonic.safety.scope import RiskLevel, SafetyVerdict
from sonic.agents.http_probe import HTTPProbe, ProbeResult, ProbeTest

logger = get_logger(__name__)


class DynamicExecutionAgent(BaseAgent):
    """
    Dynamic testing agent — performs live testing against targets.
    All actions are safety-checked before execution.
    """

    def __init__(
        self,
        *,
        sandbox_provider: Any = None,
        workspace_id: str = "",
        scope_config: dict | None = None,
        max_iterations: int = 8,
        max_requests: int = 40,
        **kwargs: Any,
    ):
        super().__init__(name="DynamicExecutionAgent", **kwargs)
        self.requests_sent = 0
        self.sandbox_id: str = workspace_id
        self.sandbox_provider = sandbox_provider
        self.workspace_id = workspace_id
        self.scope_config = scope_config or {}
        self.max_iterations = max_iterations
        self.max_requests = max_requests

    def get_system_prompt(self) -> str:
        return DYNAMIC_EXECUTION_SYSTEM

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the autonomous pentest loop.

        Observe → Think → Act → Re-probe until exploitation is confirmed or
        the request/iteration budget is exhausted. Every confirmed finding
        carries the real request+response as evidence for the Verifier.
        """
        self.status = "running"
        target = task.get("target", "")
        engagement_id = task.get("engagement_id", "")
        test_type = task.get("task", "general_testing")
        hypotheses = task.get("hypotheses", [])
        assets = task.get("assets", [])

        logger.info("dynamic_testing_starting", target=target, type=test_type)

        # Safety check (fail-closed)
        verdict = self.check_safety(
            f"Active testing against {target}: {test_type}",
            RiskLevel.L1_NEEDS_APPROVAL,
        )
        if verdict == SafetyVerdict.BLOCKED:
            self.status = "blocked"
            return {"error": "Action blocked by safety layer", "verdict": "blocked"}

        # Resolve scope config (task may carry it, else fall back to constructor)
        scope_config = task.get("scope_config") or self.scope_config or {"target": target}

        # Build the real probe. The probe owns egress/scope/rate-limit guards.
        probe_kwargs: dict[str, Any] = {
            "scope_checker": self.scope,
            "rate_limiter": get_rate_limiter(),
            "scope_config": scope_config,
        }
        if self.sandbox_provider is not None and self.workspace_id:
            probe_kwargs["sandbox_provider"] = self.sandbox_provider
            probe_kwargs["workspace_id"] = self.workspace_id

        # Generate the initial test queue from the LLM (or seeded/fallback tests).
        seeded_tests = task.get("tests")
        if seeded_tests:
            test_queue: list[dict[str, Any]] = list(seeded_tests)
        else:
            test_queue: list[dict[str, Any]] = list(
                await self._generate_test_cases(target, test_type, hypotheses, assets)
            )
            if not test_queue:
                # Seed a minimal probe from known endpoints so the agent can still act.
                test_queue = self._seed_tests_from_assets(target, assets)

        findings: list[dict[str, Any]] = []
        failed_attempts: list[dict[str, Any]] = []
        observations: list[dict[str, Any]] = []
        stored = 0
        requests_made = 0
        seen_followups = 0
        max_iterations = task.get("max_iterations", self.max_iterations)
        max_requests = task.get("max_requests", self.max_requests)

        async with HTTPProbe(**probe_kwargs) as probe:
            for iteration in range(max_iterations):
                if not test_queue or requests_made >= max_requests:
                    break

                # Execute the current batch (bounded) concurrently.
                batch_dicts = test_queue[: 5]
                test_queue = test_queue[5:]
                batch = [ProbeTest.from_dict(t) if isinstance(t, dict) else t
                         for t in batch_dicts]
                batch_results = await probe.run_batch(batch)
                requests_made += len(batch_results)

                # Triage every observation and decide follow-ups.
                for test, result in zip(batch, batch_results, strict=False):
                    obs = self._observation_to_dict(test, result, iteration)
                    observations.append(obs)
                    self.requests_sent += 1

                    triage = await self._triage(test, result, target, scope_config)
                    obs["triage"] = triage

                    if triage["verdict"] == "confirmed" or result.is_vulnerable:
                        finding = self._result_to_finding(test, result, triage, target)
                        findings.append(finding)
                        stored += await self._persist_finding(finding, engagement_id)
                    elif triage["verdict"] == "ambiguous":
                        failed_attempts.append({
                            "test": test.test_name, "reason": "ambiguous",
                            "signals": result.signals, "status": result.status_code,
                        })
                    elif triage["verdict"] in ("error", "blocked"):
                        failed_attempts.append({
                            "test": test.test_name, "reason": triage["verdict"],
                            "detail": result.error or result.block_reason,
                        })

                    # Chain: queue follow-up tests the loop generated.
                    follow_ups = triage.get("follow_up_tests") or []
                    if follow_ups and isinstance(follow_ups, list):
                        test_queue.extend(follow_ups[:5])
                        seen_followups += len(follow_ups[:5])

                logger.info(
                    "dynamic_loop_iteration",
                    iteration=iteration + 1,
                    requests=requests_made,
                    findings=len(findings),
                    queue_remaining=len(test_queue),
                )

        self.status = "completed"
        return {
            "agent_id": self.agent_id,
            "target": target,
            "tests_executed": requests_made,
            "vulnerabilities_found": len(findings),
            "findings_stored": stored,
            "follow_ups_generated": seen_followups,
            "iterations_run": min(max_iterations, max(1, (requests_made + 4) // 5)) if requests_made else 0,
            "findings": findings,
            "failed_attempts": failed_attempts,
            "observations": observations,
        }

    # ============================================
    # Probe helpers
    # ============================================

    def _seed_tests_from_assets(self, target: str, assets: list[dict]) -> list[dict]:
        """If the LLM produced no plan, seed minimal probes from discovered URLs."""
        urls = [a.get("value") for a in assets if a.get("type") in ("url", "endpoint") and a.get("value")]
        if not urls and target:
            urls = [target]
        seeded = []
        for u in urls[:5]:
            if not u.startswith("http"):
                u = "https://" + u.lstrip("/")
            seeded.append({
                "test_name": f"baseline_probe_{u}",
                "vulnerability_class": "INFO",
                "method": "GET",
                "url": u,
                "expected_if_vulnerable": "",
                "severity_if_confirmed": "info",
            })
        return seeded

    def _observation_to_dict(self, test: ProbeTest, result: ProbeResult, iteration: int) -> dict:
        return {
            "iteration": iteration,
            "test_name": result.test_name,
            "url": result.url,
            "method": result.method,
            "status_code": result.status_code,
            "blocked": result.blocked,
            "block_reason": result.block_reason,
            "error": result.error,
            "verdict": result.verdict,
            "is_vulnerable": result.is_vulnerable,
            "confidence": result.confidence,
            "signals": result.signals,
            "elapsed_seconds": result.elapsed_seconds,
            "response_preview": (result.response_body or "")[:500],
        }

    def _result_to_finding(
        self, test: ProbeTest, result: ProbeResult, triage: dict, target: str
    ) -> dict:
        sev = (triage.get("adjusted_severity") or test.severity_if_confirmed or "medium").lower()
        try:
            FindingSeverity(sev)
        except ValueError:
            sev = "medium"
        return {
            "title": f"{test.vulnerability_class} via {test.test_name or test.url}",
            "description": triage.get("reasoning") or (
                f"Confirmed {test.vulnerability_class} signal against {result.url}: "
                f"{json.dumps(result.signals)}"
            ),
            "vulnerability_class": test.vulnerability_class or "unknown",
            "severity": sev,
            "confidence": max(result.confidence, int(triage.get("confidence", 0) or 0)),
            "poc": test.payload or "",
            "impact": triage.get("impact", ""),
            "request": result.request,
            "response": result._format_response(),
            "status_code": result.status_code,
            "url": result.url,
            "signals": result.signals,
        }

    async def _persist_finding(self, finding: dict, engagement_id: str) -> int:
        if not self.memory:
            return 0
        try:
            node = FindingNode(
                title=finding.get("title", ""),
                description=finding.get("description", ""),
                vulnerability_class=finding.get("vulnerability_class", "unknown"),
                severity=FindingSeverity(finding.get("severity", "medium")),
                status=FindingStatus.NEEDS_VERIFICATION,
                confidence_score=finding.get("confidence", 60),
                poc=finding.get("poc", ""),
                impact=finding.get("impact", ""),
                raw_request=finding.get("request", ""),
                raw_response=finding.get("response", ""),
                found_by=self.agent_id,
                engagement_id=engagement_id,
                target_asset=finding.get("url", ""),
            )
            uid = await self.memory.create_finding(node)
            if not uid:
                return 0
            if finding.get("request"):
                await self.memory.create_evidence(EvidenceNode(
                    evidence_type="request", content=finding["request"],
                    description="HTTP request that triggered the vulnerability",
                    finding_id=uid, created_by=self.agent_id,
                ))
            if finding.get("response"):
                await self.memory.create_evidence(EvidenceNode(
                    evidence_type="response", content=finding["response"],
                    description="Server response showing the vulnerability",
                    finding_id=uid, created_by=self.agent_id,
                ))
            return 1
        except Exception as e:
            logger.warning("finding_store_failed", error=str(e))
            return 0

    async def _triage(
        self, test: ProbeTest, result: ProbeResult, target: str, scope_config: dict
    ) -> dict:
        """
        Decide what an observation means and what to do next.

        Uses the LLM when available to reason about chaining/re-attempts;
        otherwise falls back to the probe's deterministic signal detection
        so the loop is still useful with no LLM configured.
        """
        # Fast path: the probe already proved it.
        if result.is_vulnerable:
            base = {
                "verdict": "confirmed",
                "confidence": result.confidence,
                "reasoning": f"Probe signals matched: {json.dumps(result.signals)}",
                "adjusted_severity": test.severity_if_confirmed or "medium",
                "impact": "",
                "follow_up_tests": [],
            }
            # Ask the LLM whether to chain deeper (optional, best-effort).
            if self.router is not None:
                chained = await self._llm_triage(test, result, target, chain=True)
                if chained:
                    base["reasoning"] = chained.get("reasoning", base["reasoning"])
                    base["follow_up_tests"] = chained.get("follow_up_tests", [])
                    base["impact"] = chained.get("impact", "")
            return base

        if result.blocked or result.verdict == "blocked":
            return {"verdict": "blocked", "confidence": 0,
                    "reasoning": result.block_reason, "follow_up_tests": []}
        if result.verdict == "error":
            return {"verdict": "error", "confidence": 0,
                    "reasoning": result.error, "follow_up_tests": []}

        # Ask the LLM to interpret an ambiguous/clean response (best-effort).
        if self.router is not None:
            llm = await self._llm_triage(test, result, target, chain=False)
            if llm:
                return llm

        # Deterministic fallback.
        if result.signals:
            return {
                "verdict": "ambiguous",
                "confidence": result.confidence,
                "reasoning": f"Partial signals: {json.dumps(result.signals)}",
                "follow_up_tests": [],
            }
        return {
            "verdict": "not_vulnerable",
            "confidence": 10,
            "reasoning": "No vulnerability signal in the real response.",
            "follow_up_tests": [],
        }

    async def _llm_triage(
        self, test: ProbeTest, result: ProbeResult, target: str, *, chain: bool
    ) -> dict | None:
        """LLM interpretation of an observation; returns None on any failure."""
        instruction = (
            "This observation CONFIRMED a vulnerability. Decide if a deeper "
            "follow-up test should chain off it (e.g. escalate to RCE, exfil "
            "data, pivot). Return follow_up_tests to chain, or [] to stop."
            if chain else
            "Interpret this real observation. Is it vulnerable, ambiguous, or "
            "clean? If ambiguous, return follow_up_tests to re-attempt with a "
            "variant payload."
        )
        obs = {
            "test": test.test_name,
            "vulnerability_class": test.vulnerability_class,
            "url": result.url,
            "method": result.method,
            "status_code": result.status_code,
            "signals": result.signals,
            "response_preview": (result.response_body or "")[:1500],
            "elapsed_seconds": result.elapsed_seconds,
        }
        prompt = f"""{instruction}

REAL OBSERVATION:
{json.dumps(obs, indent=2)}

Respond ONLY with JSON:
{{
  "verdict": "confirmed|ambiguous|not_vulnerable|error|blocked",
  "confidence": 0-100,
  "reasoning": "cite the real response",
  "impact": "short impact statement if confirmed, else empty",
  "adjusted_severity": "critical|high|medium|low|info",
  "follow_up_tests": [ {{ "test_name": "...", "vulnerability_class": "...", "method": "GET", "url": "...", "headers": {{}}, "body": "", "payload": "...", "expected_if_vulnerable": "...", "severity_if_confirmed": "..." }} ]
}}
"""
        try:
            response = await self.think(prompt, task_type="verification")
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            data = json.loads(content)
            if isinstance(data, dict):
                data.setdefault("follow_up_tests", [])
                data.setdefault("confidence", result.confidence)
                return data
        except Exception as e:
            logger.debug("llm_triage_failed", error=str(e))
        return None

    async def _generate_test_cases(
        self, target: str, test_type: str,
        hypotheses: list[dict], assets: list[dict]
    ) -> list[dict]:
        """Generate the initial test queue using LLM reasoning."""
        context = ""
        if hypotheses:
            context += f"\nHYPOTHESES TO TEST:\n{json.dumps(hypotheses[:5], indent=2)}"
        if assets:
            context += f"\nKNOWN ASSETS:\n{json.dumps(assets[:10], indent=2)}"

        prompt = f"""Generate specific security test cases for: {target}
Test type: {test_type}
{context}

For each test case, provide:
{{
    "test_name": "descriptive name",
    "vulnerability_class": "XSS/SQLi/IDOR/...",
    "method": "GET/POST/PUT/DELETE",
    "url": "full URL to test",
    "headers": {{}},
    "body": "request body if any",
    "payload": "the actual test payload",
    "expected_if_vulnerable": "SPECIFIC oracle: reflected string, status code, error marker, timing, or header value",
    "severity_if_confirmed": "critical/high/medium/low"
}}

Return a JSON array of 5-10 targeted test cases. Be specific and realistic.
Use safe, non-destructive payloads only. The probe will fire these for real."""

        if self.router is None:
            return []
        try:
            response = await self.think(prompt, task_type="coding")
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            tests = json.loads(content)
            return tests if isinstance(tests, list) else []
        except Exception as e:
            logger.warning("test_generation_failed", error=str(e))
            return []

    async def _execute_test(self, test: dict, engagement_id: str) -> dict:
        """
        Execute a single test case against the target with a real probe.

        Kept for backward compatibility with the worker / swarm dispatch paths.
        The full run() loop calls the probe directly; this entrypoint runs one
        probe synchronously and returns a legacy-shaped result dict.
        """
        scope_config = self.scope_config or {}
        async with HTTPProbe(
            scope_checker=self.scope,
            rate_limiter=get_rate_limiter(),
            sandbox_provider=self.sandbox_provider,
            workspace_id=self.workspace_id,
            scope_config=scope_config,
        ) as probe:
            result = await probe.run(test)

        is_vuln = result.is_vulnerable
        return {
            "test_name": result.test_name,
            "is_vulnerable": is_vuln,
            "status": "BLOCKED" if result.blocked else ("VULNERABLE" if is_vuln else "OK"),
            "request": result.request,
            "response": result._format_response(),
            "status_code": result.status_code,
            "signals": result.signals,
            "confidence": result.confidence,
            "verdict": result.verdict,
            "error": result.error,
            "block_reason": result.block_reason,
            "reasoning": result.block_reason or result.error or (
                "Confirmed via real HTTP probe" if is_vuln else "No vulnerability signal"
            ),
        }
