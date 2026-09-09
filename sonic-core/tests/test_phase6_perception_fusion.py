"""
Tests for Phase 6: Perception Fusion & Multimodal Grounding
============================================================
Verifies:
1. Extraction of inputs, buttons, and forms from DOM into InteractiveControl entities.
2. Screenshot hashing and network event correlation.
3. Contextual page state classification (login vs access_denied vs content).
"""

from __future__ import annotations

import pytest

from sonic.perception.fusion import PerceptionFusion


@pytest.mark.no_live_infra
def test_perception_fusion_login_form_extraction():
    sample_html = """
    <html>
      <head><title>Secure Portal Login</title></head>
      <body>
        <h1>Welcome Back</h1>
        <form action="/auth/login" method="POST">
          <label>Username</label>
          <input type="text" name="username" value="" />
          <label>Password</label>
          <input type="password" name="password" value="" />
          <button type="submit">Sign In</button>
        </form>
      </body>
    </html>
    """

    fake_screenshot = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    network_traces = [
        {"method": "GET", "url": "https://portal.local/login", "status_code": 200, "response_type": "text/html"}
    ]

    state = PerceptionFusion.fuse(
        url="https://portal.local/login",
        title="Secure Portal Login",
        screenshot_bytes=fake_screenshot,
        dom_html=sample_html,
        network_traces=network_traces,
    )

    assert state.page_state == "login"
    assert len(state.controls) == 3  # 2 inputs + 1 button
    assert len(state.forms) == 1
    assert state.forms[0].action == "/auth/login"
    assert len(state.screenshot_hash) == 64
    assert len(state.network_events) == 1
    assert state.network_events[0].status_code == 200

    btn = state.find_control_by_label("Sign In")
    assert btn is not None
    assert btn.tag == "button"


@pytest.mark.no_live_infra
def test_perception_fusion_access_denied_classification():
    sample_html = """
    <html>
      <body>
        <h1>403 Forbidden</h1>
        <p>You are not authorized to view this resource. Access denied.</p>
      </body>
    </html>
    """

    state = PerceptionFusion.fuse(
        url="https://portal.local/admin/secret",
        title="403 Forbidden",
        dom_html=sample_html,
    )

    assert state.page_state == "access_denied"
    assert any("forbidden" in t.lower() for t in state.visible_text)
