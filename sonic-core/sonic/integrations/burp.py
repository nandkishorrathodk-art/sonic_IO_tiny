"""
SONIC-REDA — Burp Suite REST API & Proxy Integration
=====================================================
Enables deep integration with Burp Suite (Professional / Community / Enterprise):
    - Proxy connectivity verification (asyncio TCP open_connection)
    - Routing HTTP traffic through Burp Proxy for intercept and history logging
    - Querying proxy history and sitemap (via REST API or in-memory recorder fallback)
    - Inspecting Burp REST API if configured (e.g. port 1337 or 8080)
    - In-memory proxy recorder and bridge for traffic capture and analysis
    - Triggering scanner tasks and ingesting findings
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

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
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


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


def get_httpx_proxy_config(proxy_url: str = "http://127.0.0.1:8080") -> dict[str, str]:
    """
    Return the httpx proxies configuration mapping.
    E.g. {"all://": "http://127.0.0.1:8080"}
    """
    return {"all://": proxy_url}


class BurpProxyRecorder:
    """
    In-memory HTTP proxy recorder that tracks requests and responses
    so SONIC can inspect proxy history when Burp REST API is unavailable.
    """

    def __init__(self, max_items: int = 1000):
        self.max_items = max_items
        self._items: list[BurpHttpItem] = []

    def record(self, item: BurpHttpItem) -> None:
        """Add a BurpHttpItem to the in-memory history."""
        self._items.append(item)
        if len(self._items) > self.max_items:
            self._items.pop(0)

    def record_httpx(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None,
        content: bytes | None,
        response: httpx.Response,
    ) -> BurpHttpItem:
        """Record an httpx exchange as a BurpHttpItem."""
        parsed = urlparse(url)
        host = parsed.hostname or (str(response.url.host) if response.url else "unknown")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        protocol = parsed.scheme or "http"

        req_headers_str = "\n".join(f"{k}: {v}" for k, v in (headers or {}).items())
        body_preview = ""
        if content:
            body_preview = content.decode("utf-8", errors="replace")[:2000]
        path_str = parsed.path or "/"
        if parsed.query:
            path_str += f"?{parsed.query}"
        request_raw = (
            f"{method.upper()} {path_str} HTTP/1.1\nHost: {host}\n{req_headers_str}\n\n{body_preview}"
        )

        resp_headers_str = "\n".join(f"{k}: {v}" for k, v in response.headers.items())
        content_type = response.headers.get("content-type", "")
        if "text" in content_type or "json" in content_type or "xml" in content_type:
            resp_body_preview = response.text[:4000]
        else:
            resp_body_preview = f"<binary data {len(response.content)} bytes>"
        response_raw = (
            f"HTTP/1.1 {response.status_code} {response.reason_phrase}\n"
            f"{resp_headers_str}\n\n{resp_body_preview}"
        )

        item = BurpHttpItem(
            id=f"rec-{uuid.uuid4().hex[:8]}",
            host=host,
            port=port,
            protocol=protocol,
            url=str(response.url) if str(response.url) else url,
            method=method.upper(),
            status_code=response.status_code,
            request_raw=request_raw,
            response_raw=response_raw,
        )
        self.record(item)
        return item

    def get_history(self, limit: int = 100, host_filter: str | None = None) -> list[BurpHttpItem]:
        """Query recorded HTTP history, optionally filtered by host."""
        filtered = self._items
        if host_filter:
            norm = host_filter.lower()
            filtered = [it for it in filtered if norm in it.host.lower()]
        return filtered[-limit:]

    def get_sitemap(self, host_filter: str | None = None) -> list[str]:
        """Query unique URLs from recorded history."""
        seen: set[str] = set()
        urls: list[str] = []
        for it in self.get_history(limit=self.max_items, host_filter=host_filter):
            if it.url and it.url not in seen:
                seen.add(it.url)
                urls.append(it.url)
        return urls

    def clear(self) -> None:
        """Clear all recorded items."""
        self._items.clear()


class BurpProxyBridge:
    """
    Lightweight HTTP proxy bridge that routes incoming client traffic through Burp Suite
    while recording requests and responses in-memory for SONIC inspection.
    """

    def __init__(
        self,
        upstream_proxy: str = "http://127.0.0.1:8080",
        recorder: BurpProxyRecorder | None = None,
        timeout: float = 30.0,
    ):
        self.upstream_proxy = upstream_proxy
        self.recorder = recorder or BurpProxyRecorder()
        self.timeout = timeout
        self.server: asyncio.Server | None = None
        self.host: str = "127.0.0.1"
        self.port: int = 0

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            line = await reader.readline()
            if not line:
                writer.close()
                return
            parts = line.decode("utf-8", errors="replace").strip().split()
            if len(parts) < 2:
                writer.close()
                return
            method, target = parts[0], parts[1]

            headers: dict[str, str] = {}
            while True:
                header_line = await reader.readline()
                if not header_line or header_line in (b"\r\n", b"\n"):
                    break
                header_str = header_line.decode("utf-8", errors="replace").strip()
                if ":" in header_str:
                    k, v = header_str.split(":", 1)
                    headers[k.strip()] = v.strip()

            content = b""
            content_len = int(headers.get("Content-Length", 0))
            if content_len > 0:
                content = await reader.readexactly(content_len)

            target_url = target
            if not target_url.startswith("http://") and not target_url.startswith("https://"):
                host = headers.get("Host", "localhost")
                target_url = f"http://{host}{target_url}"

            async with httpx.AsyncClient(
                proxy=self.upstream_proxy,
                verify=False,
                timeout=self.timeout,
            ) as client:
                resp = await client.request(
                    method=method,
                    url=target_url,
                    headers=headers,
                    content=content,
                )

            self.recorder.record_httpx(
                method=method,
                url=target_url,
                headers=headers,
                content=content,
                response=resp,
            )

            resp_data = (
                f"HTTP/1.1 {resp.status_code} {resp.reason_phrase}\r\n"
                f"Content-Length: {len(resp.content)}\r\n"
                f"Connection: close\r\n\r\n"
            ).encode("latin1") + resp.content
            writer.write(resp_data)
            await writer.drain()
        except Exception as e:
            err_msg = str(e).encode("utf-8")
            err_resp = (
                f"HTTP/1.1 502 Bad Gateway\r\nContent-Length: {len(err_msg)}\r\n\r\n"
            ).encode("latin1") + err_msg
            writer.write(err_resp)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def start(self, host: str = "127.0.0.1", port: int = 0) -> int:
        """Start the proxy bridge server and return the listening port."""
        self.host = host
        self.server = await asyncio.start_server(self._handle_client, host, port)
        self.port = self.server.sockets[0].getsockname()[1]
        logger.info("burp_proxy_bridge_started", host=self.host, port=self.port)
        return self.port

    async def stop(self) -> None:
        """Stop the proxy bridge server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
            logger.info("burp_proxy_bridge_stopped")


