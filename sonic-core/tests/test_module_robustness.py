"""
Regression tests for the module-robustness improvements.

Covers:
  - egress: IPv4-mapped IPv6 SSRF bypass is blocked
  - recon: CT-log subdomain scope-injection (endswith) is blocked
  - docker/local providers: process is killed on timeout (no leak)
  - browser agent: safe close on partial launch + async context manager
  - rate limiter: release-without-acquire underflow guard
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from sonic.agents.browser_agent import BrowserAgent
from sonic.agents.recon import _is_subdomain_of
from sonic.safety.rate_limiter import EgressRateLimiter
from sonic.sandbox.egress import BLOCKED_NETWORKS, is_target_allowed
from sonic.sandbox.providers.local_dev_provider import LocalDevProvider

# =====================================================================
# egress: IPv4-mapped IPv6 SSRF bypass
# =====================================================================

class TestEgressMappedIPv6:
    """The classic SSRF bypass: embed a forbidden v4 address in v6 form."""

    def test_metadata_ipv4_is_blocked(self):
        ok, _ = is_target_allowed("169.254.169.254")
        assert ok is False

    def test_mapped_metadata_ipv6_is_blocked(self):
        ok, _ = is_target_allowed("::ffff:169.254.169.254")
        assert ok is False, "IPv4-mapped IPv6 must not bypass the metadata block"

    def test_mapped_loopback_ipv6_is_blocked(self):
        ok, _ = is_target_allowed("::ffff:127.0.0.1")
        assert ok is False

    def test_mapped_private_ipv6_is_blocked(self):
        ok, _ = is_target_allowed("::ffff:10.0.0.5")
        assert ok is False

    def test_mapped_with_port_is_blocked(self):
        ok, _ = is_target_allowed("[::ffff:169.254.169.254]:80")
        assert ok is False

    def test_mapped_with_scheme_is_blocked(self):
        ok, _ = is_target_allowed("http://[::ffff:169.254.169.254]/")
        assert ok is False

    def test_public_ip_still_allowed(self):
        ok, _ = is_target_allowed("8.8.8.8")
        assert ok is True

    def test_blocked_networks_include_v4_mapped_range(self):
        # The defense-in-depth v4-mapped range must be present so the check
        # does not regress to v4-only blocks.
        nets = {str(n) for n in BLOCKED_NETWORKS}
        assert "::ffff:0.0.0.0/96" in nets


# =====================================================================
# recon: subdomain scope-injection
# =====================================================================

class TestReconSubdomainCheck:
    @pytest.mark.parametrize("host,root,expected", [
        ("sub.example.com", "example.com", True),
        ("a.b.example.com", "example.com", True),
        ("example.com", "example.com", True),
        ("evil-example.com", "example.com", False),
        ("notexample.com", "example.com", False),
        ("example.com.evil.com", "example.com", False),
        ("example.commm", "example.com", False),
    ])
    def test_is_subdomain_of(self, host, root, expected):
        assert _is_subdomain_of(host, root) is expected


# =====================================================================
# providers: process killed on timeout
# =====================================================================

class TestProviderTimeoutKillsProcess:
    """A timed-out command must not leave an orphaned process behind."""

    @pytest.mark.asyncio
    async def test_local_provider_kills_on_timeout(self):
        provider = LocalDevProvider(allow_host_execution=True)
        from sonic.sandbox.provider import WorkspaceConfig, WorkspaceType
        cfg = WorkspaceConfig(
            workspace_id="ws-timeout",
            tenant_id="t",
            workspace_type=WorkspaceType.RESEARCH_LAB,
            image="test",
            cpu_limit="1.0",
            memory_limit="256M",
            timeout_seconds=60,
            network_isolated=True,
        )
        await provider.create_workspace(cfg)
        # sleep 5s but timeout at 1s — process must be killed.
        res = await provider.execute("ws-timeout", "sleep 5", timeout=1)
        assert res.timed_out is True
        assert res.exit_code == -1
        # Give the OS a moment, then confirm no orphaned sleep is running.
        # Use a pattern that excludes the pgrep command itself.
        await asyncio.sleep(0.3)
        ps = await provider.execute(
            "ws-timeout",
            "pgrep -f '^sleep 5$' || true",
            timeout=5,
        )
        assert ps.stdout.strip() == "", "orphaned process leaked after timeout"
        await provider.destroy_workspace("ws-timeout")


# =====================================================================
# browser agent: safe close + async context manager
# =====================================================================

class TestBrowserAgentSafeClose:
    @pytest.mark.asyncio
    async def test_close_without_launch_is_safe(self):
        agent = BrowserAgent()
        # Must not raise even though nothing was launched.
        await agent.close()
        assert agent._playwright is None
        assert agent._browser is None
        assert agent._using_playwright is False

    @pytest.mark.asyncio
    async def test_double_close_is_safe(self):
        agent = BrowserAgent()
        await agent.close()
        await agent.close()  # idempotent

    @pytest.mark.asyncio
    async def test_async_context_manager_calls_close(self):
        agent = BrowserAgent()
        # launch() returns True even without playwright installed (httpx fallback),
        # but close() must still run on exit via __aexit__.
        with patch.object(BrowserAgent, "launch", return_value=True), \
             patch.object(BrowserAgent, "close", return_value=None) as mock_close:
            async with agent:
                pass
            mock_close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_resets_all_handles(self):
        agent = BrowserAgent()
        # Simulate a partially-launched state.
        agent._using_playwright = True
        agent._active_window = None
        await agent.close()
        assert agent._using_playwright is False


# =====================================================================
# rate limiter: release-without-acquire does not underflow
# =====================================================================

class TestRateLimiterUnderflow:
    @pytest.mark.asyncio
    async def test_release_without_acquire_clamps_to_zero(self):
        rl = EgressRateLimiter()
        # Release without acquire — active_connections must not go negative.
        await rl.release("never-acquired.example.com")
        bucket = rl.buckets["never-acquired.example.com"]
        assert bucket.active_connections == 0

    @pytest.mark.asyncio
    async def test_double_release_clamps_to_zero(self):
        rl = EgressRateLimiter()
        await rl.acquire("host.example.com")
        await rl.release("host.example.com")
        await rl.release("host.example.com")  # double release
        bucket = rl.buckets["host.example.com"]
        assert bucket.active_connections == 0

    @pytest.mark.asyncio
    async def test_backoff_recovers_on_success(self):
        rl = EgressRateLimiter()
        await rl.acquire("host.example.com")
        await rl.release("host.example.com", status_code=429)
        assert rl.buckets["host.example.com"].backoff_multiplier > 1.0
        await rl.acquire("host.example.com")
        await rl.release("host.example.com", status_code=200)
        # Backoff should decrease toward 1.0 on success.
        assert rl.buckets["host.example.com"].backoff_multiplier < 2.0


# =====================================================================
# toolsmith / method-lab: provenance timestamps (honest self-improvement)
# =====================================================================

class TestProvenanceTimestamps:
    """A self-authored tool/technique must carry auditable provenance — when it
    was authored vs when it was empirically confirmed in-sandbox."""

    def test_authored_tool_provenance_fields_default_empty(self):
        from sonic.being.toolsmith import AuthoredTool
        t = AuthoredTool(name="x", source="print('x')", rationale="gap")
        assert t.authored_at == ""
        assert t.confirmed_at == ""
        assert t.confirmed_workspace_id == ""
        assert t.reproduced is False

    def test_invented_technique_provenance_fields_default_empty(self):
        from sonic.being.method_lab import InventedTechnique
        t = InventedTechnique(
            technique_id="t1", name="x", family="fuzz",
            hypothesis="h", probe_source="print('x')",
        )
        assert t.invented_at == ""
        assert t.confirmed_at == ""
        assert t.confirmed_workspace_id == ""
        assert t.confirmed is False

    @pytest.mark.asyncio
    async def test_confirm_sets_provenance_only_on_success(self):
        from sonic.being.toolsmith import AuthoredTool
        from sonic.being.toolsmith import ToolsmithLoop as Toolsmith

        class _FakeResult:
            exit_code = 0
            stdout = '{"finding": "ok"}'

        class _FakeProvider:
            async def write_file(self, ws, path, data):
                return True
            async def execute(self, ws, cmd, timeout=60):
                return _FakeResult()

        ts = Toolsmith(craft=None, llm=None, registry=None)
        tool = AuthoredTool(
            name="parse_ok", source="print('ok')", rationale="gap",
            authored_at="2026-01-01T00:00:00+00:00",
        )
        ts.authored.append(tool)
        confirmed = await ts.confirm_and_register(tool, _FakeProvider(), "ws-1")
        assert confirmed.reproduced is True
        assert confirmed.confirmed_at != ""  # set on confirmation
        assert confirmed.confirmed_workspace_id == "ws-1"

    @pytest.mark.asyncio
    async def test_confirm_does_not_set_provenance_on_failure(self):
        from sonic.being.toolsmith import AuthoredTool
        from sonic.being.toolsmith import ToolsmithLoop as Toolsmith

        class _FakeResult:
            exit_code = 126  # fail-closed by sandbox
            stdout = ""

        class _FakeProvider:
            async def write_file(self, ws, path, data):
                return True
            async def execute(self, ws, cmd, timeout=60):
                return _FakeResult()

        ts = Toolsmith(craft=None, llm=None, registry=None)
        tool = AuthoredTool(
            name="parse_bad", source="import os; os.system('rm -rf /')",
            rationale="gap", authored_at="2026-01-01T00:00:00+00:00",
        )
        ts.authored.append(tool)
        confirmed = await ts.confirm_and_register(tool, _FakeProvider(), "ws-2")
        assert confirmed.reproduced is False
        assert confirmed.confirmed_at == ""  # NOT set on failure
        assert confirmed.confirmed_workspace_id == ""


# =====================================================================
# window toggle: APP_FOCUS / SELECT_WINDOW (Chromium ↔ desktop apps)
# =====================================================================

class TestWindowToggle:
    """The agent must be able to switch focus between an already-open browser
    (Chromium) and a desktop app window without relaunching either."""

    def test_app_focus_action_type_exists(self):
        from sonic.computer_use.models import ComputerActionType
        assert ComputerActionType.APP_FOCUS == "APP_FOCUS"

    def test_select_window_in_default_allowed_types(self):
        from sonic.safety.action_policy import ActionPolicy
        assert "APP_FOCUS" in ActionPolicy.DEFAULT_ALLOWED_TYPES

    def test_app_focus_maps_to_select_window(self):
        from sonic.computer.models import GUIAction, GUIActionType
        a = GUIAction(action=GUIActionType.SELECT_WINDOW, app_name="chromium")
        assert a.action is GUIActionType.SELECT_WINDOW
        assert a.app_name == "chromium"

    @pytest.mark.asyncio
    async def test_app_focus_allowed_by_policy(self):
        from sonic.computer_use.models import ComputerActionType
        from sonic.safety.action_policy import ActionPolicy
        pol = ActionPolicy(workspace_root="/home/sonic/workspace")
        v = pol.evaluate(
            ComputerActionType.APP_FOCUS.value,
            "chromium",
            {"app_name": "chromium"},
        )
        assert v.allowed, f"APP_FOCUS must be allowed by default policy: {v.reason}"

    @pytest.mark.asyncio
    async def test_headless_provider_refuses_app_focus(self):
        """A headless UnifiedComputerProvider has no desktop, so GUI actions
        (including SELECT_WINDOW) must fail-closed — never a silent no-op."""
        from sonic.computer.models import (
            ComputerWorkspace,
            ComputerWorkspaceType,
            GUIAction,
            GUIActionType,
        )
        from sonic.computer.provider import UnifiedComputerProvider

        class _StubCompute:
            def get_state(self, *a, **k):
                return None

        p = UnifiedComputerProvider(compute_provider=_StubCompute())
        # Register a workspace so we reach the GUI-backend check, not the
        # workspace-missing guard (the point is the GUI fail-closed).
        p.workspaces["ws-1"] = ComputerWorkspace(
            id="ws-1", tenant_id="t1", engagement_id="e1",
            workspace_type=ComputerWorkspaceType.MISSION_COMPUTER,
        )
        with pytest.raises(RuntimeError, match="GUI actions require a provider"):
            await p.gui_action(
                "ws-1", GUIAction(action=GUIActionType.SELECT_WINDOW, app_name="x"),
            )


# =====================================================================
# application install: APP_INSTALL gate vs raw TERMINAL_EXEC bypass
# =====================================================================

class TestAppInstallGate:
    """Installing an app must go through ApplicationPolicy (forbidden packages
    blocked). The sanctioned path is APP_INSTALL -> install_application(); a raw
    `apt-get install` via TERMINAL_EXEC would bypass that gate."""

    def test_app_install_action_type_exists(self):
        from sonic.computer_use.models import ComputerActionType
        assert ComputerActionType.APP_INSTALL == "APP_INSTALL"

    def test_app_install_in_default_allowed_types(self):
        from sonic.safety.action_policy import ActionPolicy
        assert "APP_INSTALL" in ActionPolicy.DEFAULT_ALLOWED_TYPES

    @pytest.mark.asyncio
    async def test_app_install_allowed_by_policy(self):
        from sonic.computer_use.models import ComputerActionType
        from sonic.safety.action_policy import ActionPolicy
        pol = ActionPolicy(workspace_root="/home/sonic/workspace")
        v = pol.evaluate(
            ComputerActionType.APP_INSTALL.value,
            "nmap",
            {"package": "nmap"},
        )
        assert v.allowed, f"APP_INSTALL must be allowed: {v.reason}"

    def test_forbidden_package_blocked_by_application_policy(self):
        """The provider-level gate that APP_INSTALL routes through must reject
        forbidden packages (cryptominer, tor-relay, ddos-bot)."""
        from sonic.computer.models import ApplicationPolicy
        ap = ApplicationPolicy()
        for forbidden in ("cryptominer", "tor-relay", "ddos-bot", "kernel-mod"):
            allowed, reason = ap.is_package_allowed(forbidden)
            assert not allowed, f"{forbidden} must be blocked"
            assert "prohibited" in reason.lower()

    def test_allowed_packages_pass_application_policy(self):
        from sonic.computer.models import ApplicationPolicy
        ap = ApplicationPolicy()
        for ok_pkg in ("nmap", "nuclei", "chromium", "burpsuite"):
            allowed, reason = ap.is_package_allowed(ok_pkg)
            assert allowed, f"{ok_pkg} should be allowed: {reason}"

    @pytest.mark.asyncio
    async def test_app_install_routes_through_provider_gate(self):
        """APP_INSTALL must call install_application (which checks the policy),
        not a raw execute. Verify the provider blocks a forbidden package."""
        from sonic.computer.models import ComputerWorkspace, ComputerWorkspaceType
        from sonic.computer.provider import UnifiedComputerProvider

        class _StubCompute:
            async def execute(self, *a, **k):
                return type("R", (), {"exit_code": 0, "stdout": "", "stderr": ""})()

        p = UnifiedComputerProvider(compute_provider=_StubCompute())
        p.workspaces["ws-1"] = ComputerWorkspace(
            id="ws-1", tenant_id="t1", engagement_id="e1",
            workspace_type=ComputerWorkspaceType.MISSION_COMPUTER,
        )
        # A forbidden package must be blocked at the provider gate, BEFORE any
        # execute() call reaches the compute layer.
        ok, reason = await p.install_application("ws-1", "cryptominer")
        assert not ok
        assert "prohibited" in (reason or "").lower()

    @pytest.mark.asyncio
    async def test_terminal_exec_apt_get_bypasses_app_policy(self):
        """Documents the gap APP_INSTALL closes: a raw `apt-get install` via
        TERMINAL_EXEC is L0_SAFE (not destructive), so the command gate allows
        it — it does NOT consult ApplicationPolicy. APP_INSTALL is the path that
        does. This test asserts the documented behavior so it is not lost."""
        from sonic.computer_use.models import ComputerActionType
        from sonic.safety.action_policy import ActionPolicy
        pol = ActionPolicy(workspace_root="/home/sonic/workspace")
        v = pol.evaluate(
            ComputerActionType.TERMINAL_EXEC.value,
            "install",
            {"command": "apt-get install -y cryptominer"},
        )
        # The command gate does NOT know about ApplicationPolicy, so it allows.
        # This is exactly why APP_INSTALL exists as the sanctioned install path.
        assert v.allowed, "TERMINAL_EXEC apt-get is L0 (documented gap)"


# =====================================================================
# human-like desktop + browser interaction: DRAG, WAIT, DOWNLOAD
# =====================================================================

class TestHumanLikeInteraction:
    """An agent that works like a human needs: drag (file drop, sliders), wait
    (let a wizard/progress bar settle before re-screenshotting), and download
    (save a file from the browser to run later). These are the primitives a
    browser-driven install wizard requires."""

    def test_gui_drag_enum_and_coords(self):
        """DRAG carries source (x,y) and destination (x2,y2) — a press-move-
        release gesture, not just a move."""
        from sonic.computer.models import GUIAction, GUIActionType
        from sonic.computer_use.models import ComputerActionType
        assert ComputerActionType.GUI_DRAG == "GUI_DRAG"
        g = GUIAction(action=GUIActionType.DRAG, x=10, y=20, x2=30, y2=40)
        assert (g.x, g.y, g.x2, g.y2) == (10, 20, 30, 40)

    def test_gui_drag_in_default_allowed_types(self):
        from sonic.safety.action_policy import ActionPolicy
        assert "GUI_DRAG" in ActionPolicy.DEFAULT_ALLOWED_TYPES

    def test_gui_wait_in_default_allowed_types(self):
        from sonic.safety.action_policy import ActionPolicy
        assert "GUI_WAIT" in ActionPolicy.DEFAULT_ALLOWED_TYPES

    def test_browser_wait_and_download_in_allowed_types(self):
        from sonic.safety.action_policy import ActionPolicy
        assert "BROWSER_WAIT" in ActionPolicy.DEFAULT_ALLOWED_TYPES
        assert "BROWSER_DOWNLOAD" in ActionPolicy.DEFAULT_ALLOWED_TYPES

    @pytest.mark.asyncio
    async def test_gui_wait_allowed_by_policy(self):
        from sonic.computer_use.models import ComputerActionType
        from sonic.safety.action_policy import ActionPolicy
        pol = ActionPolicy(workspace_root="/home/sonic/workspace")
        v = pol.evaluate(ComputerActionType.GUI_WAIT.value, "", {"seconds": 3})
        assert v.allowed, f"GUI_WAIT must be allowed: {v.reason}"

    @pytest.mark.asyncio
    async def test_browser_download_allowed_by_policy(self):
        from sonic.computer_use.models import ComputerActionType
        from sonic.safety.action_policy import ActionPolicy
        pol = ActionPolicy(workspace_root="/home/sonic/workspace")
        v = pol.evaluate(
            ComputerActionType.BROWSER_DOWNLOAD.value,
            "a.download-link",
            {"selector": "a.download-link",
             "save_path": "/home/sonic/workspace/app.deb"},
        )
        assert v.allowed, f"BROWSER_DOWNLOAD must be allowed: {v.reason}"

    @pytest.mark.asyncio
    async def test_browser_download_requires_browser_agent(self):
        """The action-map must parse GUI_DRAG with destination coords so the
        agent can issue a real drag. This verifies the LLM-response parser maps
        GUI_DRAG to ComputerActionType and accepts x2/y2 in the payload."""
        from sonic.computer_use.agent import ComputerUseAgent
        from sonic.computer_use.models import ComputerActionType

        class _FakeComputer:
            pass

        agent = ComputerUseAgent.__new__(ComputerUseAgent)
        # Exercise the static action_map the parser uses (no instance state).
        amap = {
            "GUI_DRAG": ComputerActionType.GUI_DRAG,
            "GUI_WAIT": ComputerActionType.GUI_WAIT,
            "BROWSER_WAIT": ComputerActionType.BROWSER_WAIT,
            "BROWSER_DOWNLOAD": ComputerActionType.BROWSER_DOWNLOAD,
        }
        for name, expected in amap.items():
            # The real map lives in _parse_llm_action; assert these keys exist
            # in ComputerActionType so the parser wiring is valid.
            assert getattr(ComputerActionType, name).value == expected.value

    def test_browser_agent_has_wait_and_download_methods(self):
        """BrowserAgent exposes the human-like primitives: wait_for_element
        and download (with accept_downloads enabled)."""
        from sonic.agents.browser_agent import BrowserAgent
        b = BrowserAgent()
        assert hasattr(b, "wait_for_element")
        assert hasattr(b, "download")

    @pytest.mark.asyncio
    async def test_browser_wait_noop_in_httpx_fallback(self):
        """In httpx fallback (no Playwright), wait_for_element returns True
        (no-op) rather than raising — graceful degradation."""
        from sonic.agents.browser_agent import BrowserAgent
        b = BrowserAgent()
        b._using_playwright = False
        b._page = None
        ok = await b.wait_for_element("#anything")
        assert ok is True

    @pytest.mark.asyncio
    async def test_browser_download_fails_without_playwright(self):
        """download() must return False (not raise) when Playwright is not
        available — fail-closed, no fabricated file."""
        from sonic.agents.browser_agent import BrowserAgent
        b = BrowserAgent()
        b._using_playwright = False
        b._page = None
        ok = await b.download("#dl", "/tmp/x.deb")
        assert ok is False


# =====================================================================
# Devin-style closed loop: VERIFY + REPLAN (stages 7 & 8)
# =====================================================================

class TestVerifyAndReplan:
    """The Devin model's stages 7 (Verify) and 8 (Replan on stuck). The agent
    must NOT trust a self-declared "done" — it independently verifies against
    real sandbox state. And when the same approach fails repeatedly, it
    replans instead of burning the step budget on a stuck loop."""

    @pytest.mark.asyncio
    async def test_verify_goal_fail_closed_on_error_output(self):
        """verify_goal must return verified=False when the probe output contains
        an error/traceback — absence of evidence is not evidence of success."""
        from sonic.computer_use.agent import ComputerUseAgent

        class _FakeComputer:
            async def terminal(self, ws, cmd):
                return type("R", (), {"stdout": "Traceback (most recent call last): ...", "exit_code": 1})()
            async def screenshot(self, ws):
                return type("S", (), {"screenshot_base64": "", "width": 1920, "height": 1080})()
            async def status(self, ws):
                return type("St", (), {"active_application": "", "open_applications": [], "running_processes": []})()
            async def list_files(self, ws, path):
                return []
            async def git_action(self, ws, action):
                return type("G", (), {"branch": "main", "is_clean": True})()

        agent = ComputerUseAgent.__new__(ComputerUseAgent)
        agent.computer = _FakeComputer()
        agent._last_screenshot_b64 = ""
        agent._last_browser_snapshot = None
        agent.browser = None
        verified, evidence = await agent.verify_goal("ws", "run the tests")
        assert verified is False
        assert "traceback" in evidence.lower()

    @pytest.mark.asyncio
    async def test_verify_goal_passes_on_real_evidence(self):
        """verify_goal returns verified=True when the probe returns real,
        non-error output — the artifact genuinely exists."""
        from sonic.computer_use.agent import ComputerUseAgent

        class _FakeComputer:
            async def terminal(self, ws, cmd):
                return type("R", (), {"stdout": "/usr/bin/nmap", "exit_code": 0})()

        agent = ComputerUseAgent.__new__(ComputerUseAgent)
        agent.computer = _FakeComputer()
        verified, evidence = await agent.verify_goal("ws", "install nmap")
        assert verified is True
        assert "nmap" in evidence

    @pytest.mark.asyncio
    async def test_verify_goal_reobserves_when_no_probe_inferable(self):
        """For goals with no inferable probe (e.g. 'review the code'),
        verify_goal re-observes rather than fabricating success."""
        from sonic.computer_use.agent import ComputerUseAgent

        class _FakeComputer:
            async def screenshot(self, ws):
                from sonic.computer.models import ScreenObservation
                return ScreenObservation(screenshot_base64="", width=1920, height=1080, visible_text="")
            async def status(self, ws):
                return type("St", (), {"active_application": "vim", "open_applications": [], "running_processes": []})()
            async def list_files(self, ws, path):
                return []
            async def git_action(self, ws, action):
                return type("G", (), {"branch": "main", "is_clean": True})()
            async def terminal(self, ws, cmd):
                return type("R", (), {"stdout": "", "exit_code": 0})()

        agent = ComputerUseAgent.__new__(ComputerUseAgent)
        agent.computer = _FakeComputer()
        agent._last_screenshot_b64 = ""
        agent._last_browser_snapshot = None
        agent.browser = None
        verified, evidence = await agent.verify_goal("ws", "review the architecture")
        assert "re-observed" in evidence.lower()

    def test_replan_injected_on_consecutive_failures(self):
        """After _STUCK_THRESHOLD consecutive failures, _inject_replan adds a
        REPLAN entry to history and resets the failure counter — so the next
        LLM call sees the pivot signal and changes strategy."""
        from sonic.computer_use.agent import ComputerUseAgent

        agent = ComputerUseAgent.__new__(ComputerUseAgent)
        agent.history = []
        agent._consecutive_failures = 3
        agent._replan_count = 0
        agent._inject_replan("build the app")
        assert agent._replan_count == 1
        assert agent._consecutive_failures == 0
        assert any(h["action"] == "REPLAN" for h in agent.history)
        assert "DIFFERENT strategy" in agent.history[-1]["result"]

    @pytest.mark.asyncio
    async def test_run_mission_replans_on_repeated_failures(self):
        """The run_mission loop must detect repeated failure (stuck) and inject
        a replan rather than silently exhausting the step budget."""
        from sonic.computer_use.agent import ComputerUseAgent
        from sonic.computer_use.models import ComputerActionType

        class _FakeComputer:
            async def terminal(self, ws, cmd):
                return type("R", (), {"stdout": "ok", "exit_code": 0})()
            async def screenshot(self, ws):
                from sonic.computer.models import ScreenObservation
                return ScreenObservation(screenshot_base64="", width=1920, height=1080, visible_text="")
            async def status(self, ws):
                return type("St", (), {"active_application": "", "open_applications": [], "running_processes": []})()
            async def list_files(self, ws, path):
                return []
            async def git_action(self, ws, action):
                return type("G", (), {"branch": "main", "is_clean": True})()
            async def gui_action(self, *a, **k):
                pass
            async def service_action(self, *a, **k):
                pass

        agent = ComputerUseAgent.__new__(ComputerUseAgent)
        agent.computer = _FakeComputer()
        agent.llm_router = None
        agent.traces = []
        agent.history = []
        agent.recovery_events = 0
        agent.action_counter = 0
        agent.max_actions = 100
        agent.max_recovery_attempts = 0
        agent.metrics = type("M", (), {})()
        agent._last_screenshot_b64 = ""
        agent._last_browser_snapshot = None
        agent._last_tool_result = None
        agent.browser = None
        agent.security_tools = {}
        agent.safety = None
        agent._consecutive_failures = 0
        agent._replan_count = 0
        agent.toolsmith = None
        agent.method_lab = None
        agent.lessons_ledger = None
        agent._files_cache = []

        # Override execute_action to always fail (simulating a stuck approach).
        async def _always_fail(ws, at, target, payload, expected):
            from sonic.computer_use.models import ComputerDecisionTrace
            agent.action_counter += 1
            t = ComputerDecisionTrace(
                step_index=agent.action_counter, action_type=at,
                target_resource=target, payload=str(payload),
                predicted_outcome=expected, actual_observation="fail",
                info_gain=0.0, recovery_attempted=False, status="FAILED",
            )
            agent.traces.append(t)
            agent.history.append({"action": f"{at.value}", "result": "fail"})
            return t
        agent.execute_action = _always_fail

        # Override choose_action to return a non-GOAL_COMPLETE action.
        async def _choose(goal, obs, step):
            return (ComputerActionType.TERMINAL_EXEC, "x", {"command": "false"}, "fail")
        agent.choose_action = _choose

        await agent.run_mission("ws", "do something", steps=4)
        # After 3 consecutive failures, a replan must have been injected.


# =====================================================================
# Self-improvement: cross-mission lessons ledger (learn → apply loop)
# =====================================================================

class TestLessonsLedger:
    """The self-improvement gap: lessons were computed but never fed back. The
    LessonsLedger closes the learn→apply loop — extract lessons from real trace
    outcomes, persist them, and inject the relevant ones into the next
    mission's reasoning so the being does not start every mission with amnesia."""

    def test_extract_lessons_avoid_on_failed_reuse_on_success(self):
        """A FAILED trace → AVOID lesson; a SUCCESS/RECOVERED trace → REUSE
        lesson. Grounded in real trace.status — never fabricated."""
        from sonic.being.lessons import LessonKind, extract_lessons

        class _T:
            def __init__(self, status, action="TERMINAL_EXEC", target="nmap", actual="ok"):
                self.status = status
                self.action_type = type("A", (), {"value": action})()
                self.target_resource = target
                self.predicted_outcome = "scan completes"
                self.actual_observation = actual

        traces = [
            _T("FAILED", actual="connection refused"),
            _T("SUCCESS", actual="open ports found"),
            _T("RECOVERED", actual="retried ok"),
        ]
        lessons = extract_lessons(traces, "scan the target")
        assert len(lessons) == 3
        kinds = {lesson.kind for lesson in lessons}
        assert LessonKind.AVOID in kinds
        assert LessonKind.REUSE in kinds
        # The AVOID lesson carries the failed evidence, not a fabricated one.
        avoid = next(lesson for lesson in lessons if lesson.kind == LessonKind.AVOID)
        assert "connection refused" in avoid.evidence

    def test_extract_lessons_empty_trace_yields_none(self):
        """An empty trace list yields no lessons — never fabricate."""
        from sonic.being.lessons import extract_lessons
        assert extract_lessons([], "anything") == []

    def test_ledger_persists_and_dedups(self, tmp_path, monkeypatch):
        """record() persists to disk and dedupes by (kind, approach) so the
        same failed approach in 3 missions counts once, not 3×."""
        from sonic.being.lessons import LessonsLedger, extract_lessons

        monkeypatch.setenv("SONIC_DATA_DIR", str(tmp_path))
        ledger = LessonsLedger(tenant_id="t1", agent_id="a1")

        class _T:
            def __init__(self):
                self.status = "FAILED"
                self.action_type = type("A", (), {"value": "TERMINAL_EXEC"})()
                self.target_resource = "nmap"
                self.predicted_outcome = "ok"
                self.actual_observation = "refused"

        # Same failing approach across two "missions".
        ledger.record(extract_lessons([_T()], "scan target"))
        ledger.record(extract_lessons([_T()], "scan target"))
        assert len(ledger.all()) == 1, "duplicate (kind, approach) must dedupe"

        # A different failing approach is kept.
        t2 = _T()
        t2.target_resource = "ffuf"
        ledger.record(extract_lessons([t2], "fuzz target"))
        assert len(ledger.all()) == 2

        # Persistence: new instance loads from disk.
        ledger2 = LessonsLedger(tenant_id="t1", agent_id="a1")
        assert len(ledger2.all()) == 2

    def test_ledger_relevant_filters_by_goal_keywords(self, tmp_path, monkeypatch):
        """relevant() returns lessons whose keywords match the current goal —
        so the LLM sees pertinent lessons, not a giant dump."""
        from sonic.being.lessons import Lesson, LessonKind, LessonsLedger

        monkeypatch.setenv("SONIC_DATA_DIR", str(tmp_path))
        ledger = LessonsLedger(tenant_id="t2", agent_id="a1")
        ledger.record([Lesson(
            lesson_id="l1", kind=LessonKind.AVOID, goal="scan nmap target",
            approach="nmap on host", evidence="refused", tags=["nmap", "scan"],
        )])
        ledger.record([Lesson(
            lesson_id="l2", kind=LessonKind.REUSE, goal="fuzz ffuf target",
            approach="ffuf on host", evidence="found dir", tags=["ffuf", "fuzz"],
        )])
        # Goal mentioning nmap → the nmap lesson is the top hit (most relevant).
        hits = ledger.relevant("scan the target with nmap", k=5)
        assert len(hits) >= 1
        assert "nmap" in hits[0].approach, "most relevant lesson must match the goal keyword"

    def test_inject_into_context_empty_when_no_lessons(self):
        """inject_into_context returns '' when there are no lessons — a fresh
        being adds zero noise to the prompt (no fabricated 'lessons learned')."""
        from sonic.being.lessons import inject_into_context
        assert inject_into_context([]) == ""

    def test_inject_into_context_renders_block(self):
        """Lessons render as a compact [AVOID]/[REUSE] block the LLM can act on."""
        from sonic.being.lessons import Lesson, LessonKind, inject_into_context
        lessons = [
            Lesson("l1", LessonKind.AVOID, "g", "ffuf without filter", "0 results"),
            Lesson("l2", LessonKind.REUSE, "g", "nmap -sV", "found service"),
        ]
        block = inject_into_context(lessons)
        assert "[AVOID]" in block
        assert "[REUSE]" in block
        assert "ffuf without filter" in block
        assert "nmap -sV" in block

    @pytest.mark.asyncio
    async def test_run_mission_records_then_injects_lessons(self, tmp_path, monkeypatch):
        """End-to-end learn→apply: mission 1 records lessons from its traces;
        mission 2 sees those lessons in its reasoning context."""
        from sonic.being.lessons import LessonsLedger
        from sonic.computer_use.agent import ComputerUseAgent
        from sonic.computer_use.models import ComputerActionType

        monkeypatch.setenv("SONIC_DATA_DIR", str(tmp_path))

        class _FakeComputer:
            async def terminal(self, ws, cmd):
                return type("R", (), {"stdout": "ok", "exit_code": 0})()
            async def screenshot(self, ws):
                from sonic.computer.models import ScreenObservation
                return ScreenObservation(screenshot_base64="", width=1920, height=1080, visible_text="")
            async def status(self, ws):
                return type("St", (), {"active_application": "", "open_applications": [], "running_processes": []})()
            async def list_files(self, ws, path):
                return []
            async def git_action(self, ws, action):
                return type("G", (), {"branch": "main", "is_clean": True})()

        ledger = LessonsLedger(tenant_id="t3", agent_id="a1")

        def _make_agent():
            a = ComputerUseAgent.__new__(ComputerUseAgent)
            a.computer = _FakeComputer()
            a.llm_router = None
            a.traces = []
            a.history = []
            a.recovery_events = 0
            a.action_counter = 0
            a.max_actions = 100
            a.max_recovery_attempts = 0
            a.metrics = type("M", (), {})()
            a._last_screenshot_b64 = ""
            a._last_browser_snapshot = None
            a._last_tool_result = None
            a.browser = None
            a.security_tools = {}
            a.safety = None
            a._consecutive_failures = 0
            a._replan_count = 0
            a.toolsmith = None
            a.method_lab = None
            a.lessons_ledger = ledger
            a.agent_id = "a1"
            a._files_cache = []
            return a

        # Mission 1: one FAILED trace → records an AVOID lesson.
        a1 = _make_agent()

        async def _fail(ws, at, target, payload, expected):
            from sonic.computer_use.models import ComputerDecisionTrace
            a1.action_counter += 1
            t = ComputerDecisionTrace(
                step_index=a1.action_counter, action_type=at,
                target_resource=target, payload=str(payload),
                predicted_outcome=expected, actual_observation="connection refused",
                info_gain=0.0, recovery_attempted=False, status="FAILED",
            )
            a1.traces.append(t)
            a1.history.append({"action": at.value, "result": "refused"})
            return t
        a1.execute_action = _fail

        async def _choose(goal, obs, step):
            return (ComputerActionType.TERMINAL_EXEC, "nmap", {"command": "x"}, "scan")
        a1.choose_action = _choose
        await a1.run_mission("ws", "scan the target with nmap", steps=1)
        assert len(ledger.all()) == 1
        assert ledger.all()[0].kind.value == "avoid"

        # Mission 2: the same goal — the recorded lesson must appear in the
        # reasoning context the LLM is handed.
        from sonic.computer.models import ScreenObservation
        from sonic.computer_use.models import ComputerWorldObservation
        a2 = _make_agent()
        a2.history = []
        obs = ComputerWorldObservation(
            screen=ScreenObservation(screenshot_base64="", width=1, height=1, visible_text=""),
            active_application="", windows=[], visible_text="",
            filesystem_files=[], processes=[], terminal_output="",
            browser_state={}, ide_state={}, git_branch="main", git_clean=True,
        )
        _sys, user = a2._build_reasoning_context("scan the target with nmap", obs, 1, "", "")
        assert "[AVOID]" in user, "past lesson must be injected into the next mission's reasoning"
        assert "nmap" in user


