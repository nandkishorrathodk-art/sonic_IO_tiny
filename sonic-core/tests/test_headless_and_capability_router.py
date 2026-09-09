"""
Unit & integration tests for HeadlessComputeProvider and CapabilityRouter.
Covers:
  - HeadlessComputeProvider terminal execution
  - Native async TCP port scanning against 127.0.0.1
  - Direct HTTP probing via httpx
  - Local sandboxed filesystem operations and path traversal security
  - Graceful synthetic observations for unsupported GUI actions
  - CapabilityRouter action classification into COMPUTER vs HEADLESS substrates
  - Provider resolution and automatic fallback on container unavailability or exit 125
"""

import asyncio
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock

import pytest

from sonic.computer.headless import HeadlessComputeProvider, HeadlessFileContent
from sonic.computer.models import GUIAction, GUIActionType
from sonic.computer_use.models import ComputerActionType
from sonic.execution.capability_router import CapabilityRouter, ExecutionSubstrate
from sonic.sandbox.provider import ComputeProvider, ExecResult


@pytest.mark.no_live_infra
@pytest.mark.asyncio
async def test_headless_terminal_execution(tmp_path):
    # Host execution is OPT-IN: default is fail-closed (False) so a fallback
    # substrate can never silently run directly on the host OS.
    provider = HeadlessComputeProvider(base_dir=tmp_path, allow_host_execution=True)
    ws = await provider.create(tenant_id="test-tenant", engagement_id="eng-1")
    assert ws.id is not None

    # Test terminal execution
    res = await provider.terminal(ws.id, "echo sonic_headless_test_ok")
    assert res.exit_code == 0
    assert "sonic_headless_test_ok" in res.stdout
    assert res.sandbox_id == ws.id

    # Test execute interface (from ComputeProvider contract)
    res_exec = await provider.execute(ws.id, ["echo", "execute_contract_ok"])
    assert res_exec.exit_code == 0
    assert "execute_contract_ok" in res_exec.stdout

    # Test command timeout handling
    # Use python sleep command that exceeds a tiny timeout
    timeout_cmd = "python -c \"import time; time.sleep(2)\""
    res_timeout = await provider.terminal(ws.id, timeout_cmd, timeout=1)
    assert res_timeout.exit_code == 124
    assert res_timeout.timed_out is True
    assert "timed out" in res_timeout.stderr.lower()


@pytest.mark.no_live_infra
@pytest.mark.asyncio
async def test_headless_filesystem_operations_and_safety(tmp_path):
    provider = HeadlessComputeProvider(base_dir=tmp_path)
    ws_id = "ws-fs-test"

    # Write file
    ok = await provider.write_file(ws_id, "data/target.txt", "hello headless filesystem")
    assert ok is True

    # Read file
    content = await provider.read_file(ws_id, "data/target.txt")
    assert isinstance(content, HeadlessFileContent)
    assert content == "hello headless filesystem"
    # Test decode method compatibility for ComputeProvider callers
    assert content.decode("utf-8") == "hello headless filesystem"

    # Read binary
    content_bytes = await provider.read_file_bytes(ws_id, "data/target.txt")
    assert content_bytes == b"hello headless filesystem"

    # List files
    entries = await provider.list_files(ws_id, "data")
    assert len(entries) == 1
    assert entries[0].name == "target.txt"
    assert entries[0].is_dir is False
    assert entries[0].size_bytes > 0

    # Test path traversal prevention
    with pytest.raises(ValueError, match="Path traversal attempted"):
        await provider.write_file(ws_id, "../../outside.txt", "malicious_payload")

    with pytest.raises(ValueError, match="Path traversal attempted"):
        await provider.read_file(ws_id, "../../outside.txt")


@pytest.mark.no_live_infra
@pytest.mark.asyncio
async def test_headless_gui_unsupported_graceful():
    provider = HeadlessComputeProvider()
    ws_id = "ws-gui-test"

    # Screenshot returns graceful synthetic headless observation
    obs = await provider.screenshot(ws_id)
    assert obs.desktop_state == "HEADLESS"
    assert obs.width == 0
    assert obs.height == 0
    assert "NO GRAPHICAL DISPLAY" in obs.visible_text

    # GUI Action returns graceful synthetic observation
    action = GUIAction(action=GUIActionType.CLICK, x=100, y=100)
    obs_action = await provider.gui_action(ws_id, action)
    assert obs_action.desktop_state == "HEADLESS"
    assert "unsupported in headless" in obs_action.visible_text

    # Convenience methods
    obs_click = await provider.click(ws_id, 200, 300)
    assert obs_click.desktop_state == "HEADLESS"

    obs_type = await provider.type(ws_id, "test text")
    assert obs_type.desktop_state == "HEADLESS"


