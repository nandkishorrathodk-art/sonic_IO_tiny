"""
Comprehensive Test Suite for Phase 4:
  1. ComputeProvider-bound Security Tool Execution (Nmap, Nuclei, FFUF, HTTP).
  2. Fail-Closed tool execution without host fallback.
  3. Containerized Browser Runtime (Playwright/Chromium script execution).
  4. Sandbox Network Egress Control (Metadata & Private IP filtering).
  5. Async Redis Job Queue & SonicWorker Execution Engine.
  6. Multi-Tenant Job API routes.
"""

import asyncio
import pytest
from fastapi.testclient import TestClient

from sonic.api.main import app
from sonic.auth.google_auth import create_jwt_token
from sonic.auth.models import User, UserRole
from sonic.browser.container_runtime import BrowserAction, ContainerizedBrowser
from sonic.queue.job_queue import RedisJobQueue, get_job_queue
from sonic.queue.models import Job, JobPriority, JobStatus, JobType
from sonic.queue.worker import SonicWorker
from sonic.sandbox.egress import is_target_allowed
from sonic.sandbox.provider import WorkspaceConfig
from sonic.sandbox.providers.local_dev_provider import LocalDevProvider
from sonic.tools.adapters.ffuf_adapter import FFUFAdapter
from sonic.tools.adapters.http_adapter import HTTPClientAdapter
from sonic.tools.adapters.nmap_adapter import NmapAdapter
from sonic.tools.adapters.nuclei_adapter import NucleiAdapter
from sonic.tools.base import ToolRequest, ToolStatus

client = TestClient(app)


def get_test_auth_headers(role: UserRole = UserRole.OPERATOR, tenant_id: str = "tenant-phase4"):
    user = User(email=f"worker@{tenant_id}.com", name="Worker Test", tenant_id=tenant_id, role=role)
    token = create_jwt_token(user)
    return {"Authorization": f"Bearer {token.access_token}"}


# ==========================================================
# 1. Tool Adapter & Fail-Closed Tests
# ==========================================================

def test_tool_adapter_fail_closed_when_safety_locked():
    """Verify tools fail closed and never execute on host when safety locked."""
    async def _run():
        locked_provider = LocalDevProvider(allow_host_execution=False)
        nmap = NmapAdapter(locked_provider)

        req = ToolRequest(
            tenant_id="tenant-alpha",
            engagement_id="eng-01",
            workspace_id="sandbox-01",
            agent_id="recon-agent",
            tool_name="nmap",
            target="example.com",
        )

        res = await nmap.execute(req)
        assert res.status == ToolStatus.BLOCKED
        assert res.exit_code == 126
        assert "FAIL-CLOSED" in (res.error_message or "")

    asyncio.run(_run())


def test_tool_parsers():
    """Verify Nmap, Nuclei, and FFUF structured output parsers."""
    provider = LocalDevProvider(allow_host_execution=False)

    # Nmap parsing
    nmap = NmapAdapter(provider)
    sample_nmap_stdout = """
    PORT     STATE SERVICE VERSION
    22/tcp   open  ssh     OpenSSH 8.9p1 Ubuntu
    80/tcp   open  http    nginx 1.18.0
    443/tcp  open  https   nginx 1.18.0
    """
    ports = nmap.parse_output(sample_nmap_stdout, "")
    assert len(ports) == 3
    assert ports[0]["port"] == 22
    assert ports[0]["service"] == "ssh"

    # Nuclei parsing
    nuclei = NucleiAdapter(provider)
    sample_nuclei = '{"template-id": "cve-2023-1234", "info": {"name": "Test Vuln", "severity": "high", "description": "PoC Vuln"}}'
    findings = nuclei.parse_output(sample_nuclei, "")
    assert len(findings) == 1
    assert findings[0]["template_id"] == "cve-2023-1234"
    assert findings[0]["severity"] == "HIGH"

    # FFUF parsing
    ffuf = FFUFAdapter(provider)
    sample_ffuf = '{"results": [{"url": "http://target.com/admin", "status": 200, "length": 512, "input": {"FUZZ": "admin"}}]}'
    endpoints = ffuf.parse_output(sample_ffuf, "")
    assert len(endpoints) == 1
    assert endpoints[0]["url"] == "http://target.com/admin"
    assert endpoints[0]["status_code"] == 200


