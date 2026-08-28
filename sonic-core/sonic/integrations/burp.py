"""
SONIC-REDA — Burp Suite REST API Integration
===============================================
Enables deep integration with Burp Suite (Professional / Enterprise / REST Extension):
    - Querying proxy history and sitemap for discovered endpoints
    - Triggering targeted active/passive scans
    - Replaying and mutating requests via Repeater-like interface
    - Ingesting verified scanner findings with raw request/response proof
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from sonic.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BurpHttpItem:
    """An HTTP request/response item from Burp Suite."""
    id: str
    host: str
    port: int
    protocol: str
    url: str
    method: str
    status_code: int
    request_raw: str
    response_raw: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class BurpIssue:
    """A vulnerability issue identified by Burp Scanner."""
    issue_id: str
    name: str
    severity: str  # High, Medium, Low, Information
    confidence: str  # Certain, Firm, Tentative
    host: str
    path: str
    description: str
    remediation: str
    http_items: list[BurpHttpItem] = field(default_factory=list)


class BurpClient:
    """
    Client for interacting with Burp Suite REST API / OpenAPI proxy.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:1337",
        api_key: str = "",
        proxy_url: str = "http://localhost:8080",
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.proxy_url = proxy_url
        self.timeout = timeout
        self._headers = {"X-API-Key": api_key} if api_key else {}

    async def health_check(self) -> bool:
        """Check if Burp Suite REST API endpoint is responsive."""
        try:
            async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers, timeout=5) as client:
                res = await client.get("/v0.1/version")
                return res.status_code < 500
        except Exception:
            return False

    async def get_sitemap(self, host_filter: Optional[str] = None) -> list[str]:
        """
        Fetch all URLs discovered in Burp's target sitemap.
        """
        logger.info("burp_get_sitemap", host=host_filter)
        try:
            async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers, timeout=self.timeout) as client:
                params = {"urlPrefix": f"http://{host_filter}"} if host_filter else {}
                res = await client.get("/v0.1/target/sitemap", params=params)
                if res.status_code == 200:
                    data = res.json()
                    return [item.get("url") for item in data if "url" in item]
        except Exception as e:
            logger.warning("burp_sitemap_failed", error=str(e))
        return []

    async def get_proxy_history(self, limit: int = 100, host_filter: Optional[str] = None) -> list[BurpHttpItem]:
        """
        Query HTTP proxy history intercepted by Burp.
        """
        logger.info("burp_get_proxy_history", limit=limit, host=host_filter)
        items: list[BurpHttpItem] = []
        try:
            async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers, timeout=self.timeout) as client:
                res = await client.get("/v0.1/proxy/history", params={"limit": limit})
                if res.status_code == 200:
                    for raw in res.json():
                        req_b64 = raw.get("request", "")
                        resp_b64 = raw.get("response", "")
                        req_str = base64.b64decode(req_b64).decode("utf-8", errors="replace") if req_b64 else ""
                        resp_str = base64.b64decode(resp_b64).decode("utf-8", errors="replace") if resp_b64 else ""

                        items.append(
                            BurpHttpItem(
                                id=str(raw.get("id", "")),
                                host=raw.get("host", ""),
                                port=raw.get("port", 80),
                                protocol=raw.get("protocol", "http"),
                                url=raw.get("url", ""),
                                method=raw.get("method", "GET"),
                                status_code=raw.get("status_code", 200),
                                request_raw=req_str,
                                response_raw=resp_str,
                            )
                        )
        except Exception as e:
            logger.warning("burp_proxy_history_failed", error=str(e))
        return items

    async def send_custom_request(
        self,
        method: str,
        url: str,
        headers: Optional[dict[str, str]] = None,
        data: Optional[str | bytes] = None,
        use_burp_proxy: bool = True,
    ) -> BurpHttpItem:
        """
        Send a crafted HTTP request through Burp's proxy for logging and analysis.
        """
        proxies = self.proxy_url if use_burp_proxy else None
        async with httpx.AsyncClient(proxies=proxies, verify=False, timeout=self.timeout) as client:
            res = await client.request(method=method, url=url, headers=headers, content=data)
            return BurpHttpItem(
                id="custom",
                host=str(res.url.host),
                port=res.url.port or (443 if res.url.scheme == "https" else 80),
                protocol=res.url.scheme,
                url=str(res.url),
                method=method,
                status_code=res.status_code,
                request_raw=f"{method} {res.url.path} HTTP/1.1\nHost: {res.url.host}\n\n",
                response_raw=f"HTTP/1.1 {res.status_code}\n\n{res.text[:2000]}",
            )

    async def launch_scan(self, target_urls: list[str]) -> Optional[str]:
        """
        Start an active/passive scan task in Burp Scanner.
        """
        logger.info("burp_launch_scan", urls=target_urls)
        try:
            async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers, timeout=self.timeout) as client:
                res = await client.post(
                    "/v0.1/scan",
                    json={"urls": target_urls, "scan_configurations": [{"name": "Crawl and audit - Fast"}]},
                )
                if res.status_code in [200, 201]:
                    # Location header or task ID
                    task_id = res.headers.get("Location", "").split("/")[-1]
                    return task_id or "scan-task-01"
        except Exception as e:
            logger.warning("burp_scan_launch_failed", error=str(e))
        return None

    async def get_scan_issues(self, host_filter: Optional[str] = None) -> list[BurpIssue]:
        """
        Retrieve all scanner issues identified by Burp Scanner.
        """
        issues: list[BurpIssue] = []
        try:
            async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers, timeout=self.timeout) as client:
                res = await client.get("/v0.1/scan/issues", params={"host": host_filter} if host_filter else {})
                if res.status_code == 200:
                    for item in res.json():
                        issues.append(
                            BurpIssue(
                                issue_id=str(item.get("serialNumber", "")),
                                name=item.get("name", "Unknown Issue"),
                                severity=item.get("severity", "Information"),
                                confidence=item.get("confidence", "Tentative"),
                                host=item.get("host", ""),
                                path=item.get("path", ""),
                                description=item.get("issueBackground", "") or item.get("issueDetail", ""),
                                remediation=item.get("remediationBackground", "") or item.get("remediationDetail", ""),
                            )
                        )
        except Exception as e:
            logger.warning("burp_get_issues_failed", error=str(e))
        return issues
