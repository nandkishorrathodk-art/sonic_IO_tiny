"""
SONIC-REDA — Recon Agent
============================
Surface mapping, subdomain enumeration, tech detection, asset discovery.
First agent to run in any engagement — builds the attack surface map.

Capabilities:
    - Subdomain enumeration (passive + active)
    - Technology fingerprinting
    - Port scanning
    - Directory/endpoint discovery
    - API surface mapping
    - Certificate transparency log mining
"""

from __future__ import annotations

from typing import Any
import json
from sonic.logger import get_logger
from sonic.agents.base import BaseAgent
from sonic.memory.schemas import AssetNode, AssetType

logger = get_logger(__name__)


class ReconAgent(BaseAgent):
    """
    Reconnaissance agent — discovers and maps the target attack surface.
    Stores all discovered assets in Graph Memory.
    """

    def __init__(self, **kwargs: Any):
        super().__init__(name="ReconAgent", **kwargs)
        self.discovered_assets: list[dict] = []

    def get_system_prompt(self) -> str:
        return """You are the Recon Agent of SONIC-REDA, an autonomous AI red-team system.

Your job is to discover and map the target's attack surface. You are thorough, methodical, and miss nothing.

For a given target, you should identify:
1. SUBDOMAINS: All subdomains and related domains
2. TECHNOLOGIES: Web servers, frameworks, languages, CDNs, WAFs
3. ENDPOINTS: Interesting URLs, API endpoints, admin panels
4. PORTS: Open ports and running services
5. PARAMETERS: URL parameters, form fields, API parameters that could be tested
6. REPOSITORIES: Any public source code or documentation

For each discovered asset, provide:
- type: domain/subdomain/ip/url/endpoint/technology/port/parameter
- value: the actual value
- metadata: any extra context (headers, versions, notes)

Return your findings as a JSON array of assets.
Always be thorough — missing attack surface means missing vulnerabilities."""

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute reconnaissance on the target."""
        self.status = "running"
        target = task.get("target", "")
        engagement_id = task.get("engagement_id", "")
        recon_type = task.get("task", "full_recon")

        logger.info("recon_starting", target=target, recon_type=recon_type)

        # Use LLM to plan and simulate recon (tool execution in Phase 2)
        assets = await self._discover_assets(target, recon_type, engagement_id)

        # Store assets in Graph Memory
        stored_count = 0
        for asset_data in assets:
            try:
                asset = AssetNode(
                    asset_type=AssetType(asset_data.get("type", "domain")),
                    value=asset_data.get("value", ""),
                    name=asset_data.get("name", ""),
                    metadata=json.dumps(asset_data.get("metadata", {})),
                    discovered_by=self.agent_id,
                    engagement_id=engagement_id,
                )
                if self.memory:
                    uid = await self.memory.upsert_asset(asset)
                    if uid:
                        stored_count += 1
                self.discovered_assets.append(asset_data)
            except Exception as e:
                logger.warning("asset_store_failed", error=str(e), asset=asset_data)

        self.status = "completed"
        result = {
            "agent_id": self.agent_id,
            "target": target,
            "recon_type": recon_type,
            "assets_discovered": len(assets),
            "assets_stored": stored_count,
            "assets": assets,
        }
        self._log_action("recon_complete", {"assets_found": len(assets)})
        return result

    async def _discover_assets(
        self, target: str, recon_type: str, engagement_id: str
    ) -> list[dict]:
        """Use LLM reasoning to discover/enumerate assets."""
        prompt = f"""Perform {recon_type} reconnaissance on this target: {target}

Think step by step about what assets exist for this target:
1. What subdomains likely exist? (api., admin., staging., dev., mail., etc.)
2. What technologies would this target typically use?
3. What common endpoints and API paths would exist?
4. What ports would be open?
5. What parameters are commonly tested for this type of application?

Return a JSON array of discovered assets:
[
    {{"type": "subdomain", "value": "api.{target}", "name": "API subdomain", "metadata": {{"reason": "standard API subdomain"}}}},
    {{"type": "technology", "value": "nginx", "name": "Web Server", "metadata": {{"version": "unknown"}}}},
    ...
]

Be thorough but realistic. Include at least 10-15 assets."""

        response = await self.think(prompt, task_type="fast_recon")

        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            assets = json.loads(content)
            if isinstance(assets, list):
                return assets
        except Exception as e:
            logger.warning("recon_parse_failed", error=str(e))

        # Never invent an attack surface when the model response is missing or
        # malformed. A real recon adapter must supply observed assets.
        logger.warning("recon_assets_unavailable", target=target)
        return []

    async def enumerate_subdomains(self, domain: str, engagement_id: str) -> list[dict]:
        """Focused subdomain enumeration task."""
        task = {"target": domain, "engagement_id": engagement_id, "task": "subdomain_enumeration"}
        return (await self.run(task)).get("assets", [])

    async def detect_technologies(self, target: str, engagement_id: str) -> list[dict]:
        """Focused technology detection task."""
        task = {"target": target, "engagement_id": engagement_id, "task": "tech_detection"}
        return (await self.run(task)).get("assets", [])