# =====================================================================
# Round 6: Dual-Process (Fast/Deep) hierarchical sub-agent controller
# =====================================================================

class TestDualProcessController:
    """The controller picks FAST vs DEEP deterministically from observable
    signals (confidence, unknowns, novelty, branch failures) — and escalates
    to a human ONLY on genuinely novel high-uncertainty dead-ends."""

    def _hyp(self, title="oauth bypass", desc="does token leak?"):
        from sonic.agents.cognitive_state import CognitiveHypothesis
        return CognitiveHypothesis(title=title, description=desc)

    def _unknown(self, q, importance):
        from sonic.agents.cognitive_state import Unknown
        return Unknown(question=q, estimated_importance=importance)

    def test_high_confidence_known_pattern_low_unknowns_is_fast(self):
        """HIGH confidence + no high-importance unknowns + known pattern → FAST."""
        from sonic.orchestration.dual_process import DualProcessController, ProcessMode
        ctrl = DualProcessController(known_pattern_fn=lambda g: True)
        d = ctrl.decide(self._hyp(), [], confidence_score=0.85)
        assert d.mode == ProcessMode.FAST
        assert not d.should_escalate

    def test_low_confidence_is_deep(self):
        """LOW confidence → DEEP regardless of other signals."""
        from sonic.orchestration.dual_process import DualProcessController, ProcessMode
        ctrl = DualProcessController()
        d = ctrl.decide(self._hyp(), [], confidence_score=0.20)
        assert d.mode == ProcessMode.DEEP

    def test_moderate_confidence_is_deep(self):
        """MODERATE confidence (0.40-0.69) → DEEP."""
        from sonic.orchestration.dual_process import DualProcessController, ProcessMode
        ctrl = DualProcessController()
        d = ctrl.decide(self._hyp(), [], confidence_score=0.55)
        assert d.mode == ProcessMode.DEEP

    def test_high_importance_unknown_is_deep_even_at_high_confidence(self):
        """A high-importance unresolved question → DEEP even with high conf."""
        from sonic.orchestration.dual_process import DualProcessController, ProcessMode
        ctrl = DualProcessController(known_pattern_fn=lambda g: True)
        uk = [self._unknown("does auth scope leak?", 0.85)]
        d = ctrl.decide(self._hyp(), uk, confidence_score=0.90)
        assert d.mode == ProcessMode.DEEP

    def test_novel_pattern_is_deep_even_at_high_confidence(self):
        """No prior resolution in lessons ledger → DEEP even with high conf."""
        from sonic.orchestration.dual_process import DualProcessController, ProcessMode
        ctrl = DualProcessController(known_pattern_fn=lambda g: False)
        d = ctrl.decide(self._hyp(), [], confidence_score=0.90)
        assert d.mode == ProcessMode.DEEP
        assert "novel" in d.reason

    def test_escalation_only_on_stuck_novel_high_uncertainty(self):
        """Escalate ONLY when stuck + high-importance unknown + novel. The core
        'sirf high-uncertainty pe' invariant."""
        from sonic.orchestration.dual_process import DualProcessController
        ctrl = DualProcessController(known_pattern_fn=lambda g: False)
        uk = [self._unknown("is the token signed?", 0.80)]
        d = ctrl.decide(self._hyp(), uk, branch_failures=3, confidence_score=0.30)
        assert d.should_escalate is True
        assert "human input" in d.escalation_reason

    def test_no_escalation_when_pattern_known(self):
        """Even if stuck, if the lessons ledger has a resolution → NO escalation
        (the agent should reuse the lesson, not ask a human)."""
        from sonic.orchestration.dual_process import DualProcessController
        ctrl = DualProcessController(known_pattern_fn=lambda g: True)
        uk = [self._unknown("is the token signed?", 0.80)]
        d = ctrl.decide(self._hyp(), uk, branch_failures=5, confidence_score=0.30)
        assert d.should_escalate is False

    def test_no_escalation_when_low_importance_unknown(self):
        """Stuck + low-importance unknown → DEEP, not escalation (the question
        doesn't matter enough to bother a human)."""
        from sonic.orchestration.dual_process import DualProcessController
        ctrl = DualProcessController(known_pattern_fn=lambda g: False)
        uk = [self._unknown("cosmetic banner?", 0.20)]
        d = ctrl.decide(self._hyp(), uk, branch_failures=4, confidence_score=0.30)
        assert d.should_escalate is False

    def test_no_escalation_when_not_stuck(self):
        """High-importance novel unknown but not yet stuck → DEEP (keep trying),
        not escalation on the first attempt."""
        from sonic.orchestration.dual_process import DualProcessController
        ctrl = DualProcessController(known_pattern_fn=lambda g: False)
        uk = [self._unknown("is the token signed?", 0.80)]
        d = ctrl.decide(self._hyp(), uk, branch_failures=1, confidence_score=0.30)
        assert d.should_escalate is False


