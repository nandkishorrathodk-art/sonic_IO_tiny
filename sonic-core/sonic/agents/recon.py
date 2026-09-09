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

import json
from typing import Any

from sonic.agents.base import BaseAgent
from sonic.llm.prompts import RECON_SYSTEM
from sonic.logger import get_logger
from sonic.memory.schemas import AssetNode, AssetType
from sonic.sandbox.egress import is_target_allowed

logger = get_logger(__name__)


def _is_subdomain_of(host: str, root_domain: str) -> bool:
    """True iff ``host`` is a proper subdomain of ``root_domain``.

    ``endswith`` alone is unsafe: ``"evil-example.com".endswith("example.com")``
    is True. A correct check requires the root to be preceded by a literal dot.
    """
    return host == root_domain or host.endswith("." + root_domain)


class ReconAgent(BaseAgent):
    """
    Reconnaissance agent — discovers and maps the target attack surface.
    Stores all discovered assets in Graph Memory.
    """

    def __init__(self, **kwargs: Any):
        super().__init__(name="ReconAgent", **kwargs)
        self.discovered_assets: list[dict] = []

    def get_system_prompt(self) -> str:
        return RECON_SYSTEM

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute reconnaissance on the target."""
        self.status = "running"
        target = task.get("target", "")
        engagement_id = task.get("engagement_id", "")
        recon_type = task.get("task", "full_recon")

        logger.info("recon_starting", target=target, recon_type=recon_type)

        # LLM-reasoned asset planning + real HTTP enrichment (when permitted).
        assets = await self._discover_assets(target, recon_type, engagement_id)
        assets = await self._enrich_with_live_probe(target, assets)

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

    async def _enrich_with_live_probe(self, target: str, assets: list[dict]) -> list[dict]:
        """
        Augment LLM-planned assets with REAL observations from a live probe
        (HTTP tech fingerprint + reachable URL) when the target is public and
        in-scope. Best-effort: never raises, never invents assets when the
        probe is blocked or unavailable.
        """
        if not target:
            return assets
        normalized = target if target.startswith("http") else f"https://{target}"
        allowed, reason = is_target_allowed(normalized)
        if not allowed:
            logger.info("recon_live_probe_skipped", target=target, reason=reason)
            return assets

        try:
            from sonic.tools.http_probe import HTTPProbe, ProbeTest

            live_assets: list[dict] = []
            async with HTTPProbe() as probe:
                test = ProbeTest(
                    test_name="recon_baseline",
                    vulnerability_class="INFO",
                    method="GET",
                    url=normalized,
                )
                res = await probe.run(test)
            if not res.blocked and res.error == "":
                if res.status_code:
                    live_assets.append({
                        "type": "url", "value": res.url, "name": "Live root URL",
                        "metadata": {"status_code": res.status_code,
                                     "discovered_by": "live_probe"},
                    })
                server = res.response_headers.get("server") or res.response_headers.get("Server")
                if server:
                    live_assets.append({
                        "type": "technology", "value": server, "name": "Web Server",
                        "metadata": {"source": "http_header",
                                     "discovered_by": "live_probe"},
                    })
                powered = res.response_headers.get("x-powered-by") or res.response_headers.get("X-Powered-By")
                if powered:
                    live_assets.append({
                        "type": "technology", "value": powered, "name": "Backend",
                        "metadata": {"source": "x-powered-by",
                                     "discovered_by": "live_probe"},
                    })
            # Merge live assets without duplicating existing values
            existing = {a.get("value") for a in assets}
            for la in live_assets:
                if la.get("value") and la.get("value") not in existing:
                    assets.append(la)
                    existing.add(la.get("value"))
        except Exception as e:
            logger.debug("recon_live_probe_failed", error=str(e))
        return assets

    async def _enumerate_subdomains_real(self, domain: str) -> list[dict]:
        """Enumerate subdomains from a REAL source — Certificate Transparency
        logs (crt.sh) — when the target is public and reachable.

        This replaces imagining subdomains. Returns assets with
        ``discovered_by: "certificate_transparency"``. Best-effort: never
        raises, returns [] if the CT source is blocked/unavailable.
        """
        # crt.sh needs a bare domain; strip scheme/path.
        bare = domain
        if "://" in bare:
            bare = bare.split("://", 1)[1]
        bare = bare.split("/", 1)[0].split(":")[0]
        if not bare or "." not in bare:
            return []
        # Egress-check the CT source (public, non-private).
        allowed, reason = is_target_allowed("https://crt.sh")
        if not allowed:
            logger.info("recon_ct_source_blocked", reason=reason)
            return []
        try:
            from sonic.tools.http_probe import HTTPProbe, ProbeTest
            async with HTTPProbe() as probe:
                res = await probe.run(ProbeTest(
                    test_name="ct_subdomain_enum",
                    vulnerability_class="INFO",
                    method="GET",
                    url=f"https://crt.sh/?q=%.{bare}&output=json",
                ))
            if res.blocked or res.error or not res.response_body:
                return []
            entries = json.loads(res.response_body)
            names: set[str] = set()
            for entry in entries:
                name_value = entry.get("name_value", "")
                # crt.sh returns newline-separated SANs; take the bare host.
                for n in name_value.split("\n"):
                    n = n.strip().lower().lstrip("*.")
                    # Use a proper suffix check so an out-of-scope host
                    # like "evil-example.com" / "notexample.com" cannot
                    # sneak in via a bare endswith(bare) match.
                    if n and _is_subdomain_of(n, bare) and n != bare:
                        names.add(n)
            return [
                {"type": "subdomain", "value": n, "name": "Subdomain (CT log)",
                 "metadata": {"source": "certificate_transparency",
                              "discovered_by": "certificate_transparency"}}
                for n in sorted(names)
            ]
        except Exception as e:
            logger.debug("recon_ct_enum_failed", error=str(e))
            return []

    async def _discover_assets(
        self, target: str, recon_type: str, engagement_id: str
    ) -> list[dict]:
        """Discover assets: REAL CT-log subdomains first, LLM hypothesis only
        as a labeled fallback — never presents imagined subdomains as
        observed truth."""
        assets: list[dict] = []

        # 1. Real subdomain enumeration from Certificate Transparency logs.
        real_subdomains = await self._enumerate_subdomains_real(target)
        assets.extend(real_subdomains)

        prompt = f"""Perform {recon_type} reconnaissance on this target: {target}