@pytest.mark.no_live_infra
@pytest.mark.asyncio
async def test_headless_http_probe():
    provider = HeadlessComputeProvider()

    # Start a lightweight local HTTP server for testing
    body_data = b'{"status": "reachable"}'

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        await reader.read(1024)
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            b"Connection: close\r\n"
            + f"Content-Length: {len(body_data)}\r\n\r\n".encode()
            + body_data
        )
        writer.write(response)
        await writer.drain()
        writer.close()
        with suppress(Exception):
            await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        probe = await provider.http_probe(f"http://127.0.0.1:{port}/api/health", method="GET")
        assert probe["status_code"] == 200
        assert probe["ok"] is True
        assert '{"status": "reachable"}' in probe["body"]
        assert "application/json" in probe["headers"].get("content-type", "")
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.no_live_infra
@pytest.mark.asyncio
async def test_async_tcp_port_scanning():
    provider = HeadlessComputeProvider()

    # Start an ephemeral TCP server to represent an active listening port (e.g. 12000 or ephemeral)
    server = None
    target_port = 12000
    try:
        server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", target_port)
    except OSError:
        # If port 12000 is occupied by the host environment, bind to an ephemeral port
        server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
        target_port = server.sockets[0].getsockname()[1]

    # Use a port that is guaranteed closed (pick high port)
    closed_port = 59991

    try:
        results = await provider.scan_ports("127.0.0.1", [target_port, closed_port], timeout=1.0)
        assert len(results) == 2

        open_res = next(r for r in results if r["port"] == target_port)
        assert open_res["state"] == "open"
        assert open_res["open"] is True
        assert open_res["protocol"] == "tcp"

        closed_res = next(r for r in results if r["port"] == closed_port)
        assert closed_res["state"] in ("closed", "timeout")
        assert closed_res["open"] is False
    finally:
        if server:
            server.close()
            await server.wait_closed()


@pytest.mark.no_live_infra
def test_capability_router_action_classification():
    # GUI actions -> COMPUTER
    gui_actions = [
        ComputerActionType.GUI_CLICK,
        ComputerActionType.GUI_DOUBLE_CLICK,
        ComputerActionType.GUI_RIGHT_CLICK,
        ComputerActionType.GUI_TYPE,
        ComputerActionType.GUI_KEYPRESS,
        ComputerActionType.GUI_MOVE,
        ComputerActionType.GUI_SCROLL,
        ComputerActionType.GUI_SCREENSHOT,
        ComputerActionType.GUI_DRAG,
        ComputerActionType.GUI_WAIT,
    ]
    for act in gui_actions:
        assert CapabilityRouter.route_action(act) == ExecutionSubstrate.COMPUTER

    # Desktop app lifecycle actions -> COMPUTER
    app_actions = [
        ComputerActionType.APP_LAUNCH,
        ComputerActionType.APP_CLOSE,
        ComputerActionType.APP_FOCUS,
        ComputerActionType.APP_INSTALL,
    ]
    for act in app_actions:
        assert CapabilityRouter.route_action(act) == ExecutionSubstrate.COMPUTER

    # Interactive browser actions -> COMPUTER
    assert CapabilityRouter.route_action(ComputerActionType.BROWSER_CLICK) == ExecutionSubstrate.COMPUTER
    assert CapabilityRouter.route_action(ComputerActionType.BROWSER_TYPE) == ExecutionSubstrate.COMPUTER
    assert CapabilityRouter.route_action(ComputerActionType.BROWSER_SCREENSHOT) == ExecutionSubstrate.COMPUTER
    assert CapabilityRouter.route_action(ComputerActionType.BROWSER_WAIT) == ExecutionSubstrate.COMPUTER

    # BROWSER_NAVIGATE: headless fetch suffices vs interactive browser requested
    assert CapabilityRouter.route_action(ComputerActionType.BROWSER_NAVIGATE, {}) == ExecutionSubstrate.HEADLESS
    assert (
        CapabilityRouter.route_action(ComputerActionType.BROWSER_NAVIGATE, {"interactive": True})
        == ExecutionSubstrate.COMPUTER
    )
    assert (
        CapabilityRouter.route_action(ComputerActionType.BROWSER_NAVIGATE, {"requires_gui": True})
        == ExecutionSubstrate.COMPUTER
    )
    assert (
        CapabilityRouter.route_action(ComputerActionType.BROWSER_NAVIGATE, {"render_js": True})
        == ExecutionSubstrate.COMPUTER
    )

    # Headless actions -> HEADLESS
    headless_actions = [
        ComputerActionType.TERMINAL_EXEC,
        ComputerActionType.FILE_READ,
        ComputerActionType.FILE_WRITE,
        ComputerActionType.SECURITY_TOOL,
        ComputerActionType.GIT_BRANCH,
        ComputerActionType.GIT_COMMIT,
        ComputerActionType.SERVICE_ACTION,
        ComputerActionType.TOOL_AUTHOR,
        ComputerActionType.TOOL_RUN,
        ComputerActionType.METHOD_INVENT,
    ]
    for act in headless_actions:
        assert CapabilityRouter.route_action(act) == ExecutionSubstrate.HEADLESS


