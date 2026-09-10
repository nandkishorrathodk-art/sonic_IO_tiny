"""
Target-First Reconnaissance & Direct Target Profiling Test Suite.
================================================================
Verifies that:
1. Recon does NOT require or force external scanners (nmap/nuclei/ffuf).
2. SONIC directly inspects HTTP status, response headers, OPTIONS methods,
   security headers, robots.txt, sitemaps, HTML structure, and API endpoints.
3. SONIC directly performs native DNS resolution, TLS certificate inspection,
   and socket port probing.
4. Discovered assets in DynamicWorldModel reflect real observations with
   honest provenance rather than canned tool output formats.
5. Safety envelope (is_target_allowed) is strictly enforced.
"""

from __future__ import annotations

import asyncio
import json
import socket
import ssl
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sonic.agents.recon import ReconAgent, _is_subdomain_of
from sonic.brain.world_model import DynamicWorldModel, ResourceNode
import sonic.tools.http_probe as http_probe


# ============================================================================
# Helpers & Fixtures
# ============================================================================

class _MockResponse:
    def __init__(
        self,
        url: str = "https://target.example.com",
        status_code: int = 200,
        response_headers: dict[str, str] | None = None,
        response_body: str = "",
        blocked: bool = False,
        error: str = "",
    ):
        self.url = url
        self.status_code = status_code
        self.response_headers = response_headers or {}
        self.response_body = response_body
        self.blocked = blocked
        self.error = error


class _MockProbe:
    """Mock HTTPProbe returning configurable responses based on URL/method."""
    def __init__(self, dispatch_fn=None):
        self.dispatch_fn = dispatch_fn

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def run(self, test):
        if self.dispatch_fn:
            return self.dispatch_fn(test)
        return _MockResponse()


def _patch_probe_with_dispatcher(dispatch_fn):
    return patch.object(http_probe, "HTTPProbe", return_value=_MockProbe(dispatch_fn))


# ============================================================================
# 1. DynamicWorldModel Asset Ingestion & Attack Surface Tests
# ============================================================================

def test_world_model_ingests_real_observations():
    """Verify that DynamicWorldModel converts observed recon assets into ResourceNodes."""
    wm = DynamicWorldModel(target="https://app.target.local", goal="Assess web portal")
    
    raw_assets = [
        {
            "type": "url",
            "value": "https://app.target.local/",
            "name": "Live root URL",
            "metadata": {"status_code": 200, "discovered_by": "live_probe", "confirmed": True},
        },
        {
            "type": "endpoint",
            "value": "https://app.target.local/admin/login",
            "name": "Admin Login",
            "metadata": {"discovered_by": "robots_txt", "disallowed_by_robots": True, "confirmed": True},
        },
        {
            "type": "technology",
            "value": "nginx/1.24.0",
            "name": "Web Server",
            "metadata": {"source": "http_header_server", "discovered_by": "live_probe", "confirmed": True},
        },
        {
            "type": "port",
            "value": "app.target.local:443",
            "name": "Port 443 (https)",
            "metadata": {"port": 443, "service": "https", "discovered_by": "socket_probe", "confirmed": True},
        },
        {
            "type": "subdomain",
            "value": "api.target.local",
            "name": "API Subdomain",
            "metadata": {"discovered_by": "tls_certificate", "confirmed": True},
        },
        {
            "type": "ip_address",
            "value": "198.51.100.25",
            "name": "DNS IP",
            "metadata": {"discovered_by": "dns_lookup", "confirmed": True},
        },
    ]

    nodes = wm.ingest_recon_assets(raw_assets)
    assert len(nodes) == 6
    assert len(wm.resources) == 6

    # Verify honest provenance preserved in ResourceNodes
    admin_node = next(n for n in nodes if "/admin/login" in n.uri)
    assert admin_node.sensitive is True
    assert "disallowed_by_robots" in admin_node.access_rules
    assert admin_node.metadata.get("discovered_by") == "robots_txt"

    port_node = next(n for n in nodes if ":443" in n.uri)
    assert port_node.resource_type == "service"
    assert port_node.metadata.get("discovered_by") == "socket_probe"

    # Verify attack surface categorization
    surface = wm.get_attack_surface()
    assert len(surface["endpoints"]) == 2  # root url and /admin/login
    assert len(surface["technologies"]) == 1
    assert len(surface["services"]) == 1
    assert len(surface["subdomains"]) == 1
    assert len(surface["infrastructure"]) == 1

    # Verify summary metrics
    summary = wm.get_summary()
    assert summary["resources_count"] == 6
    assert summary["endpoints_count"] == 2
    assert summary["services_count"] == 1
    assert summary["confirmed_assets_count"] == 6