class BurpClient:
    """
    Client for interacting with Burp Suite Proxy and REST API / OpenAPI.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:1337",
        api_key: str = "",
        proxy_url: str = "http://127.0.0.1:8080",
        timeout: int = 30,
        recorder: BurpProxyRecorder | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.proxy_url = proxy_url
        self.timeout = timeout
        self._headers = {"X-API-Key": api_key} if api_key else {}
        self.recorder: BurpProxyRecorder = (
            recorder if recorder is not None else BurpProxyRecorder()
        )
        self._bridge: BurpProxyBridge | None = None
        self.has_rest_api: bool = False

    async def check_proxy_live(self, timeout: float = 2.0) -> bool:
        """
        Check if TCP port 8080 (or self.proxy_url) is accepting connections
        using asyncio.open_connection.
        """
        try:
            proxy_str = self.proxy_url
            if "://" not in proxy_str:
                proxy_str = f"http://{proxy_str}"
            parsed = urlparse(proxy_str)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 8080

            # On Windows, localhost may resolve to ::1 while Burp listens on 127.0.0.1
            hosts_to_try = [host]
            if host == "localhost":
                hosts_to_try.append("127.0.0.1")

            for h in hosts_to_try:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(h, port),
                        timeout=timeout,
                    )
                    writer.close()
                    await writer.wait_closed()
                    return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    def get_httpx_proxy_config(self) -> dict[str, str]:
        """
        Returns the httpx proxies configuration (e.g. {"all://": "http://127.0.0.1:8080"}).
        """
        return get_httpx_proxy_config(self.proxy_url)

    async def send_via_proxy(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Sends HTTP request routed through Burp Proxy so Burp intercepts
        and logs it in Proxy History. Also records in-memory for SONIC inspection.
        """
        async with httpx.AsyncClient(
            proxy=self.proxy_url,
            verify=False,
            timeout=self.timeout,
        ) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                content=content,
                **kwargs,
            )
            if self.recorder is not None:
                self.recorder.record_httpx(
                    method=method,
                    url=url,
                    headers=headers,
                    content=content,
                    response=response,
                )
            return response

    async def health_check(self) -> bool:
        """Check if Burp Suite REST API endpoint is responsive and returns valid JSON."""
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers,
                timeout=5,
            ) as client:
                res = await client.get("/v0.1/version")
                if res.status_code < 400:
                    data = res.json()
                    return isinstance(data, (dict, list))
                return False
        except Exception:
            return False

    async def inspect_rest_api(
        self,
        candidate_ports: list[int] | None = None,
        timeout: float = 2.0,
    ) -> dict[str, Any] | None:
        """
        Inspect whether Burp REST API is available on port 1337 or 8080.
        If available, updates self.base_url and self.has_rest_api.
        If not configured, returns None (indicating fallback to in-memory recorder).
        """
        ports = candidate_ports or [1337, 8080]
        candidates = [self.base_url]
        for port in ports:
            for host in ["127.0.0.1", "localhost"]:
                cand = f"http://{host}:{port}"
                if cand not in candidates:
                    candidates.append(cand)

        for candidate in candidates:
            for endpoint in ["/v0.1/version", "/api/v1/version"]:
                try:
                    async with httpx.AsyncClient(
                        base_url=candidate,
                        headers=self._headers,
                        timeout=timeout,
                    ) as client:
                        res = await client.get(endpoint)
                        if res.status_code < 400:
                            data = res.json()
                            if isinstance(data, (dict, list)):
                                self.base_url = candidate
                                self.has_rest_api = True
                                logger.info("burp_rest_api_discovered", base_url=candidate)
                                return {
                                    "available": True,
                                    "base_url": candidate,
                                    "version_info": data,
                                }
                except Exception:
                    continue

        self.has_rest_api = False
        logger.info("burp_rest_api_not_configured_using_in_memory_recorder")
        return None

    async def get_sitemap(self, host_filter: str | None = None) -> list[str]:
        """
        Fetch all URLs discovered in Burp's target sitemap.
        Queries REST API if available; falls back to in-memory recorder.
        """
        logger.info("burp_get_sitemap", host=host_filter)
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers,
                timeout=self.timeout,
            ) as client:
                params = {"urlPrefix": f"http://{host_filter}"} if host_filter else {}
                res = await client.get("/v0.1/target/sitemap", params=params)
                if res.status_code == 200:
                    data = res.json()
                    if isinstance(data, list):
                        urls = [
                            item.get("url")
                            for item in data
                            if isinstance(item, dict) and "url" in item
                        ]
                        if urls:
                            return urls
        except Exception as e:
            logger.debug("burp_sitemap_failed", error=str(e))

        if self.recorder:
            return self.recorder.get_sitemap(host_filter=host_filter)
        return []

    async def get_proxy_history(
        self,
        limit: int = 100,
        host_filter: str | None = None,
    ) -> list[BurpHttpItem]:
        """
        Query HTTP proxy history intercepted by Burp.
        Queries REST API if available; falls back to in-memory recorder.
        """
        logger.info("burp_get_proxy_history", limit=limit, host=host_filter)
        items: list[BurpHttpItem] = []
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers,
                timeout=self.timeout,
            ) as client:
                res = await client.get("/v0.1/proxy/history", params={"limit": limit})
                if res.status_code == 200:
                    data = res.json()
                    if isinstance(data, list):
                        for raw in data:
                            if not isinstance(raw, dict):
                                continue
                            req_b64 = raw.get("request", "")
                            resp_b64 = raw.get("response", "")
                            req_str = (
                                base64.b64decode(req_b64).decode("utf-8", errors="replace")
                                if req_b64
                                else ""
                            )
                            resp_str = (
                                base64.b64decode(resp_b64).decode("utf-8", errors="replace")
                                if resp_b64
                                else ""
                            )

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
                        if host_filter:
                            items = [it for it in items if host_filter.lower() in it.host.lower()]
                        return items
        except Exception as e:
            logger.debug("burp_proxy_history_failed", error=str(e))

        if self.recorder:
            return self.recorder.get_history(limit=limit, host_filter=host_filter)
        return []

    async def send_custom_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        data: str | bytes | None = None,
        use_burp_proxy: bool = True,
    ) -> BurpHttpItem:
        """
        Send a crafted HTTP request through Burp's proxy for logging and analysis.
        """
        proxy = self.proxy_url if use_burp_proxy else None
        content = data.encode("utf-8") if isinstance(data, str) else data
        async with httpx.AsyncClient(
            proxy=proxy,
            verify=False,
            timeout=self.timeout,
        ) as client:
            res = await client.request(method=method, url=url, headers=headers, content=content)
            req_path = (
                res.url.raw_path.decode("ascii", errors="replace")
                if hasattr(res.url, "raw_path")
                else res.url.path
            )
            item = BurpHttpItem(
                id=f"custom-{uuid.uuid4().hex[:8]}",
                host=str(res.url.host),
                port=res.url.port or (443 if res.url.scheme == "https" else 80),
                protocol=res.url.scheme,
                url=str(res.url),
                method=method,
                status_code=res.status_code,
                request_raw=f"{method} {req_path} HTTP/1.1\nHost: {res.url.host}\n\n",
                response_raw=f"HTTP/1.1 {res.status_code} {res.reason_phrase}\n\n{res.text[:2000]}",
            )
            if self.recorder is not None:
                self.recorder.record(item)
            return item

    async def launch_scan(self, target_urls: list[str]) -> str | None:
        """
        Start an active/passive scan task in Burp Scanner.
        """
        logger.info("burp_launch_scan", urls=target_urls)
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers,
                timeout=self.timeout,
            ) as client:
                res = await client.post(
                    "/v0.1/scan",
                    json={
                        "urls": target_urls,
                        "scan_configurations": [{"name": "Crawl and audit - Fast"}],
                    },
                )
                if res.status_code in [200, 201]:
                    task_id = res.headers.get("Location", "").split("/")[-1]
                    return task_id or "scan-task-01"
        except Exception as e:
            logger.warning("burp_scan_launch_failed", error=str(e))
        return None

    async def get_scan_issues(self, host_filter: str | None = None) -> list[BurpIssue]:
        """
        Retrieve all scanner issues identified by Burp Scanner.
        """
        issues: list[BurpIssue] = []
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers,
                timeout=self.timeout,
            ) as client:
                res = await client.get(
                    "/v0.1/scan/issues",
                    params={"host": host_filter} if host_filter else {},
                )
                if res.status_code == 200:
                    data = res.json()
                    if isinstance(data, list):
                        for item in data:
                            if not isinstance(item, dict):
                                continue
                            issues.append(
                                BurpIssue(
                                    issue_id=str(item.get("serialNumber", "")),
                                    name=item.get("name", "Unknown Issue"),
                                    severity=item.get("severity", "Information"),
                                    confidence=item.get("confidence", "Tentative"),
                                    host=item.get("host", ""),
                                    path=item.get("path", ""),
                                    description=(
                                        item.get("issueBackground", "")
                                        or item.get("issueDetail", "")
                                    ),
                                    remediation=(
                                        item.get("remediationBackground", "")
                                        or item.get("remediationDetail", "")
                                    ),
                                )
                            )
        except Exception as e:
            logger.warning("burp_get_issues_failed", error=str(e))
        return issues

    async def start_bridge(self, host: str = "127.0.0.1", port: int = 0) -> int:
        """Start the in-memory proxy bridge server and return the assigned port."""
        if self._bridge is None:
            self._bridge = BurpProxyBridge(
                upstream_proxy=self.proxy_url,
                recorder=self.recorder,
                timeout=float(self.timeout),
            )
        return await self._bridge.start(host=host, port=port)

    async def stop_bridge(self) -> None:
        """Stop the in-memory proxy bridge server."""
        if self._bridge is not None:
            await self._bridge.stop()
            self._bridge = None
