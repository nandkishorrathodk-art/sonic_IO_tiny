"""
Unit tests for Browser Vision Agent & Bug Bounty Client.
"""

import asyncio
import pytest
from sonic.agents.browser_agent import BrowserAgent, PageSnapshot, DOMElement
from sonic.integrations.bugbounty import BugBountyClient, BugBountyProgram, DraftReport


def test_browser_agent_httpx_fallback():
    """Test browser agent works in httpx-only mode (no Playwright)."""
    async def _run():
        agent = BrowserAgent(headless=True)
        await agent.launch()

        # Navigate to a known public URL using httpx fallback
        snapshot = await agent.navigate("https://httpbin.org/html")
        assert snapshot.url is not None
        assert snapshot.status_code == 200
        assert len(snapshot.html_content) > 0
        assert "Herman Melville" in snapshot.html_content

        await agent.close()

    asyncio.run(_run())


def test_bug_bounty_report_formatter():
    """Test finding → draft report conversion."""
    finding = {
        "title": "IDOR on /api/v2/users/{id}/tokens",
        "severity": "critical",
        "vulnerability_class": "Broken Object Level Authorization",
        "description": "Changing the user ID in the URL allows reading other users' API tokens without authorization.",
        "poc": "curl -H 'Authorization: Bearer USER_A_TOKEN' https://target.com/api/v2/users/999/tokens",
        "impact": "An attacker can steal any user's API token and impersonate them.",
        "remediation": "Implement server-side authorization check verifying the requesting user owns the resource.",
    }

    report = BugBountyClient.format_report(finding, platform="hackerone")
    assert report.title == "IDOR on /api/v2/users/{id}/tokens"
    assert report.severity == "Critical"
    assert "curl" in report.poc
    assert "Steps to Reproduce" in report.steps_to_reproduce
    assert "SONIC-REDA" in report.description


def test_browser_agent_requires_explicit_scope_when_configured():
    agent = BrowserAgent(
        scope_checker=type("Checker", (), {"is_target_in_scope": lambda *_: True})(),
        require_scope=True,
    )

    async def _run():
        with pytest.raises(ValueError, match="explicit engagement scope"):
            await agent.navigate("https://example.com")

    asyncio.run(_run())


def test_bug_bounty_scope_to_yaml():
    """Test scope auto-import → YAML conversion."""
    program = BugBountyProgram(
        platform="hackerone",
        handle="example-corp",
        name="Example Corp",
        in_scope_domains=["*.example.com", "api.example.com", "app.example.com"],
        out_of_scope=["blog.example.com", "status.example.com"],
        policy_url="https://hackerone.com/example-corp",
    )

    yaml_str = BugBountyClient.scope_to_yaml(program)
    assert "targets:" in yaml_str
    assert "*.example.com" in yaml_str
    assert "exclusions:" in yaml_str
    assert "blog.example.com" in yaml_str
    assert "hackerone" in yaml_str