Think step by step about what assets are plausible for this target:
1. What subdomains would LIKELY exist? (only if not already discovered above)
2. What technologies would this target typically use?
3. What common endpoints and API paths would exist?
4. What ports would be open?
5. What parameters are commonly tested for this type of application?

These are HYPOTHESES to guide probing — they are NOT confirmed observations.
Return a JSON array of candidate assets:
[
    {{"type": "subdomain", "value": "api.{target}", "name": "Candidate subdomain", "metadata": {{"reason": "hypothesized standard API subdomain"}}}},
    {{"type": "technology", "value": "nginx", "name": "Candidate web server", "metadata": {{"version": "unknown"}}}},
    ...
]

Be thorough but realistic. Include at least 10-15 candidates."""

        if self.router is None:
            return assets
        try:
            response = await self.think(prompt, task_type="fast_recon")
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            hypothesized = json.loads(content)
            if isinstance(hypothesized, list):
                # Clearly label LLM-suggested assets as hypotheses, not observed.
                # Dedupe against real subdomains already discovered.
                real_values = {a.get("value") for a in assets}
                for a in hypothesized:
                    if a.get("value") and a.get("value") not in real_values:
                        meta = a.get("metadata", {}) or {}
                        meta["discovered_by"] = "llm_hypothesis"
                        meta["confirmed"] = False
                        a["metadata"] = meta
                        assets.append(a)
        except Exception as e:
            logger.warning("recon_parse_failed", error=str(e))

        return assets

    async def enumerate_subdomains(self, domain: str, engagement_id: str) -> list[dict]:
        """Focused subdomain enumeration task."""
        task = {"target": domain, "engagement_id": engagement_id, "task": "subdomain_enumeration"}
        return (await self.run(task)).get("assets", [])

    async def detect_technologies(self, target: str, engagement_id: str) -> list[dict]:
        """Focused technology detection task."""
        task = {"target": target, "engagement_id": engagement_id, "task": "tech_detection"}
        return (await self.run(task)).get("assets", [])
