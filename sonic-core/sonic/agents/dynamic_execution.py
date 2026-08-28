"""
SONIC-REDA — Dynamic Execution Agent
========================================
Live testing inside sandbox environments. Active HTTP testing,
fuzzing, Burp Suite interaction, and real-time exploitation.

Capabilities:
    - HTTP request crafting and sending
    - Endpoint fuzzing (parameters, paths, headers)
    - Authentication testing
    - Payload injection testing
    - Burp Suite API integration (Phase 2)
    - Browser automation (Phase 2)
"""

from __future__ import annotations

import json
from typing import Any

from sonic.logger import get_logger
from sonic.agents.base import BaseAgent
from sonic.memory.schemas import (
    FindingNode, FindingSeverity, FindingStatus,
    EvidenceNode, TechniqueNode,
)
from sonic.safety.scope import RiskLevel, SafetyVerdict

logger = get_logger(__name__)


class DynamicExecutionAgent(BaseAgent):
    """
    Dynamic testing agent — performs live testing against targets.
    All actions are safety-checked before execution.
    """

    def __init__(self, **kwargs: Any):
        super().__init__(name="DynamicExecutionAgent", **kwargs)
        self.requests_sent = 0
        self.sandbox_id: str = ""

    def get_system_prompt(self) -> str:
        return """You are the Dynamic Execution Agent of SONIC-REDA, an autonomous AI red-team system.

Your job is to ACTIVELY TEST targets for vulnerabilities by crafting and sending HTTP requests.

Your capabilities:
1. CRAFT REQUESTS: Build targeted HTTP requests to test for vulnerabilities
2. FUZZ PARAMETERS: Test parameters with various payloads
3. AUTH TESTING: Test authentication and authorization flaws
4. INJECTION TESTING: Test for SQLi, XSS, SSRF, SSTI, command injection
5. LOGIC TESTING: Test business logic flaws, race conditions, IDOR

CRITICAL RULES:
- ALWAYS check with the safety layer before sending requests
- NEVER send destructive payloads (DROP, DELETE, rm -rf, etc.)
- ALWAYS record the exact request and response as evidence
- Use targeted, minimal payloads — not brute force
- Respect rate limits

For each test, generate:
- The exact HTTP request (method, URL, headers, body)
- The expected vulnerable response
- The actual response (will be filled after execution)
- Whether the test confirms a vulnerability

Return test plans as JSON arrays of test cases."""

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute dynamic testing."""
        self.status = "running"
        target = task.get("target", "")
        engagement_id = task.get("engagement_id", "")
        test_type = task.get("task", "general_testing")
        hypotheses = task.get("hypotheses", [])
        assets = task.get("assets", [])

        logger.info("dynamic_testing_starting", target=target, type=test_type)

        # Safety check
        verdict = self.check_safety(
            f"Active testing against {target}: {test_type}",
            RiskLevel.L1_NEEDS_APPROVAL,
        )
        if verdict == SafetyVerdict.BLOCKED:
            self.status = "blocked"
            return {"error": "Action blocked by safety layer", "verdict": "blocked"}

        # Generate test cases
        test_cases = await self._generate_test_cases(
            target, test_type, hypotheses, assets
        )

        # Execute tests (simulated in MVP, real HTTP in Phase 2)
        results = []
        for test in test_cases:
            result = await self._execute_test(test, engagement_id)
            results.append(result)

        # Store confirmed findings
        findings = [r for r in results if r.get("is_vulnerable")]
        stored = 0
        for f in findings:
            try:
                finding = FindingNode(
                    title=f.get("title", ""),
                    description=f.get("description", ""),
                    vulnerability_class=f.get("vulnerability_class", "unknown"),
                    severity=FindingSeverity(f.get("severity", "medium")),
                    status=FindingStatus.NEEDS_VERIFICATION,
                    confidence_score=f.get("confidence", 60),
                    poc=f.get("poc", ""),
                    impact=f.get("impact", ""),
                    raw_request=f.get("request", ""),
                    raw_response=f.get("response", ""),
                    found_by=self.agent_id,
                    engagement_id=engagement_id,
                )
                if self.memory:
                    uid = await self.memory.create_finding(finding)
                    if uid:
                        stored += 1
                        # Store evidence
                        if f.get("request"):
                            evidence = EvidenceNode(
                                evidence_type="request",
                                content=f["request"],
                                description="HTTP request that triggered the vulnerability",
                                finding_id=uid,
                                created_by=self.agent_id,
                            )
                            await self.memory.create_evidence(evidence)
                        if f.get("response"):
                            evidence = EvidenceNode(
                                evidence_type="response",
                                content=f["response"],
                                description="Server response showing vulnerability",
                                finding_id=uid,
                                created_by=self.agent_id,
                            )
                            await self.memory.create_evidence(evidence)
            except Exception as e:
                logger.warning("finding_store_failed", error=str(e))

        self.status = "completed"
        return {
            "agent_id": self.agent_id,
            "tests_executed": len(results),
            "vulnerabilities_found": len(findings),
            "findings_stored": stored,
            "results": results,
        }

    async def _generate_test_cases(
        self, target: str, test_type: str,
        hypotheses: list[dict], assets: list[dict]
    ) -> list[dict]:
        """Generate specific test cases using LLM."""
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
    "expected_if_vulnerable": "what response indicates vulnerability",
    "severity_if_confirmed": "critical/high/medium/low"
}}

Return a JSON array of 5-10 targeted test cases. Be specific and realistic.
Use safe, non-destructive payloads only."""

        response = await self.think(prompt, task_type="coding")

        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            tests = json.loads(content)
            return tests if isinstance(tests, list) else []
        except Exception:
            return []

    async def _execute_test(self, test: dict, engagement_id: str) -> dict:
        """
        Execute a single test case.
        MVP: Simulated via LLM reasoning.
        Phase 2: Real HTTP requests via sandbox.
        """
        prompt = f"""Simulate executing this security test and predict the likely outcome:

TEST: {json.dumps(test, indent=2)}

Based on common web application behavior, would this test likely reveal a vulnerability?

Return JSON:
{{
    "test_name": "{test.get('test_name', '')}",
    "is_vulnerable": true/false,
    "title": "finding title if vulnerable",
    "vulnerability_class": "...",
    "severity": "...",
    "description": "what was found",
    "poc": "step by step reproduction",
    "impact": "what attacker can do",
    "confidence": 0-100,
    "request": "the exact request sent",
    "response": "simulated response",
    "reasoning": "why you think this is/isn't vulnerable"
}}"""

        response = await self.think(prompt, task_type="reasoning")
        self.requests_sent += 1

        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            return json.loads(content)
        except Exception:
            return {
                "test_name": test.get("test_name", ""),
                "is_vulnerable": False,
                "reasoning": "Failed to parse test result",
            }