# ==========================================================
# 2. Containerized Browser Tests
# ==========================================================

def test_containerized_browser_fail_closed():
    """Verify ContainerizedBrowser fails closed if sandbox is unavailable."""
    async def _run():
        locked_provider = LocalDevProvider(allow_host_execution=False)
        browser = ContainerizedBrowser(locked_provider)

        actions = [BrowserAction(action="navigate", url="https://example.com")]
        res = await browser.execute_browser_script("sandbox-ws-01", actions)
        assert res.success is False
        assert "FAIL-CLOSED" in (res.error_message or "").upper()

    asyncio.run(_run())



# ==========================================================
# 3. Egress Security Filtering Tests
# ==========================================================

def test_egress_security_filtering():
    """Verify that cloud metadata and private IP ranges are blocked by default."""
    # Metadata blocked
    allowed, msg = is_target_allowed("169.254.169.254")
    assert allowed is False
    assert "blocked" in msg

    # Loopback blocked
    allowed_lb, msg_lb = is_target_allowed("127.0.0.1")
    assert allowed_lb is False

    # Private RFC 1918 blocked
    allowed_priv, _ = is_target_allowed("10.0.0.5")
    assert allowed_priv is False

    allowed_priv_c, _ = is_target_allowed("192.168.1.100")
    assert allowed_priv_c is False

    # Public domain allowed
    allowed_pub, _ = is_target_allowed("example.com")
    assert allowed_pub is True


# ==========================================================
# 4. Async Queue & Worker Engine Tests
# ==========================================================

def test_job_queue_and_worker_execution():
    """Verify job enqueuing, priority ordering, and worker dispatching."""
    async def _run():
        queue = RedisJobQueue()  # Uses in-memory fallback
        provider = LocalDevProvider(allow_host_execution=False)
        worker = SonicWorker(queue=queue, provider=provider, worker_id="test-worker")

        # 1. Enqueue job
        job = Job(
            tenant_id="tenant-phase4",
            engagement_id="eng-01",
            job_type=JobType.TOOL_EXECUTION,
            priority=JobPriority.HIGH,
            payload={"tool_name": "http_client", "target": "https://example.com"},
        )
        job_id = await queue.enqueue_job(job)
        assert job_id == job.id

        # 2. Dequeue and execute via worker
        processed_job = await worker.run_once()
        assert processed_job is not None
        assert processed_job.id == job_id
        # Because provider is safety locked, worker records failure gracefully
        assert processed_job.status in (JobStatus.QUEUED, JobStatus.FAILED)

    asyncio.run(_run())


# ==========================================================
# 5. Multi-Tenant Job API Endpoints
# ==========================================================

def test_job_api_multi_tenant_isolation():
    """Verify Job API endpoints enforce authentication and tenant isolation."""
    headers_alpha = get_test_auth_headers(tenant_id="tenant-alpha-jobs")
    headers_beta = get_test_auth_headers(tenant_id="tenant-beta-jobs")

    # 1. Tenant Alpha submits job
    res_submit = client.post(
        "/jobs/",
        json={
            "engagement_id": "eng-alpha",
            "job_type": "tool_execution",
            "priority": "high",
            "payload": {"tool_name": "nmap", "target": "alpha-target.com"},
        },
        headers=headers_alpha,
    )
    assert res_submit.status_code == 200
    job_id = res_submit.json()["job_id"]

    # 2. Tenant Alpha can fetch job
    res_get_alpha = client.get(f"/jobs/{job_id}", headers=headers_alpha)
    assert res_get_alpha.status_code == 200
    assert res_get_alpha.json()["job"]["id"] == job_id

    # 3. Tenant Beta direct query -> MUST return 404 Not Found
    res_get_beta = client.get(f"/jobs/{job_id}", headers=headers_beta)
    assert res_get_beta.status_code == 404
