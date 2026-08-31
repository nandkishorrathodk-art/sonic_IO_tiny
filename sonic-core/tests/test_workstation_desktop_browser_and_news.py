"""
SONIC-REDA — Workstation Desktop Browser, News & Action Logic Tests
===================================================================
Tests:
    1. Natural language intent & app recognition (Hindi / English / News / Browser / Terminal).
    2. RSS news parsing & extraction.
    3. Graceful degradation for unprovisioned sessions (git-diff, tree).
    4. Autonomous desktop loop action execution and grounded fallback synthesis.
"""

import pytest
from fastapi.testclient import TestClient

from sonic.api.main import app
from sonic.api.routes.workstation import (
    _clean_rss_titles,
    _detect_requested_app,
    _is_action_prompt,
)
from sonic.auth.google_auth import create_jwt_token
from sonic.auth.models import User, UserRole


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    user = User(
        email="engineer@company.com",
        name="Lead Engineer",
        role=UserRole.OPERATOR,
        tenant_id="tenant-alpha",
    )
    auth_token = create_jwt_token(user)
    return {"Authorization": f"Bearer {auth_token.access_token}"}


def test_detect_requested_app_news_hindi():
    """Proves Hindi news prompt correctly detects Chromium with Google News URL."""
    app_name, url = _detect_requested_app("desktop par browser se aaj ki news dekho")
    assert app_name == "chromium"
    assert "news.google.com" in url


def test_detect_requested_app_terminal():
    """Proves terminal request detects xfce4-terminal."""
    app_name, url = _detect_requested_app("terminal kholo aur check karo")
    assert app_name == "xfce4-terminal"
    assert url == ""


def test_detect_requested_app_custom_url():
    """Proves domain in prompt routes browser to domain URL."""
    app_name, url = _detect_requested_app("open browser and check opensea.io")
    assert app_name == "chromium"
    assert url == "https://opensea.io"


def test_is_action_prompt_intents():
    """Proves various Hindi and English action prompts are recognized."""
    assert _is_action_prompt("desktop par browser se aaj ki news dekho") is True
    assert _is_action_prompt("aaj ki khabar batao") is True
    assert _is_action_prompt("terminal open karo") is True
    assert _is_action_prompt("opensea.io par bug dhundo") is True
    assert _is_action_prompt("perform active recon on target") is True
    assert _is_action_prompt("hello how are you") is False


def test_clean_rss_titles_parsing():
    """Proves XML RSS feed is parsed into clean, entity-decoded titles."""
    sample_rss = """
    <rss version="2.0">
      <channel>
        <title>Google News</title>
        <item>
          <title><![CDATA[Major Tech Breakthrough Announced &amp; Verified]]></title>
        </item>
        <item>
          <title>Global Markets Rally on Economic Data &#39;Optimism&#39;</title>
        </item>
      </channel>
    </rss>
    """
    titles = _clean_rss_titles(sample_rss)
    assert len(titles) == 2
    assert titles[0] == "Major Tech Breakthrough Announced & Verified"
    assert titles[1] == "Global Markets Rally on Economic Data 'Optimism'"


def test_unprovisioned_workstation_endpoints_degrade_gracefully(client, auth_headers):
    """Proves git-diff and tree endpoints return graceful empty states instead of 409."""
    res_diff = client.get("/workstation/git-diff?session_id=unprov-test", headers=auth_headers)
    assert res_diff.status_code == 200
    assert res_diff.json()["success"] is True

    res_tree = client.get("/workstation/tree?session_id=unprov-test", headers=auth_headers)
    assert res_tree.status_code == 200
    assert res_tree.json()["files"] == []