@pytest.mark.no_live_infra
def test_capability_router_provider_resolution():
    router = CapabilityRouter()

    # When preferred is already HeadlessComputeProvider
    headless = HeadlessComputeProvider()
    assert router.resolve_provider(headless) is headless

    # When preferred is None
    resolved = router.resolve_provider(None)
    assert isinstance(resolved, HeadlessComputeProvider)

    # When task_type is explicitly HEADLESS
    resolved_task = router.resolve_provider(None, task_type="HEADLESS")
    assert isinstance(resolved_task, HeadlessComputeProvider)

    # When preferred is unconfigured Daytona (no api_key)
    dummy_daytona = MagicMock()
    dummy_daytona.__class__.__name__ = "DaytonaComputerProvider"
    dummy_daytona.api_key = ""
    resolved_daytona = router.resolve_provider(dummy_daytona)
    assert isinstance(resolved_daytona, HeadlessComputeProvider)

    # When preferred is Docker and daemon is marked unavailable
    dummy_docker = MagicMock()
    dummy_docker.__class__.__name__ = "DockerComputerProvider"
    dummy_docker._daemon_checked = False
    resolved_docker = router.resolve_provider(dummy_docker)
    assert isinstance(resolved_docker, HeadlessComputeProvider)


@pytest.mark.no_live_infra
@pytest.mark.asyncio
async def test_capability_router_execute_with_exit_125_fallback(tmp_path):
    headless = HeadlessComputeProvider(base_dir=tmp_path, allow_host_execution=True)
    router = CapabilityRouter(headless_provider=headless)

    # Create a mock Docker provider that passes initial check but returns exit code 125
    # (simulating container was killed or not running)
    failing_provider = MagicMock(spec=ComputeProvider)
    failing_provider.__class__.__name__ = "SimulatedSandboxProvider"
    failing_provider.terminal = AsyncMock(
        return_value=ExecResult(
            command="echo test",
            exit_code=125,
            stdout="",
            stderr="container is not running; command blocked fail-closed",
        )
    )

    # Execute with fallback: should detect exit code 125 and automatically run on HeadlessComputeProvider
    res = await router.execute_with_fallback(
        provider=failing_provider,
        workspace_id="ws-test",
        command="echo fallback_success",
    )
    assert res.exit_code == 0
    assert "fallback_success" in res.stdout

@pytest.mark.no_live_infra
@pytest.mark.asyncio
async def test_headless_default_fail_closed_no_silent_host_execution():
    """
    The audit backdoor: HeadlessComputeProvider previously defaulted to
    allow_host_execution=True — so when Docker/Daytona were down, the
    CapabilityRouter silently fell back to a provider that ran commands directly
    on the host OS (zero isolation). Now the default is fail-closed:
    - constructor default → exit 126 (no host subprocess spawned)
    - CapabilityRouter's fallback provider is constructed host-execution-DISABLED
    """
    provider = HeadlessComputeProvider()
    res = await provider.execute("ws-test", "echo should_not_run")
    assert res.exit_code == 126
    assert "FAIL-CLOSED" in res.stderr

    # CapabilityRouter safe fallback — default construction is host-execution-safe.
    router = CapabilityRouter()
    fallback = router.resolve_provider(None)
    assert fallback.allow_host_execution is False

    # execute_with_fallback with a unavailable Docker provider must fail-closed,
    # NOT silently run on the host machine.
    failing = MagicMock(spec=ComputeProvider)
    failing.__class__.__name__ = "DockerComputerProvider"
    failing.terminal = AsyncMock(
        return_value=ExecResult(command="echo x", exit_code=125, stdout="", stderr="")
    )
    res = await router.execute_with_fallback(
        provider=failing,
        workspace_id="ws-test",
        command="echo host_backdoor",
    )
    assert res.exit_code == 126
    assert "FAIL-CLOSED" in res.stderr
