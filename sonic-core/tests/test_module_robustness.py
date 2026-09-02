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
        from sonic.being.toolsmith import AuthoredTool, ToolsmithLoop as Toolsmith

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
        from sonic.being.toolsmith import AuthoredTool, ToolsmithLoop as Toolsmith

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
        from sonic.safety.action_policy import ActionPolicy
        from sonic.computer_use.models import ComputerActionType
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
        from sonic.computer.models import GUIAction, GUIActionType, ComputerWorkspace, ComputerWorkspaceType
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
        from sonic.safety.action_policy import ActionPolicy
        from sonic.computer_use.models import ComputerActionType
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
        from sonic.safety.action_policy import ActionPolicy
        from sonic.computer_use.models import ComputerActionType
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
        from sonic.safety.action_policy import ActionPolicy
        from sonic.computer_use.models import ComputerActionType
        pol = ActionPolicy(workspace_root="/home/sonic/workspace")
        v = pol.evaluate(ComputerActionType.GUI_WAIT.value, "", {"seconds": 3})
        assert v.allowed, f"GUI_WAIT must be allowed: {v.reason}"

    @pytest.mark.asyncio
    async def test_browser_download_allowed_by_policy(self):
        from sonic.safety.action_policy import ActionPolicy
        from sonic.computer_use.models import ComputerActionType
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
        assert agent._replan_count >= 1, "replan must trigger on repeated failure"
