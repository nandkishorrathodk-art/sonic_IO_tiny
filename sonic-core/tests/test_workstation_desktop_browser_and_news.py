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


def test_workstation_desktop_tile_route(client, auth_headers):
    """Proves POST /workstation/desktop/tile calls tile_workstation and returns {"tiled": True}."""
    res = client.post("/workstation/desktop/tile", headers=auth_headers, json={"desktop_id": "test-ws"})
    assert res.status_code == 200
    assert res.json() == {"tiled": True}


def test_workstation_desktop_action_open_app_policy(client, auth_headers):
    """Proves /workstation/desktop/action validates app_name against app_policy for OPEN_APP."""
    # Forbidden package rejected with 403
    res_forbidden = client.post(
        "/workstation/desktop/action",
        headers=auth_headers,
        json={"action": "open_app", "target": "cryptominer --gpu"},
    )
    assert res_forbidden.status_code == 403
    assert "blocked by security policy" in res_forbidden.json()["detail"].lower()

    # Allowed package passes policy check
    res_allowed = client.post(
        "/workstation/desktop/action",
        headers=auth_headers,
        json={"action": "open_app", "target": "chromium https://target.local"},
    )
    assert res_allowed.status_code == 200
    assert res_allowed.json()["status"] == "success"


def test_workstation_desktop_gui_action_open_app_policy(client, auth_headers):
    """Proves /workstation/desktop/gui-action validates app_name against app_policy for OPEN_APP."""
    # Forbidden package rejected with 403
    res_forbidden = client.post(
        "/workstation/desktop/gui-action",
        headers=auth_headers,
        json={"action": "OPEN_APP", "app_name": "tor-relay"},
    )
    assert res_forbidden.status_code == 403
    assert "blocked by security policy" in res_forbidden.json()["detail"].lower()


def test_is_action_prompt_conversational_greetings():
    """Proves conversational greetings and questions are NOT routed to visual ComputerUseAgent."""
    conversational_inputs = [
        "hi sonic",
        "hi sonic ?",
        "hello sonic",
        "hey sonic",
        "who are you",
        "what can you do",
        "status",
        "kya kar rahe ho",
        "kaun ho tum",
        "who are you?",
        "what can you do?",
        "status?",
    ]
    for prompt in conversational_inputs:
        assert _is_action_prompt(prompt) is False, f"Expected '{prompt}' to be False"


def test_list_workstation_sessions_ignores_non_dict(client, auth_headers):
    """Proves list_workstation_sessions safely skips non-dict keys in _tenant_workstations without 500 crash."""
    from sonic.api.routes.workstation import _tenant_workstations

    email = "engineer@company.com"
    if email not in _tenant_workstations:
        _tenant_workstations[email] = {}
    
    # Inject non-dict keys that previously caused AttributeError: 'str' object has no attribute 'get'
    _tenant_workstations[email]["tenant_id"] = "tenant-alpha"
    _tenant_workstations[email]["workspace_type"] = "daytona_cloud"

    res = client.get("/workstation/sessions", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    # Ensure none of the returned entries are the string keys
    returned_sids = [s["session_id"] for s in data]
    assert "tenant_id" not in returned_sids
    assert "workspace_type" not in returned_sids


def test_workstation_prompt_eliminates_puppet_queued_status(client, auth_headers):
    """Proves prompt submission sets dynamic Thinking status instead of puppet 'Reasoning queued'."""
    res = client.post(
        "/workstation/prompt",
        headers=auth_headers,
        json={"prompt": "check open ports and running services", "session_id": "test-puppet-check"},
    )
    assert res.status_code == 200
    data = res.json()
    state = data.get("state", {})
    action = state.get("current_action", "")
    assert "Reasoning queued" not in action
    assert action == "Thinking..."
    assert data.get("reasoning") != "queued"


def test_grounded_conversational_responses():
    """Proves _generate_grounded_workstation_response generates informative content for questions/greetings."""
    from sonic.api.routes.workstation import _generate_grounded_workstation_response

    state = {"status": "IDLE", "current_action": "Ready when you are."}
    who_res = _generate_grounded_workstation_response("who are you", "s1", state, "", "context")
    assert "SONIC" in who_res
    assert "Penetration Architect" in who_res

    what_res = _generate_grounded_workstation_response("what can you do", "s1", state, "", "context")
    assert "Terminal & Shell Execution" in what_res

    status_res = _generate_grounded_workstation_response("status", "s1", state, "ws-123", "context")
    assert "SONIC Workstation Status Report" in status_res
    assert "ws-123" in status_res


