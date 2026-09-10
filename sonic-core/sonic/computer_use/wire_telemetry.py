"""
SONIC — Dual Perception Network Wire Telemetry Engine
=====================================================
Captures in-flight network HTTP transactions via local ring buffer and
live application network events for closed-loop reasoning context.
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any
from urllib.parse import urlsplit

from sonic.logger import get_logger

logger = get_logger(__name__)


def _get_status_phrase(code: int) -> str:
    """Return standard HTTP status phrase for a status code, or empty string."""
    try:
        return HTTPStatus(code).phrase
    except Exception:
        return ""


class WireTelemetryEngine:
    """
    Engine for tracking, fetching, and formatting network wire HTTP events
    for agent reasoning context without vendor-specific tool dependencies.
    """

    def __init__(
        self,
        network_interceptor: Any | None = None,
        max_history: int = 20,
        **kwargs: Any,
    ):
        self.network_interceptor = (
            network_interceptor
            or kwargs.get("interceptor")
            or kwargs.get("network_interceptor")
        )
        self._ring_buffer: deque[dict[str, Any]] = deque(maxlen=max_history)

    def record_wire_event(
        self,
        method: str,
        url: str,
        status_code: int,
        response_body: str = "",
        req_headers: dict[str, Any] | None = None,
        res_headers: dict[str, Any] | None = None,
        redirect_url: str | None = None,
    ) -> None:
        """
        Record an HTTP transaction event into the local ring buffer.
        """
        event: dict[str, Any] = {
            "method": method.upper(),
            "url": url,
            "status_code": status_code,
            "response_body": response_body or "",
            "req_headers": req_headers or {},
            "res_headers": res_headers or {},
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Resolve redirect target if applicable
        if redirect_url:
            event["redirect_url"] = redirect_url
        elif res_headers and ("Location" in res_headers or "location" in res_headers):
            event["redirect_url"] = res_headers.get("Location") or res_headers.get("location")
        elif 300 <= status_code < 400 and response_body:
            trimmed = response_body.strip()
            if trimmed.startswith("/") or trimmed.startswith("http://") or trimmed.startswith("https://"):
                event["redirect_url"] = trimmed

        self._ring_buffer.append(event)

    async def fetch_latest_wire_events(self, limit: int = 3) -> list[dict[str, Any]]:
        """
        Fetch the most recent wire events from live application interceptor or ring buffer.
        """
        if self.network_interceptor is not None:
            try:
                if hasattr(self.network_interceptor, "get_proxy_history"):
                    history_call = self.network_interceptor.get_proxy_history(limit=limit)
                    raw_items = await history_call if asyncio.iscoroutine(history_call) else history_call
                    if raw_items:
                        events: list[dict[str, Any]] = []
                        for item in raw_items:
                            if isinstance(item, dict):
                                events.append(item)
                            else:
                                resp_raw = getattr(item, "response_raw", "")
                                body = ""
                                if "\r\n\r\n" in resp_raw:
                                    _, body = resp_raw.split("\r\n\r\n", 1)
                                elif "\n\n" in resp_raw:
                                    _, body = resp_raw.split("\n\n", 1)
                                else:
                                    body = resp_raw
                                events.append({
                                    "method": getattr(item, "method", "GET"),
                                    "url": getattr(item, "url", ""),
                                    "status_code": getattr(item, "status_code", 200),
                                    "response_body": body.strip()[:200],
                                    "timestamp": getattr(item, "timestamp", ""),
                                })
                        return events[-limit:]
            except Exception as e:
                logger.debug("network_interceptor_query_failed", error=str(e))

        # Default: in-memory ring buffer
        all_events = list(self._ring_buffer)
        return all_events[-limit:]

    def fetch_latest_wire_events_sync(self, limit: int = 3) -> list[dict[str, Any]]:
        """Synchronously return recent wire events from ring buffer."""
        all_events = list(self._ring_buffer)
        return all_events[-limit:]

    def format_wire_summary(self, events: list[dict[str, Any]]) -> str:
        """
        Format a concise wire summary for LLM reasoning context:
        LAST ACTION NETWORK WIRE (HTTP Stream):
          [1] POST /api/v1/auth -> 401 Unauthorized (Response: {"error":"invalid token"})
          [2] GET /dashboard -> 302 Found (Redirect: /login)
        """
        if not events:
            return ""

        lines = ["LAST ACTION NETWORK WIRE (HTTP Stream):"]
        for idx, ev in enumerate(events, start=1):
            method = ev.get("method", "GET").upper()
            url = ev.get("url", "")

            # Format URL as route/path if it's an absolute URL
            if url.startswith("http://") or url.startswith("https://"):
                try:
                    parsed = urlsplit(url)
                    path = parsed.path or "/"
                    if parsed.query:
                        path = f"{path}?{parsed.query}"
                except Exception:
                    path = url
            else:
                path = url

            status_code = ev.get("status_code", 200)
            phrase = _get_status_phrase(status_code)
            status_text = f"{status_code} {phrase}".strip() if phrase else str(status_code)

            detail = ""
            redirect = ev.get("redirect_url")
            if not redirect:
                res_headers = ev.get("res_headers", {})
                redirect = res_headers.get("Location") or res_headers.get("location")
            if not redirect and 300 <= status_code < 400:
                body = ev.get("response_body", "").strip()
                if body.startswith("/") or body.startswith("http://") or body.startswith("https://"):
                    redirect = body

            if redirect:
                detail = f" (Redirect: {redirect})"
            elif ev.get("response_body"):
                body = ev.get("response_body", "").strip().replace("\n", " ")
                if len(body) > 60:
                    body = body[:57] + "..."
                detail = f" (Response: {body})"

            lines.append(f"  [{idx}] {method} {path} -> {status_text}{detail}")

        return "\n".join(lines)