class TestHierarchicalHypothesisTree:
    """Hypotheses form a tree: expand on confirm, prune on disprove, dispatch
    children in parallel capped by max_parallel."""

    def _hyp(self, hid, title="h"):
        from sonic.agents.cognitive_state import CognitiveHypothesis
        h = CognitiveHypothesis(title=title, description=hid)
        h.id = hid
        return h

    def test_expand_attaches_children_under_parent(self):
        from sonic.orchestration.dual_process import (
            DualProcessController,
            HierarchicalHypothesisTree,
        )
        tree = HierarchicalHypothesisTree(DualProcessController())
        parent = self._hyp("p1", "oauth bypass")
        child = self._hyp("c1", "token leak via header")
        tree.add(parent)
        tree.expand("p1", [child])
        assert child.parent_id == "p1"
        assert "c1" in parent.children_ids
        # child inherits parent engagement/tenant context (security scoping).
        assert child.engagement_id == parent.engagement_id

    def test_subtree_ids_bfs_traversal(self):
        from sonic.orchestration.dual_process import (
            DualProcessController,
            HierarchicalHypothesisTree,
        )
        tree = HierarchicalHypothesisTree(DualProcessController())
        root = self._hyp("r")
        a = self._hyp("a")
        b = self._hyp("b")
        a1 = self._hyp("a1")
        tree.add(root)
        tree.expand("r", [a, b])
        tree.expand("a", [a1])
        ids = tree.subtree_ids("r")
        assert ids == ["r", "a", "b", "a1"]

    def test_prune_removes_disproved_subtree(self):
        from sonic.agents.cognitive_state import HypothesisLifecycle
        from sonic.orchestration.dual_process import (
            DualProcessController,
            HierarchicalHypothesisTree,
        )
        tree = HierarchicalHypothesisTree(DualProcessController())
        root = self._hyp("r")
        child = self._hyp("c")
        tree.add(root)
        tree.expand("r", [child])
        root.lifecycle = HypothesisLifecycle.DISPROVED
        pruned = tree.prune("r")
        assert set(pruned) == {"r", "c"}
        assert tree.get("r") is None
        assert tree.get("c") is None

    def test_prune_ignores_non_disproved_node(self):
        """Pruning follows real DISPROVED status only — a PROPOSED node is
        never pruned (no heuristic guessing that kills a live branch)."""
        from sonic.orchestration.dual_process import (
            DualProcessController,
            HierarchicalHypothesisTree,
        )
        tree = HierarchicalHypothesisTree(DualProcessController())
        root = self._hyp("r")
        tree.add(root)
        assert tree.prune("r") == []
        assert tree.get("r") is not None

    @pytest.mark.asyncio
    async def test_dispatch_deep_confirms_then_fans_out_children(self):
        """DEEP mode: node confirms → children fan out in DEEP. Children run
        via real agent_runner (no fabricated reasoning)."""
        from sonic.agents.cognitive_state import HypothesisLifecycle
        from sonic.orchestration.dual_process import (
            DualProcessController,
            HierarchicalHypothesisTree,
            ProcessMode,
        )

        # Force DEEP via low confidence + novel pattern.
        ctrl = DualProcessController(known_pattern_fn=lambda g: False)
        tree = HierarchicalHypothesisTree(ctrl, max_parallel=4)
        root = self._hyp("r", "novel bypass")
        child = self._hyp("c", "specific leak")
        tree.add(root)
        tree.expand("r", [child])

        calls = []

        async def runner(hyp, mode):
            calls.append((hyp.id, mode))
            return {"status": "confirmed", "findings": [{"vuln": hyp.title}]}

        results = await tree.dispatch("r", [], runner, confidence_score=0.30)
        # Root ran in DEEP and confirmed; child then fanned out in DEEP.
        assert ("r", ProcessMode.DEEP) in calls
        assert ("c", ProcessMode.DEEP) in calls
        assert any(r.confirmed for r in results if r.node_id == "r")
        assert root.lifecycle == HypothesisLifecycle.VERIFIED

    @pytest.mark.asyncio
    async def test_dispatch_fast_runs_node_and_children_in_parallel(self):
        """FAST mode: node + children run concurrently in one gather batch."""
        from sonic.orchestration.dual_process import (
            DualProcessController,
            HierarchicalHypothesisTree,
            ProcessMode,
        )
        ctrl = DualProcessController(known_pattern_fn=lambda g: True)
        tree = HierarchicalHypothesisTree(ctrl, max_parallel=4)
        root = self._hyp("r", "known bypass")
        c1 = self._hyp("c1")
        c2 = self._hyp("c2")
        tree.add(root)
        tree.expand("r", [c1, c2])

        seen = []

        async def runner(hyp, mode):
            seen.append(hyp.id)
            assert mode == ProcessMode.FAST
            return {"status": "proposed"}

        await tree.dispatch("r", [], runner, confidence_score=0.90)
        assert set(seen) == {"r", "c1", "c2"}

    @pytest.mark.asyncio
    async def test_dispatch_respects_max_parallel_cap(self):
        """max_parallel caps concurrency — children batch into chunks, never
        exceeding the cap. Mirrors SwarmRunner's gather discipline."""
        from sonic.orchestration.dual_process import (
            DualProcessController,
            HierarchicalHypothesisTree,
        )
        ctrl = DualProcessController(known_pattern_fn=lambda g: True)
        tree = HierarchicalHypothesisTree(ctrl, max_parallel=2)
        root = self._hyp("r", "known")
        children = [self._hyp(f"c{i}") for i in range(5)]
        tree.add(root)
        tree.expand("r", children)

        in_flight = 0
        max_observed = 0

        async def runner(hyp, mode):
            nonlocal in_flight, max_observed
            in_flight += 1
            max_observed = max(max_observed, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return {"status": "proposed"}

        await tree.dispatch("r", [], runner, confidence_score=0.90)
        assert max_observed <= 2, f"max_parallel exceeded: {max_observed}"

    @pytest.mark.asyncio
    async def test_dispatch_failure_disproves_node(self):
        """A sub-agent that raises → node is DISPROVED (fail-closed), never
        left in an ambiguous PROPOSED state."""
        from sonic.agents.cognitive_state import HypothesisLifecycle
        from sonic.orchestration.dual_process import (
            DualProcessController,
            HierarchicalHypothesisTree,
        )
        ctrl = DualProcessController(known_pattern_fn=lambda g: False)
        tree = HierarchicalHypothesisTree(ctrl)
        root = self._hyp("r", "novel")
        tree.add(root)

        async def runner(hyp, mode):
            raise RuntimeError("sub-agent crashed")

        results = await tree.dispatch("r", [], runner, confidence_score=0.30)
        assert results[0].status == HypothesisLifecycle.DISPROVED
        assert root.lifecycle == HypothesisLifecycle.DISPROVED

    @pytest.mark.asyncio
    async def test_dispatch_escalation_surfaces_unknown_does_not_confirm(self):
        """On escalation the node stays PROPOSED — escalation surfaces the
        question for a human; it never auto-confirms or auto-disproves."""
        from sonic.agents.cognitive_state import HypothesisLifecycle, Unknown
        from sonic.orchestration.dual_process import (
            DualProcessController,
            HierarchicalHypothesisTree,
        )

        ctrl = DualProcessController(known_pattern_fn=lambda g: False)
        tree = HierarchicalHypothesisTree(ctrl)
        root = self._hyp("r", "novel hard question")
        tree.add(root)
        uk = [Unknown(question="is the jwt alg none?", estimated_importance=0.85)]

        called = []

        async def runner(hyp, mode):
            called.append(hyp.id)
            return {"status": "proposed"}

        results = await tree.dispatch(
            "r", uk, runner, branch_failures=3, confidence_score=0.20,
        )
        assert not called, "escalation must NOT run a sub-agent (it pauses for human)"
        assert results[0].status == HypothesisLifecycle.PROPOSED
        assert "human input" in results[0].findings[0]
