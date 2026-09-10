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

import asyncio
import json
import re
import socket
import ssl
from typing import Any
from urllib.parse import urljoin, urlparse

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
    Stores all discovered assets in Graph Memory and Dynamic World Model.

    100% Target-First: Prioritizes direct target observation (HTTP GET/OPTIONS,
    native socket connection, TLS certificate inspection, DNS resolution, robots.txt,
    sitemap, HTML structure, API probing) without forcing pre-packaged external scanners.
    """

    def __init__(self, world_model: Any = None, **kwargs: Any):
        super().__init__(name="ReconAgent", **kwargs)
        self.discovered_assets: list[dict] = []
        self.world_model = world_model
        self.target_profile: dict[str, Any] = {}

    def get_system_prompt(self) -> str:
        return RECON_SYSTEM

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute reconnaissance on the target."""
        self.status = "running"
        target = task.get("target", "")
        engagement_id = task.get("engagement_id", "")
        recon_type = task.get("task", "full_recon")

        logger.info("recon_starting", target=target, recon_type=recon_type)

        # LLM-reasoned asset planning + real direct target enrichment (when permitted).
        assets = await self._discover_assets(target, recon_type, engagement_id)
        assets = await self._enrich_with_live_probe(target, assets)

        # Ingest into DynamicWorldModel if attached
        wm = task.get("world_model") or self.world_model
        if wm and hasattr(wm, "ingest_recon_assets"):
            wm.ingest_recon_assets(assets)
        if wm and hasattr(wm, "update_target_profile"):
            wm.update_target_profile(self.target_profile)

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
                    meta_src = (asset_data.get("metadata", {}) or {}).get(
                        "discovered_by", self.agent_id
                    )
                    asset.discovered_by = str(meta_src)
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
            "target_profile": self.target_profile,
            "assets": assets,
        }
        self._log_action("recon_complete", {"assets_found": len(assets), "profile": self.target_profile})
        return result

    def _parse_target(self, target: str) -> dict[str, Any]:
        """Extract scheme, host, port, path, and normalized URL from target."""
        if not target:
            return {"scheme": "https", "host": "", "port": 443, "path": "/", "normalized": ""}
        normalized = target if "://" in target else f"https://{target}"
        parsed = urlparse(normalized)
        scheme = parsed.scheme.lower() or "https"
        host = (parsed.hostname or parsed.netloc or "").split(":")[0]
        port = parsed.port or (443 if scheme == "https" else 80)
        path = parsed.path or "/"
        return {
            "scheme": scheme,
            "host": host,
            "port": port,
            "path": path,
            "normalized": normalized,
        }

    async def _probe_dns(self, host: str) -> list[dict]:
        """Direct DNS resolution via native socket without external tools."""
        if not host or "." not in host:
            return []
        allowed, _ = is_target_allowed(f"http://{host}")
        if not allowed:
            return []

        def _resolve() -> list[dict]:
            dns_assets: list[dict] = []
            try:
                addr_info = socket.getaddrinfo(host, None)
                ips: set[str] = set()
                for family, _, _, _, sockaddr in addr_info:
                    ip = sockaddr[0]
                    if ip and ip not in ips:
                        ips.add(ip)
                        dns_assets.append({
                            "type": "ip_address",
                            "value": ip,
                            "name": f"DNS IP for {host}",
                            "metadata": {
                                "host": host,
                                "address_family": "IPv6" if family == socket.AF_INET6 else "IPv4",
                                "source": "dns_lookup",
                                "discovered_by": "dns_lookup",
                                "confirmed": True,
                            },
                        })
                # Attempt reverse lookup on the first IP
                if ips:
                    first_ip = next(iter(ips))
                    try:
                        ptr_host, _, _ = socket.gethostbyaddr(first_ip)
                        if ptr_host and ptr_host != host:
                            dns_assets.append({
                                "type": "domain",
                                "value": ptr_host,
                                "name": f"PTR Reverse Host for {first_ip}",
                                "metadata": {
                                    "ip": first_ip,
                                    "source": "reverse_dns",
                                    "discovered_by": "dns_lookup",
                                    "confirmed": True,
                                },
                            })
                    except Exception:
                        pass
            except Exception as e:
                logger.debug("recon_dns_lookup_failed", host=host, error=str(e))
            return dns_assets

        try:
            return await asyncio.to_thread(_resolve)
        except Exception:
            return []

    async def _probe_tls(self, host: str, port: int = 443) -> list[dict]:
        """Direct TLS/SSL certificate inspection without external tools.
        
        Extracts Subject CN, SANs (discovering additional real subdomains/domains),
        Issuer, Validity, and TLS protocol parameters natively.
        """
        if not host:
            return []
        allowed, _ = is_target_allowed(f"https://{host}:{port}")
        if not allowed:
            return []

        def _inspect_cert() -> list[dict]:
            tls_assets: list[dict] = []
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_OPTIONAL
                with socket.create_connection((host, port), timeout=2.5) as sock:
                    with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                        cert = ssock.getpeercert()
                        cipher = ssock.cipher()
                        version = ssock.version()

                        # Extract SANs (Subject Alternative Names)
                        sans = []
                        if cert and "subjectAltName" in cert:
                            for san_type, san_val in cert["subjectAltName"]:
                                if san_type == "DNS":
                                    san_clean = san_val.lower().lstrip("*.")
                                    sans.append(san_clean)
                                    if san_clean and san_clean != host and _is_subdomain_of(san_clean, host):
                                        tls_assets.append({
                                            "type": "subdomain",
                                            "value": san_clean,
                                            "name": "Subdomain (TLS SAN)",
                                            "metadata": {
                                                "source": "tls_san",
                                                "discovered_by": "tls_certificate",
                                                "confirmed": True,
                                            },
                                        })

                        subject = dict(x[0] for x in cert.get("subject", [])) if cert else {}
                        issuer = dict(x[0] for x in cert.get("issuer", [])) if cert else {}

                        tls_assets.append({
                            "type": "certificate",
                            "value": f"tls:{host}:{port}",
                            "name": f"TLS Certificate ({host})",
                            "metadata": {
                                "subject_cn": subject.get("commonName", ""),
                                "issuer": issuer.get("organizationName") or issuer.get("commonName", ""),
                                "not_after": cert.get("notAfter", "") if cert else "",
                                "tls_version": version,
                                "cipher": cipher[0] if cipher else "",
                                "sans": sans,
                                "discovered_by": "tls_certificate",
                                "confirmed": True,
                            },
                        })
            except Exception as e:
                logger.debug("recon_tls_probe_failed", host=host, port=port, error=str(e))
            return tls_assets

        try:
            return await asyncio.to_thread(_inspect_cert)
        except Exception:
            return []

    async def _probe_socket_ports(self, host: str, ports: list[int] | None = None) -> list[dict]:
        """Direct socket connect probing without requiring nmap or external scanners."""
        if not host:
            return []
        common_ports = ports or [80, 443, 8080, 8443, 3000, 5000, 8000, 22, 21, 3306, 5432, 6379]

        service_hints = {
            80: "http", 443: "https", 8080: "http-alt", 8443: "https-alt",
            3000: "http-node", 5000: "http-flask", 8000: "http-dev",
            22: "ssh", 21: "ftp", 3306: "mysql", 5432: "postgresql", 6379: "redis",
        }

        async def _check_single_port(p: int) -> dict | None:
            allowed, _ = is_target_allowed(f"http://{host}:{p}")
            if not allowed:
                return None
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, p),
                    timeout=1.2
                )
                banner = ""
                # Attempt lightweight HTTP HEAD banner grab for web-like ports
                if p in (80, 8080, 8000, 3000, 5000):
                    try:
                        writer.write(f"HEAD / HTTP/1.0\r\nHost: {host}\r\n\r\n".encode())
                        await writer.drain()
                        raw_data = await asyncio.wait_for(reader.read(256), timeout=0.8)
                        banner = raw_data.decode(errors="ignore").split("\r\n")[0]
                    except Exception:
                        pass
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
                return {
                    "type": "port",
                    "value": f"{host}:{p}",
                    "name": f"Port {p} ({service_hints.get(p, 'unknown')})",
                    "metadata": {
                        "host": host,
                        "port": p,
                        "service": service_hints.get(p, "unknown"),
                        "banner": banner,
                        "source": "socket_connect",
                        "discovered_by": "socket_probe",
                        "confirmed": True,
                    },
                }
            except Exception:
                return None

        tasks = [_check_single_port(p) for p in common_ports]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, dict)]

    async def _probe_http_surface(self, normalized: str) -> tuple[list[dict], dict[str, Any]]:
        """Deep direct HTTP surface inspection: status, headers, security headers,
        CORS, OPTIONS methods, HTML metadata, robots.txt, sitemaps, and API endpoints."""
        live_assets: list[dict] = []
        profile: dict[str, Any] = {}

        try:
            from sonic.tools.http_probe import HTTPProbe, ProbeTest

            async with HTTPProbe() as probe:
                # 1. Root GET Baseline
                baseline_test = ProbeTest(
                    test_name="recon_baseline",
                    vulnerability_class="INFO",
                    method="GET",
                    url=normalized,
                )
                res = await probe.run(baseline_test)
                if not getattr(res, "blocked", False) and getattr(res, "error", "") == "":
                    status_code = getattr(res, "status_code", 0)
                    headers = getattr(res, "response_headers", {}) or {}
                    body = getattr(res, "response_body", "") or ""

                    if status_code:
                        profile["status_code"] = status_code
                        profile["url"] = getattr(res, "url", normalized)
                        live_assets.append({
                            "type": "url",
                            "value": profile["url"],
                            "name": "Live root URL",
                            "metadata": {
                                "status_code": status_code,
                                "source": "http_get",
                                "discovered_by": "live_probe",
                                "confirmed": True,
                            },
                        })

                    # Server & Backend Technologies
                    server = headers.get("server") or headers.get("Server")
                    if server:
                        profile["server"] = server
                        live_assets.append({
                            "type": "technology",
                            "value": server,
                            "name": "Web Server",
                            "metadata": {
                                "source": "http_header_server",
                                "discovered_by": "live_probe",
                                "confirmed": True,
                            },
                        })

                    powered = headers.get("x-powered-by") or headers.get("X-Powered-By")
                    if powered:
                        profile["x_powered_by"] = powered
                        live_assets.append({
                            "type": "technology",
                            "value": powered,
                            "name": "Backend Framework",
                            "metadata": {
                                "source": "x-powered-by",
                                "discovered_by": "live_probe",
                                "confirmed": True,
                            },
                        })

                    for tech_hdr in ("x-aspnet-version", "x-runtime", "x-generator"):
                        tech_val = headers.get(tech_hdr) or headers.get(tech_hdr.title())
                        if tech_val:
                            live_assets.append({
                                "type": "technology",
                                "value": f"{tech_hdr}: {tech_val}",
                                "name": "Technology Indicator",
                                "metadata": {
                                    "source": tech_hdr,
                                    "discovered_by": "live_probe",
                                    "confirmed": True,
                                },
                            })

                    # Security Posture Headers Analysis
                    security_headers = {}
                    for sh in (
                        "content-security-policy", "strict-transport-security",
                        "x-frame-options", "x-content-type-options",
                        "referrer-policy", "permissions-policy",
                    ):
                        val = headers.get(sh) or headers.get(sh.title())
                        security_headers[sh] = val if val else "missing"
                    profile["security_headers"] = security_headers

                    # CORS Configuration
                    cors_origin = headers.get("access-control-allow-origin") or headers.get("Access-Control-Allow-Origin")
                    if cors_origin:
                        profile["cors_origin"] = cors_origin
                        live_assets.append({
                            "type": "technology",
                            "value": f"CORS: {cors_origin}",
                            "name": "CORS Policy",
                            "metadata": {
                                "allow_origin": cors_origin,
                                "source": "cors_headers",
                                "discovered_by": "live_probe",
                                "confirmed": True,
                            },
                        })

                    # HTML Structure & Form Discovery
                    if body:
                        # Page Title
                        title_match = re.search(r"<title[^>]*>(.*?)</title>", body, re.IGNORECASE | re.DOTALL)
                        if title_match:
                            page_title = title_match.group(1).strip()
                            profile["page_title"] = page_title
                            live_assets.append({
                                "type": "technology",
                                "value": f"Title: {page_title}",
                                "name": "Page Title",
                                "metadata": {"title": page_title, "discovered_by": "html_structure", "confirmed": True},
                            })

                        # Meta Generator
                        gen_match = re.search(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)["\']', body, re.IGNORECASE)
                        if gen_match:
                            generator = gen_match.group(1).strip()
                            profile["generator"] = generator
                            live_assets.append({
                                "type": "technology",
                                "value": generator,
                                "name": "CMS/Generator",
                                "metadata": {"source": "meta_generator", "discovered_by": "html_structure", "confirmed": True},
                            })

                        # HTML Forms & Actions
                        form_actions = re.findall(r'<form[^>]+action=["\']([^"\']+)["\']', body, re.IGNORECASE)
                        for action in form_actions[:5]:
                            full_action = urljoin(normalized, action)
                            live_assets.append({
                                "type": "endpoint",
                                "value": full_action,
                                "name": f"HTML Form Endpoint ({action})",
                                "metadata": {"source": "html_form", "discovered_by": "html_structure", "confirmed": True},
                            })

                        # In-page API Route References
                        api_routes = set(re.findall(r'["\'](/api/v?[0-9]?[a-zA-Z0-9_\-/]+)["\']', body))
                        for api_route in sorted(api_routes)[:10]:
                            full_api = urljoin(normalized, api_route)
                            live_assets.append({
                                "type": "endpoint",
                                "value": full_api,
                                "name": f"In-page API Route: {api_route}",
                                "metadata": {"source": "javascript_html_reference", "discovered_by": "html_structure", "confirmed": True},
                            })

                # 2. HTTP OPTIONS Probe (Allowed Methods)
                options_test = ProbeTest(
                    test_name="recon_options",
                    vulnerability_class="INFO",
                    method="OPTIONS",
                    url=normalized,
                )
                res_opt = await probe.run(options_test)
                if not getattr(res_opt, "blocked", False) and getattr(res_opt, "error", "") == "":
                    opt_headers = getattr(res_opt, "response_headers", {}) or {}
                    allowed_methods = opt_headers.get("allow") or opt_headers.get("Allow") or opt_headers.get("access-control-allow-methods")
                    if allowed_methods:
                        profile["allowed_methods"] = allowed_methods
                        live_assets.append({
                            "type": "technology",
                            "value": f"Allowed Methods: {allowed_methods}",
                            "name": "HTTP Allowed Methods",
                            "metadata": {"methods": allowed_methods, "discovered_by": "live_probe", "confirmed": True},
                        })

                # 3. Direct robots.txt Inspection
                robots_url = urljoin(normalized, "/robots.txt")
                allowed, _ = is_target_allowed(robots_url)
                if allowed:
                    res_robots = await probe.run(ProbeTest(
                        test_name="recon_robots_txt",
                        vulnerability_class="INFO",
                        method="GET",
                        url=robots_url,
                    ))
                    if getattr(res_robots, "status_code", 0) == 200 and getattr(res_robots, "response_body", ""):
                        robots_body = getattr(res_robots, "response_body", "")
                        for line in robots_body.splitlines():
                            line_str = line.strip()
                            if line_str.lower().startswith(("disallow:", "allow:")):
                                parts = line_str.split(":", 1)
                                if len(parts) == 2:
                                    r_path = parts[1].strip()
                                    if r_path and r_path != "/":
                                        full_r_url = urljoin(normalized, r_path)
                                        is_sens = any(k in r_path.lower() for k in ("admin", "secret", "private", "backup", "internal", "config"))
                                        live_assets.append({
                                            "type": "endpoint",
                                            "value": full_r_url,
                                            "name": f"Robots path: {r_path}",
                                            "metadata": {
                                                "path": r_path,
                                                "disallowed_by_robots": line_str.lower().startswith("disallow:"),
                                                "sensitive": is_sens,
                                                "discovered_by": "robots_txt",
                                                "confirmed": True,
                                            },
                                        })

                # 4. Direct sitemap.xml Inspection
                sitemap_url = urljoin(normalized, "/sitemap.xml")
                allowed, _ = is_target_allowed(sitemap_url)
                if allowed:
                    res_sitemap = await probe.run(ProbeTest(
                        test_name="recon_sitemap",
                        vulnerability_class="INFO",
                        method="GET",
                        url=sitemap_url,
                    ))
                    if getattr(res_sitemap, "status_code", 0) == 200 and "<loc>" in getattr(res_sitemap, "response_body", ""):
                        locs = re.findall(r"<loc>(.*?)</loc>", getattr(res_sitemap, "response_body", ""))
                        for loc in locs[:10]:
                            loc_clean = loc.strip()
                            if loc_clean:
                                live_assets.append({
                                    "type": "endpoint",
                                    "value": loc_clean,
                                    "name": "Sitemap URL",
                                    "metadata": {"discovered_by": "sitemap", "confirmed": True},
                                })

                # 5. Common API & Health Endpoint Probing (Zero ffuf required)
                common_api_paths = [
                    "/api", "/api/v1", "/health", "/healthz",
                    "/metrics", "/docs", "/openapi.json", "/swagger.json",
                    "/.well-known/security.txt",
                ]
                for api_path in common_api_paths:
                    test_url = urljoin(normalized, api_path)
                    allowed, _ = is_target_allowed(test_url)
                    if not allowed:
                        continue
                    res_api = await probe.run(ProbeTest(
                        test_name=f"recon_probe_{api_path.strip('/').replace('/', '_')}",
                        vulnerability_class="INFO",
                        method="GET",
                        url=test_url,
                    ))
                    api_status = getattr(res_api, "status_code", 0)
                    # Any response other than 404/0/500/blocked indicates endpoint presence
                    if api_status in (200, 204, 301, 302, 307, 308, 401, 403):
                        is_sens = any(k in api_path for k in ("admin", "metrics", "swagger", "openapi", "docs", "security.txt"))
                        live_assets.append({
                            "type": "endpoint",
                            "value": test_url,
                            "name": f"Discovered Endpoint {api_path} ({api_status})",
                            "metadata": {
                                "path": api_path,
                                "status_code": api_status,
                                "auth_required": api_status in (401, 403),
                                "sensitive": is_sens,
                                "discovered_by": "api_probe",
                                "confirmed": True,
                            },
                        })
        except Exception as e:
            logger.debug("recon_http_surface_probe_failed", error=str(e))

        return live_assets, profile

    async def _enrich_with_live_probe(self, target: str, assets: list[dict]) -> list[dict]:
        """
        Target-First live enrichment: combines direct HTTP surface probing,
        native DNS resolution, direct TLS certificate inspection, and native
        socket port probing without forcing external pre-packaged scanners.
        """
        if not target:
            return assets

        parsed = self._parse_target(target)
        normalized = parsed["normalized"]
        host = parsed["host"]

        allowed, reason = is_target_allowed(normalized)
        if not allowed:
            logger.info("recon_live_probe_skipped", target=target, reason=reason)
            return assets

        live_assets: list[dict] = []

        # 1. Direct HTTP Surface Inspection (Status, Headers, Robots, Sitemap, APIs)
        http_assets, http_profile = await self._probe_http_surface(normalized)
        live_assets.extend(http_assets)
        self.target_profile.update(http_profile)

        # 2. Direct DNS Resolution (Native socket)
        dns_assets = await self._probe_dns(host)
        live_assets.extend(dns_assets)

        # 3. Direct TLS Certificate Inspection (Native ssl + socket)
        if parsed["scheme"] == "https" or parsed["port"] in (443, 8443):
            tls_assets = await self._probe_tls(host, parsed["port"])
            live_assets.extend(tls_assets)

        # 4. Direct Socket Port Probing (Native asyncio.open_connection)
        socket_assets = await self._probe_socket_ports(host)
        live_assets.extend(socket_assets)

        # Merge live assets without duplicating existing values
        existing = {a.get("value") for a in assets}
        for la in live_assets:
            if la.get("value") and la.get("value") not in existing:
                assets.append(la)
                existing.add(la.get("value"))

        self.target_profile["discovered_assets_count"] = len(assets)
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