def test_world_model_target_profile_tracking():
    """Verify live target profile updates in DynamicWorldModel."""
    wm = DynamicWorldModel(target="https://target.local", goal="Target profiling")
    
    profile_data = {
        "status_code": 200,
        "server": "Apache/2.4.52",
        "open_ports": [80, 443, 8080],
        "allowed_methods": "GET, POST, OPTIONS",
        "security_headers": {
            "content-security-policy": "missing",
            "strict-transport-security": "max-age=31536000",
        },
    }
    wm.update_target_profile(profile_data)
    assert wm.target_profile["server"] == "Apache/2.4.52"
    assert wm.target_profile["allowed_methods"] == "GET, POST, OPTIONS"
    assert wm.get_summary()["target_profile"]["server"] == "Apache/2.4.52"


# ============================================================================
# 2. Direct HTTP Probing (Headers, OPTIONS, HTML, Robots, Sitemap, APIs)
# ============================================================================

@pytest.mark.asyncio
async def test_direct_http_surface_inspection():
    """Verify direct HTTP inspection captures headers, security posture, and OPTIONS."""
    agent = ReconAgent()

    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Client Portal - Secure Login</title>
        <meta name="generator" content="Next.js 14.2.0">
    </head>
    <body>
        <form action="/auth/v2/login" method="POST">
            <input name="username" type="text">
        </form>
        <script>
            fetch('/api/v1/users/me');
        </script>
    </body>
    </html>
    """

    def fake_dispatcher(test):
        if test.method == "OPTIONS":
            return _MockResponse(
                url=test.url,
                status_code=204,
                response_headers={"Allow": "GET, POST, PUT, DELETE, OPTIONS"},
            )
        elif "/robots.txt" in test.url:
            return _MockResponse(
                url=test.url,
                status_code=200,
                response_body="User-agent: *\nDisallow: /admin\nDisallow: /private/api\nAllow: /public\nSitemap: https://target.example.com/sitemap.xml",
            )
        elif "/sitemap.xml" in test.url:
            return _MockResponse(
                url=test.url,
                status_code=200,
                response_body="<urlset><url><loc>https://target.example.com/products</loc></url></urlset>",
            )
        elif "/api/v1" in test.url:
            return _MockResponse(
                url=test.url,
                status_code=200,
                response_body='{"status":"ok"}',
            )
        elif "/health" in test.url:
            return _MockResponse(
                url=test.url,
                status_code=200,
                response_body='{"healthy":true}',
            )
        elif test.method == "GET" and test.test_name == "recon_baseline":
            return _MockResponse(
                url=test.url,
                status_code=200,
                response_headers={
                    "Server": "gunicorn/20.1.0",
                    "X-Powered-By": "FastAPI",
                    "Access-Control-Allow-Origin": "*",
                    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
                },
                response_body=html_content,
            )
        return _MockResponse(status_code=404)

    with patch("sonic.agents.recon.is_target_allowed", return_value=(True, "Allowed")):
        with _patch_probe_with_dispatcher(fake_dispatcher):
            assets, profile = await agent._probe_http_surface("https://target.example.com")

    # 1. Root & Headers Verification
    assert profile["server"] == "gunicorn/20.1.0"
    assert profile["x_powered_by"] == "FastAPI"
    assert profile["page_title"] == "Client Portal - Secure Login"
    assert profile["generator"] == "Next.js 14.2.0"
    assert profile["allowed_methods"] == "GET, POST, PUT, DELETE, OPTIONS"
    assert profile["cors_origin"] == "*"
    assert profile["security_headers"]["strict-transport-security"] != "missing"

    # 2. HTML Structure Extraction Verification
    form_assets = [a for a in assets if a.get("metadata", {}).get("source") == "html_form"]
    assert any("/auth/v2/login" in a["value"] for a in form_assets)

    api_route_assets = [a for a in assets if "/api/v1/users/me" in a["value"]]
    assert len(api_route_assets) >= 1

    # 3. Robots.txt Extraction Verification
    robots_assets = [a for a in assets if a.get("metadata", {}).get("discovered_by") == "robots_txt"]
    assert any("/admin" in a["value"] for a in robots_assets)
    assert any("/private/api" in a["value"] for a in robots_assets)
    admin_r = next(a for a in robots_assets if "/admin" in a["value"])
    assert admin_r["metadata"]["sensitive"] is True

    # 4. Sitemap.xml Verification
    sitemap_assets = [a for a in assets if a.get("metadata", {}).get("discovered_by") == "sitemap"]
    assert any("/products" in a["value"] for a in sitemap_assets)

    # 5. Direct API Probe Verification (zero ffuf)
    api_probe_assets = [a for a in assets if a.get("metadata", {}).get("discovered_by") == "api_probe"]
    assert any("/health" in a["value"] for a in api_probe_assets)
    assert any("/api/v1" in a["value"] for a in api_probe_assets)


# ============================================================================
# 3. Direct Native Probes (DNS, TLS, Socket Ports)
# ============================================================================

@pytest.mark.asyncio
async def test_direct_dns_probe():
    """Verify native DNS lookup without external dig/host commands."""
    agent = ReconAgent()

    mock_addr_info = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:2800:220:1:248:1893:25c8:1946", 0)),
    ]

    with patch("sonic.agents.recon.is_target_allowed", return_value=(True, "Allowed")):
        with patch("socket.getaddrinfo", return_value=mock_addr_info):
            with patch("socket.gethostbyaddr", return_value=("origin.example.com", [], ["93.184.216.34"])):
                assets = await agent._probe_dns("example.com")

    assert len(assets) >= 2
    ips = {a["value"] for a in assets if a["type"] == "ip_address"}
    assert "93.184.216.34" in ips
    assert "2606:2800:220:1:248:1893:25c8:1946" in ips
    assert all(a["metadata"]["discovered_by"] == "dns_lookup" for a in assets)


@pytest.mark.asyncio
async def test_direct_tls_certificate_probe():
    """Verify native TLS certificate inspection without openssl or external tools."""
    agent = ReconAgent()

    mock_cert = {
        "subject": ((("commonName", "example.com"),),),
        "issuer": ((("organizationName", "DigiCert Inc"),),),
        "notAfter": "Jan 01 00:00:00 2027 GMT",
        "subjectAltName": (
            ("DNS", "example.com"),
            ("DNS", "api.example.com"),
            ("DNS", "staging.example.com"),
        ),
    }

    mock_sock = MagicMock()
    mock_ssock = MagicMock()
    mock_ssock.getpeercert.return_value = mock_cert
    mock_ssock.cipher.return_value = ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)
    mock_ssock.version.return_value = "TLSv1.3"

    with patch("sonic.agents.recon.is_target_allowed", return_value=(True, "Allowed")):
        with patch("socket.create_connection", return_value=mock_sock):
            with patch("ssl.create_default_context") as mock_ctx_cls:
                mock_ctx = MagicMock()
                mock_ctx.wrap_socket.return_value.__enter__.return_value = mock_ssock
                mock_ctx_cls.return_value = mock_ctx

                assets = await agent._probe_tls("example.com", 443)

    # Should discover certificate asset + discovered subdomains from SANs
    cert_asset = next(a for a in assets if a["type"] == "certificate")
    assert cert_asset["metadata"]["subject_cn"] == "example.com"
    assert cert_asset["metadata"]["issuer"] == "DigiCert Inc"
    assert cert_asset["metadata"]["tls_version"] == "TLSv1.3"

    subdomains = {a["value"] for a in assets if a["type"] == "subdomain"}
    assert "api.example.com" in subdomains
    assert "staging.example.com" in subdomains
    assert all(a["metadata"]["discovered_by"] == "tls_certificate" for a in assets)


@pytest.mark.asyncio
async def test_direct_socket_port_probe():
    """Verify native socket port probing without requiring nmap."""
    agent = ReconAgent()

    async def fake_open_connection(host, port):
        if port in (80, 443, 8080):
            mock_reader = AsyncMock()
            mock_reader.read.return_value = b"HTTP/1.1 200 OK\r\nServer: Caddy\r\n"
            mock_writer = MagicMock()
            mock_writer.drain = AsyncMock()
            mock_writer.wait_closed = AsyncMock()
            return mock_reader, mock_writer
        raise ConnectionRefusedError(f"Port {port} closed")

    with patch("sonic.agents.recon.is_target_allowed", return_value=(True, "Allowed")):
        with patch("asyncio.open_connection", side_effect=fake_open_connection):
            assets = await agent._probe_socket_ports("target.example.com", ports=[80, 443, 8080, 22, 3306])

    ports_found = {a["metadata"]["port"] for a in assets}
    assert ports_found == {80, 443, 8080}
    assert all(a["metadata"]["discovered_by"] == "socket_probe" for a in assets)
    assert all(a["metadata"]["confirmed"] is True for a in assets)
    
    http_80 = next(a for a in assets if a["metadata"]["port"] == 80)
    assert "Caddy" in http_80["metadata"]["banner"] or "HTTP/1.1 200 OK" in http_80["metadata"]["banner"]


# ============================================================================
# 4. End-to-End ReconAgent + DynamicWorldModel Integration
# ============================================================================

@pytest.mark.asyncio
async def test_recon_agent_populates_dynamic_world_model():
    """Verify ReconAgent runs direct target-first enrichment and populates DynamicWorldModel."""
    wm = DynamicWorldModel(target="https://target.example.com", goal="Autonomous Reconnaissance")
    agent = ReconAgent(world_model=wm)

    def fake_dispatcher(test):
        if test.test_name == "recon_baseline":
            return _MockResponse(
                url="https://target.example.com",
                status_code=200,
                response_headers={"Server": "nginx/1.22.0"},
                response_body="<html><title>Target Service</title></html>",
            )
        elif "/robots.txt" in test.url:
            return _MockResponse(
                url=test.url,
                status_code=200,
                response_body="User-agent: *\nDisallow: /superadmin",
            )
        return _MockResponse(status_code=404)

    with patch("sonic.agents.recon.is_target_allowed", return_value=(True, "Allowed")):
        with _patch_probe_with_dispatcher(fake_dispatcher):
            with patch.object(agent, "_probe_dns", return_value=[{
                "type": "ip_address", "value": "93.184.216.34", "name": "DNS IP",
                "metadata": {"discovered_by": "dns_lookup", "confirmed": True}
            }]):
                with patch.object(agent, "_probe_tls", return_value=[{
                    "type": "certificate", "value": "tls:target.example.com:443", "name": "TLS Cert",
                    "metadata": {"discovered_by": "tls_certificate", "confirmed": True}
                }]):
                    with patch.object(agent, "_probe_socket_ports", return_value=[{
                        "type": "port", "value": "target.example.com:443", "name": "Port 443",
                        "metadata": {"port": 443, "discovered_by": "socket_probe", "confirmed": True}
                    }]):
                        res = await agent.run({
                            "target": "target.example.com",
                            "engagement_id": "eng-101",
                            "task": "full_recon",
                        })

    assert res["assets_discovered"] >= 5
    assert wm.get_summary()["resources_count"] >= 5
    assert len(wm.get_attack_surface()["services"]) >= 1
    assert len(wm.get_attack_surface()["endpoints"]) >= 2
    assert wm.target_profile.get("server") == "nginx/1.22.0"


# ============================================================================
# 5. Safety & Egress Confinement
# ============================================================================

@pytest.mark.asyncio
async def test_recon_skips_out_of_scope_private_target():
    """Verify that private or egress-blocked targets fail-closed before probing."""
    agent = ReconAgent()
    # 127.0.0.1 or 169.254.169.254 are blocked by default in non-dev or egress rules
    with patch("sonic.agents.recon.is_target_allowed", return_value=(False, "metadata_ip_blocked")):
        assets = await agent._enrich_with_live_probe("http://169.254.169.254", [])
        assert assets == []
        assert agent.target_profile == {}
