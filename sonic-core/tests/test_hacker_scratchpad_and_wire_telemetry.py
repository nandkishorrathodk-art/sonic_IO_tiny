"""
Unit tests for HackerScratchpad and WireTelemetryEngine.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from sonic.computer_use.scratchpad import HackerScratchpad
from sonic.computer_use.wire_telemetry import WireTelemetryEngine


class TestHackerScratchpad:
    """Test suite for HackerScratchpad loot memory and regex extractors."""

    def test_empty_scratchpad_and_hud(self):
        scratchpad = HackerScratchpad()
        assert scratchpad.is_empty() is True
        assert scratchpad.tokens == {}
        assert scratchpad.credentials == []
        assert scratchpad.parameters == {}
        assert scratchpad.endpoints == []
        assert scratchpad.notes == []
        assert scratchpad.render_hud_markdown() == ""

    def test_jwt_extraction_and_deduplication(self):
        scratchpad = HackerScratchpad()
        valid_jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ."
            "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        sample_text = f"HTTP/1.1 200 OK\r\nSet-Cookie: session={valid_jwt}; Secure\r\n\r\nLogin success."

        res = scratchpad.extract_from_text(sample_text, source="login_resp")
        assert res["tokens"] == 1
        assert "login_resp_jwt_1" in scratchpad.tokens
        assert scratchpad.tokens["login_resp_jwt_1"] == valid_jwt

        # Deduplication check: re-running extraction should not duplicate token
        res_repeat = scratchpad.extract_from_text(sample_text, source="login_resp")
        assert res_repeat["tokens"] == 0
        assert len(scratchpad.tokens) == 1

    def test_bearer_token_extraction(self):
        scratchpad = HackerScratchpad()
        sample_text = "Authorization: Bearer secret_bearer_token_1234567890abcdef"

        res = scratchpad.extract_from_text(sample_text)
        assert res["tokens"] == 1
        assert "bearer_auth" in scratchpad.tokens
        assert scratchpad.tokens["bearer_auth"] == "secret_bearer_token_1234567890abcdef"

        # Additional bearer token
        second_text = "Authorization: Bearer secondary_token_abcdef12345678"
        res2 = scratchpad.extract_from_text(second_text)
        assert res2["tokens"] == 1
        assert "bearer_2" in scratchpad.tokens
        assert scratchpad.tokens["bearer_2"] == "secondary_token_abcdef12345678"

    def test_url_parameter_extraction(self):
        scratchpad = HackerScratchpad()
        sample_text = (
            "GET /api/v1/search?id=42&redirect=%2Fdashboard&admin=true&role=sec_admin HTTP/1.1\n"
            "Host: target.internal\n"
        )

        res = scratchpad.extract_from_text(sample_text)
        assert res["parameters"] >= 4
        assert "id" in scratchpad.parameters
        assert "42" in scratchpad.parameters["id"]
        assert "redirect" in scratchpad.parameters
        assert "admin" in scratchpad.parameters
        assert "role" in scratchpad.parameters

        # Discovered endpoints check
        assert "/api/v1/search" in scratchpad.endpoints

    def test_credentials_and_email_extraction(self):
        scratchpad = HackerScratchpad()
        sample_text = (
            "Contact security lead at admin@victimcorp.internal.\n"
            "Default test credentials: username: superadmin, password: P@ssw0rd123!\n"
            "Secret header api_key = api_key_998877665544332211"
        )

        res = scratchpad.extract_from_text(sample_text)
        assert res["credentials"] >= 3
        emails = [c.get("email") for c in scratchpad.credentials if "email" in c]
        assert "admin@victimcorp.internal" in emails

        pairs = [c for c in scratchpad.credentials if "username" in c]
        assert any(p.get("username") == "superadmin" and p.get("password") == "P@ssw0rd123!" for p in pairs)

        api_keys = [c.get("api_key") for c in scratchpad.credentials if "api_key" in c]
        assert "api_key_998877665544332211" in api_keys

    def test_manual_tokens_and_notes(self):
        scratchpad = HackerScratchpad()
        scratchpad.add_token("csrf_token", "random_csrf_token_value_xyz")
        assert scratchpad.tokens["csrf_token"] == "random_csrf_token_value_xyz"

        scratchpad.add_note("Identified possible SQL injection on id parameter")
        scratchpad.add_note("Identified possible SQL injection on id parameter")  # duplicate
        assert len(scratchpad.notes) == 1
        assert scratchpad.notes[0] == "Identified possible SQL injection on id parameter"

    def test_render_hud_markdown_formatting(self):
        scratchpad = HackerScratchpad()
        jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ."
            "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        scratchpad.tokens["jwt_1"] = jwt
        scratchpad.tokens["bearer_auth"] = "bearer_secret_12345"
        scratchpad.parameters["id"] = ["1", "2"]
        scratchpad.parameters["redirect"] = ["/login"]
        scratchpad.parameters["debug"] = ["true"]
        scratchpad.endpoints.extend(["/api/v1/user", "/login"])
        scratchpad.add_note("Target login rate limit bypassed via X-Forwarded-For")

        hud = scratchpad.render_hud_markdown()
        assert "HACKER SCRATCHPAD (Working Loot & Memory):" in hud
        assert "Tokens: jwt_1=eyJhbGciOi... (truncated), bearer_auth=bearer_secret..." in hud
        assert "Parameters: id, redirect, debug" in hud
        assert "Discovered Endpoints: /api/v1/user, /login" in hud
        assert "Notes: Target login rate limit bypassed via X-Forwarded-For" in hud


class TestWireTelemetryEngine:
    """Test suite for WireTelemetryEngine transaction buffering and formatting."""

    def test_ring_buffer_capacity(self):
        engine = WireTelemetryEngine(max_history=20)
        for i in range(25):
            engine.record_wire_event(
                method="GET",
                url=f"/endpoint/{i}",
                status_code=200,
                response_body=f"body_{i}",
            )

        assert len(engine._ring_buffer) == 20
        # Earliest kept item should be item 5 (6th element)
        assert engine._ring_buffer[0]["url"] == "/endpoint/5"
        assert engine._ring_buffer[-1]["url"] == "/endpoint/24"

    @pytest.mark.asyncio
    async def test_fetch_latest_from_ring_buffer(self):
        engine = WireTelemetryEngine()
        engine.record_wire_event("POST", "/api/login", 200, '{"token":"xyz"}')
        engine.record_wire_event("GET", "/api/user", 200, '{"id":1}')
        engine.record_wire_event("GET", "/api/admin", 403, '{"error":"forbidden"}')

        events = await engine.fetch_latest_wire_events(limit=2)
        assert len(events) == 2
        assert events[0]["url"] == "/api/user"
        assert events[1]["url"] == "/api/admin"
        assert events[1]["status_code"] == 403

    @pytest.mark.asyncio
    async def test_fetch_latest_from_burp_client(self):
        mock_burp = MagicMock()
        mock_burp.health_check = AsyncMock(return_value=True)

        mock_item_1 = MagicMock()
        mock_item_1.method = "POST"
        mock_item_1.url = "http://target.internal/api/v1/auth"
        mock_item_1.status_code = 401
        mock_item_1.response_raw = 'HTTP/1.1 401 Unauthorized\r\nContent-Type: application/json\r\n\r\n{"error":"invalid token"}'
        mock_item_1.timestamp = "2026-09-07T12:00:00Z"

        mock_burp.get_proxy_history = AsyncMock(return_value=[mock_item_1])

        engine = WireTelemetryEngine(burp_client=mock_burp)
        events = await engine.fetch_latest_wire_events(limit=1)

        assert len(events) == 1
        assert events[0]["method"] == "POST"
        assert events[0]["url"] == "http://target.internal/api/v1/auth"
        assert events[0]["status_code"] == 401
        assert events[0]["response_body"] == '{"error":"invalid token"}'

    @pytest.mark.asyncio
    async def test_fetch_burp_fallback_on_unresponsive(self):
        mock_burp = MagicMock()
        mock_burp.health_check = AsyncMock(return_value=False)
        mock_burp.get_proxy_history = AsyncMock(side_effect=RuntimeError("Burp down"))

        engine = WireTelemetryEngine(burp_client=mock_burp)
        engine.record_wire_event("GET", "/local/fallback", 200, "fallback content")

        events = await engine.fetch_latest_wire_events(limit=1)
        assert len(events) == 1
        assert events[0]["url"] == "/local/fallback"
        assert events[0]["response_body"] == "fallback content"

    def test_format_wire_summary_empty(self):
        engine = WireTelemetryEngine()
        assert engine.format_wire_summary([]) == ""

    def test_format_wire_summary_formatting(self):
        engine = WireTelemetryEngine()
        events = [
            {
                "method": "POST",
                "url": "/api/v1/auth",
                "status_code": 401,
                "response_body": '{"error":"invalid token"}',
            },
            {
                "method": "GET",
                "url": "/dashboard",
                "status_code": 302,
                "response_body": "",
                "redirect_url": "/login",
            },
        ]

        summary = engine.format_wire_summary(events)
        expected = (
            "LAST ACTION NETWORK WIRE (HTTP Stream):\n"
            '  [1] POST /api/v1/auth -> 401 Unauthorized (Response: {"error":"invalid token"})\n'
            "  [2] GET /dashboard -> 302 Found (Redirect: /login)"
        )
        assert summary == expected

    def test_format_wire_summary_with_full_url(self):
        engine = WireTelemetryEngine()
        events = [
            {
                "method": "GET",
                "url": "https://sec.target.internal/api/v2/metrics?filter=all",
                "status_code": 200,
                "response_body": '{"metrics":[]}',
            }
        ]
        summary = engine.format_wire_summary(events)
        assert "LAST ACTION NETWORK WIRE (HTTP Stream):" in summary
        assert "[1] GET /api/v2/metrics?filter=all -> 200 OK (Response: {\"metrics\":[]})" in summary

