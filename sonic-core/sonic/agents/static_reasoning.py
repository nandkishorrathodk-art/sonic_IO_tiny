"""
SONIC-REDA — Static Reasoning Agent
=======================================
Code analysis, configuration review, pattern matching, dataflow analysis.
Analyzes source code and configurations for vulnerabilities WITHOUT running anything.

Capabilities:
    - Source code vulnerability detection
    - Configuration misidentification
    - Dataflow tracing (source → sink)
    - Hardcoded secret detection
    - Dependency vulnerability checking
    - API specification analysis
"""

from __future__ import annotations

import json
from typing import Any

from sonic.agents.base import BaseAgent
from sonic.logger import get_logger
from sonic.memory.schemas import FindingNode, FindingSeverity, FindingStatus, HypothesisNode

logger = get_logger(__name__)


class StaticReasoningAgent(BaseAgent):
    """
    Static analysis agent — finds vulnerabilities through code/config reasoning.
    No live testing. Pure analysis using LLM reasoning.
    """

    def __init__(self, **kwargs: Any):
        super().__init__(name="StaticReasoningAgent", **kwargs)

    def get_system_prompt(self) -> str:
        return """You are the Static Reasoning Agent of SONIC — an Autonomous Self-Evolving Penetration Architect (A-SEA).

Your job is to analyze code, configurations, and application logic to find vulnerabilities WITHOUT executing anything.

Your analysis techniques:
1. SOURCE-SINK ANALYSIS: Trace user input from entry points to dangerous functions
2. PATTERN MATCHING: Identify known vulnerable code patterns
3. CONFIG REVIEW: Check for misconfigurations (CORS, CSP, cookies, headers)
4. SECRET DETECTION: Find hardcoded credentials, API keys, tokens
5. LOGIC ANALYSIS: Identify business logic flaws, race conditions, IDOR patterns
6. DEPENDENCY AUDIT: Check for known vulnerable libraries/versions

For each finding, you MUST provide:
- title: Clear description of the vulnerability
- vulnerability_class: Standard class (XSS, SQLi, IDOR, SSRF, etc.)
- severity: critical/high/medium/low/info
- description: Detailed explanation of the vulnerability
- poc: How to reproduce it (request, payload, steps)
- impact: What an attacker could do
- confidence: 0-100 (how sure are you?)

Return findings as a JSON array. NO findings without evidence.
If you're unsure, create a HYPOTHESIS instead of a FINDING."""

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute static analysis."""
        self.status = "running"
        target = task.get("target", "")
        engagement_id = task.get("engagement_id", "")
        code = task.get("code", "")
        config = task.get("config", "")
        assets = task.get("assets", [])
        analysis_type = task.get("task", "full_analysis")

        logger.info("static_analysis_starting", target=target, type=analysis_type)

        # Analyze based on available data
        findings = []
        hypotheses = []

        if code:
            code_results = await self._analyze_code(code, target, engagement_id)
            findings.extend(code_results.get("findings", []))
            hypotheses.extend(code_results.get("hypotheses", []))

        if config:
            config_results = await self._analyze_config(config, target, engagement_id)
            findings.extend(config_results.get("findings", []))

        if assets:
            asset_results = await self._analyze_assets(assets, target, engagement_id)
            findings.extend(asset_results.get("findings", []))
            hypotheses.extend(asset_results.get("hypotheses", []))

        # If no specific data, do general analysis based on target
        if not code and not config and not assets:
            general = await self._general_analysis(target, engagement_id)
            findings.extend(general.get("findings", []))
            hypotheses.extend(general.get("hypotheses", []))

        # Store findings in Graph Memory
        stored_findings = 0
        for f in findings:
            try:
                finding = FindingNode(
                    title=f.get("title", ""),
                    description=f.get("description", ""),
                    vulnerability_class=f.get("vulnerability_class", "unknown"),
                    severity=FindingSeverity(f.get("severity", "medium")),
                    status=FindingStatus.NEEDS_VERIFICATION,
                    confidence_score=f.get("confidence", 50),
                    poc=f.get("poc", ""),
                    impact=f.get("impact", ""),
                    found_by=self.agent_id,
                    engagement_id=engagement_id,
                    target_asset=f.get("asset_uid", ""),
                )
                if self.memory:
                    await self.memory.create_finding(finding)
                    stored_findings += 1
            except Exception as e:
                logger.warning("finding_store_failed", error=str(e))

        # Store hypotheses
        for h in hypotheses:
            try:
                hyp = HypothesisNode(
                    title=h.get("title", ""),
                    description=h.get("description", ""),
                    vulnerability_class=h.get("vulnerability_class", "unknown"),
                    rationale=h.get("rationale", ""),
                    test_plan=h.get("test_plan", ""),
                    proposed_by=self.agent_id,
                    engagement_id=engagement_id,
                )
                if self.memory:
                    await self.memory.create_hypothesis(hyp)
            except Exception as e:
                logger.warning("hypothesis_store_failed", error=str(e))

        self.status = "completed"
        return {
            "agent_id": self.agent_id,
            "findings": findings,
            "hypotheses": hypotheses,
            "findings_stored": stored_findings,
        }

    async def _analyze_code(self, code: str, target: str, engagement_id: str) -> dict:
        """Analyze source code for vulnerabilities."""
        prompt = f"""Analyze this source code for security vulnerabilities:

TARGET: {target}
CODE:
```
{code[:8000]}
```

Perform:
1. Source-sink analysis (user input → dangerous functions)
2. Pattern matching for known vulnerable patterns
3. Hardcoded secret detection
4. Logic flaw identification

Return JSON:
{{
    "findings": [
        {{
            "title": "...",
            "vulnerability_class": "XSS/SQLi/IDOR/...",
            "severity": "critical/high/medium/low",
            "description": "detailed explanation",
            "poc": "how to exploit",
            "impact": "what attacker can do",
            "confidence": 0-100
        }}
    ],
    "hypotheses": [
        {{
            "title": "...",
            "vulnerability_class": "...",
            "description": "...",
            "rationale": "why this might be vulnerable",
            "test_plan": "how to verify"
        }}
    ]
}}"""

        response = await self.think(prompt, task_type="reasoning")
        return self._parse_analysis_response(response.content)

    async def _analyze_config(self, config: str, target: str, engagement_id: str) -> dict:
        """Analyze configuration for security issues."""
        prompt = f"""Analyze this configuration for security misconfigurations:

TARGET: {target}
CONFIG:
```
{config[:5000]}
```

Check for: CORS misconfig, missing security headers, weak CSP, debug mode, exposed endpoints, default credentials.

Return JSON with "findings" array (same format as code analysis)."""

        response = await self.think(prompt, task_type="reasoning")
        return self._parse_analysis_response(response.content)

    async def _analyze_assets(self, assets: list[dict], target: str, engagement_id: str) -> dict:
        """Analyze discovered assets for potential vulnerabilities."""
        assets_summary = json.dumps(assets[:20], indent=2)
        prompt = f"""Based on these discovered assets, identify potential vulnerabilities:

TARGET: {target}
ASSETS:
{assets_summary}

Think about:
1. What vulnerability classes are likely given these technologies?
2. Are there any risky endpoints or parameters?
3. What attack vectors should be tested?
4. Any obvious misconfigurations?

Return JSON with "findings" and "hypotheses" arrays."""

        response = await self.think(prompt, task_type="reasoning")
        return self._parse_analysis_response(response.content)

    async def _general_analysis(self, target: str, engagement_id: str) -> dict:
        """General analysis when no specific data is available."""
        prompt = f"""For the target "{target}", perform a theoretical static analysis:

Based on common web application patterns, identify:
1. Most likely vulnerability classes for this type of target
2. Common misconfigurations to check
3. Standard attack vectors to test
4. Hypotheses about potential weaknesses

Return JSON with "findings" (high-confidence only) and "hypotheses" (theories to test)."""

        response = await self.think(prompt, task_type="reasoning")
        return self._parse_analysis_response(response.content)

    def _parse_analysis_response(self, content: str) -> dict:
        """Parse LLM analysis response into structured data."""
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            data = json.loads(content)
            return {
                "findings": data.get("findings", []),
                "hypotheses": data.get("hypotheses", []),
            }
        except Exception:
            return {"findings": [], "hypotheses": []}
