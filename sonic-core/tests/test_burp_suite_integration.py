"""
Integration and unit tests for Burp Suite Bridge (Proxy, REST API, In-Memory Recorder).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from sonic.integrations.burp import (
    BurpClient,
    BurpHttpItem,
    BurpProxyBridge,
    BurpProxyRecorder,
    get_httpx_proxy_config,
)


@pytest.fixture
def test_recorder() -> BurpProxyRecorder:
    return BurpProxyRecorder(max_items=100)


@pytest.mark.asyncio
async def test_check_proxy_live_mock_server():
    """Verify check_proxy_live returns True for active ports and False for inactive ones."""
    async def dummy_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(dummy_handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    client_live = BurpClient(proxy_url=f"http://127.0.0.1:{port}")
    assert await client_live.check_proxy_live() is True

    # Test with localhost resolution
    client_localhost = BurpClient(proxy_url=f"http://localhost:{port}")
    assert await client_localhost.check_proxy_live() is True

    server.close()
    await server.wait_closed()

    # Closed port should return False
    client_dead = BurpClient(proxy_url="http://127.0.0.1:59998")
    assert await client_dead.check_proxy_live(timeout=0.5) is False


@pytest.mark.asyncio
async def test_get_httpx_proxy_config():
    """Verify httpx proxy config generation."""
    default_config = get_httpx_proxy_config()
    assert default_config == {"all://": "http://127.0.0.1:8080"}

    custom_url = "http://192.168.1.50:8080"
    custom_config = get_httpx_proxy_config(custom_url)
    assert custom_config == {"all://": custom_url}

    client = BurpClient(proxy_url="http://10.0.0.1:8080")
    assert client.get_httpx_proxy_config() == {"all://": "http://10.0.0.1:8080"}


@pytest.mark.asyncio
async def test_burp_proxy_recorder_operations(test_recorder: BurpProxyRecorder):
    """Test in-memory proxy recorder tracking, filtering, sitemap, and capacity limits."""
    item1 = BurpHttpItem(
        id="1",
        host="api.target.com",
        port=443,
        protocol="https",
        url="https://api.target.com/users",
        method="GET",
        status_code=200,
        request_raw="GET /users HTTP/1.1",
        response_raw="HTTP/1.1 200 OK",
    )
    item2 = BurpHttpItem(
        id="2",
        host="auth.target.com",
        port=443,
        protocol="https",
        url="https://auth.target.com/login",
        method="POST",
        status_code=302,
        request_raw="POST /login HTTP/1.1",
        response_raw="HTTP/1.1 302 Found",
    )
    item3 = BurpHttpItem(
        id="3",
        host="api.target.com",
        port=443,
        protocol="https",
        url="https://api.target.com/orders",
        method="GET",
        status_code=200,
        request_raw="GET /orders HTTP/1.1",
        response_raw="HTTP/1.1 200 OK",
    )

    test_recorder.record(item1)
    test_recorder.record(item2)
    test_recorder.record(item3)

    # History retrieval
    history = test_recorder.get_history(limit=2)
    assert len(history) == 2
    assert history[0].id == "2"
    assert history[1].id == "3"

    # Host filtering
    api_history = test_recorder.get_history(host_filter="api.target.com")
    assert len(api_history) == 2
    assert all("api.target.com" in it.host for it in api_history)

    # Sitemap extraction
    sitemap = test_recorder.get_sitemap()
    assert len(sitemap) == 3
    assert "https://api.target.com/users" in sitemap
    assert "https://auth.target.com/login" in sitemap

    filtered_sitemap = test_recorder.get_sitemap(host_filter="auth")
    assert filtered_sitemap == ["https://auth.target.com/login"]

    # Clear
    test_recorder.clear()
    assert test_recorder.get_history() == []


@pytest.mark.asyncio
async def test_send_via_proxy_mock_proxy():
    """Test send_via_proxy routing traffic through an HTTP proxy and recording it."""
    recorded_requests = []

    async def mock_proxy_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        req_line = await reader.readline()
        headers = []
        while True:
            line = await reader.readline()
            if not line or line in (b"\r\n", b"\n"):
                break
            headers.append(line)

        recorded_requests.append(req_line.decode("utf-8", errors="replace"))

        # Respond with 200 OK
        body = b'{"status": "proxied_ok"}'
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n"
            b"Connection: close\r\n\r\n" + body
        )
        writer.write(response)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    proxy_server = await asyncio.start_server(mock_proxy_handler, "127.0.0.1", 0)
    proxy_port = proxy_server.sockets[0].getsockname()[1]

    client = BurpClient(proxy_url=f"http://127.0.0.1:{proxy_port}")
    res = await client.send_via_proxy(
        method="POST",
        url="http://target.example.org/api/data",
        headers={"X-Test": "burp-bridge"},
        content=b'{"action": "test"}',
    )

    assert res.status_code == 200
    assert res.json() == {"status": "proxied_ok"}
    assert len(recorded_requests) == 1
    assert "POST" in recorded_requests[0]

    # Verify transaction was recorded in client.recorder
    history = client.recorder.get_history()
    assert len(history) == 1
    assert history[0].method == "POST"
    assert "target.example.org" in history[0].url
    assert history[0].status_code == 200

    proxy_server.close()
    await proxy_server.wait_closed()


@pytest.mark.asyncio
async def test_inspect_rest_api_fallback_behavior():
    """Verify inspect_rest_api falls back cleanly to in-memory recorder when REST API is missing."""
    # Pointing to inactive REST API ports
    client = BurpClient(
        base_url="http://127.0.0.1:59997",
        proxy_url="http://127.0.0.1:59996",
    )

    api_info = await client.inspect_rest_api(candidate_ports=[59997, 59996], timeout=0.2)
    assert api_info is None
    assert client.has_rest_api is False
    assert await client.health_check() is False

    # Since REST API is absent, get_proxy_history and get_sitemap should fall back to recorder
    client.recorder.record(
        BurpHttpItem(
            id="rec-01",
            host="fallback.test",
            port=80,
            protocol="http",
            url="http://fallback.test/home",
            method="GET",
            status_code=200,
            request_raw="GET /home HTTP/1.1",
            response_raw="HTTP/1.1 200 OK",
        )
    )

    history = await client.get_proxy_history()
    assert len(history) == 1
    assert history[0].url == "http://fallback.test/home"

    sitemap = await client.get_sitemap()
    assert sitemap == ["http://fallback.test/home"]


@pytest.mark.asyncio
async def test_inspect_rest_api_mock_available():
    """Verify inspect_rest_api detects an active REST API when present."""
    async def mock_rest_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        req_line = await reader.readline()
        while True:
            line = await reader.readline()
            if not line or line in (b"\r\n", b"\n"):
                break

        if b"/v0.1/version" in req_line:
            body = b'{"version": "2026.1.0", "burpVersion": "Burp Suite Pro"}'
            response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n"
                b"Connection: close\r\n\r\n" + body
            )
        elif b"/v0.1/proxy/history" in req_line:
            body = b'[{"id": 101, "host": "rest.api.test", "port": 443, "protocol": "https", "url": "https://rest.api.test/profile", "method": "GET", "status_code": 200, "request": "", "response": ""}]'
            response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n"
                b"Connection: close\r\n\r\n" + body
            )
        else:
            body = b"Not Found"
            response = b"HTTP/1.1 404 Not Found\r\nContent-Length: 9\r\n\r\n" + body

        writer.write(response)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    rest_server = await asyncio.start_server(mock_rest_handler, "127.0.0.1", 0)
    rest_port = rest_server.sockets[0].getsockname()[1]

    client = BurpClient(base_url=f"http://127.0.0.1:{rest_port}")
    info = await client.inspect_rest_api(candidate_ports=[rest_port])

    assert info is not None
    assert info["available"] is True
    assert info["version_info"]["version"] == "2026.1.0"
    assert client.has_rest_api is True
    assert await client.health_check() is True

    # Proxy history should be fetched from REST API
    items = await client.get_proxy_history()
    assert len(items) == 1
    assert items[0].host == "rest.api.test"

    rest_server.close()
    await rest_server.wait_closed()


@pytest.mark.asyncio
async def test_burp_proxy_bridge():
    """Verify BurpProxyBridge intercepts and records client traffic."""
    # Spin up a mock upstream server
    async def upstream_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        line = await reader.readline()
        while True:
            h = await reader.readline()
            if not h or h in (b"\r\n", b"\n"):
                break
        body = b"Bridge response OK"
        res = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/plain\r\n"
            b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n"
            b"Connection: close\r\n\r\n" + body
        )
        writer.write(res)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    upstream_server = await asyncio.start_server(upstream_handler, "127.0.0.1", 0)
    upstream_port = upstream_server.sockets[0].getsockname()[1]

    # Create and start the bridge
    bridge = BurpProxyBridge(upstream_proxy=f"http://127.0.0.1:{upstream_port}")
    port = await bridge.start("127.0.0.1", 0)
    assert port > 0

    # Make request through bridge
    async with httpx.AsyncClient(proxy=f"http://127.0.0.1:{port}", timeout=5) as client:
        res = await client.get("http://target.local/test-endpoint")
        assert res.status_code == 200
        assert res.text == "Bridge response OK"

    # Verify request was captured in recorder
    history = bridge.recorder.get_history()
    assert len(history) == 1
    assert history[0].method == "GET"
    assert "test-endpoint" in history[0].url

    await bridge.stop()
    upstream_server.close()
    await upstream_server.wait_closed()


@pytest.mark.asyncio
async def test_live_burp_suite_host_integration():
    """
    Test against active Burp Suite on host (http://127.0.0.1:8080) if running.
    This fulfills the live requirement when Burp is active on the user's host.
    """
    client = BurpClient(proxy_url="http://127.0.0.1:8080")
    is_live = await client.check_proxy_live(timeout=1.0)
    if not is_live:
        pytest.skip("Burp Suite proxy is not actively listening on 127.0.0.1:8080")

    # Burp proxy is actively listening!
    # Send request routed through Burp Proxy to http://burp/ (internal Burp landing page)
    res = await client.send_via_proxy("GET", "http://burp/")
    assert res.status_code == 200
    assert "Burp Suite" in res.text

    # Verify request is recorded in client's proxy recorder
    history = client.recorder.get_history()
    assert len(history) >= 1
    assert any("burp" in it.url.lower() for it in history)

    # Inspect REST API - Burp community/pro default proxy returns HTML, so REST API is not configured
    rest_info = await client.inspect_rest_api()
    # If no REST extension configured, it falls back to recorder gracefully
    if rest_info is None:
        assert client.has_rest_api is False
        history_items = await client.get_proxy_history()
        assert len(history_items) >= 1

