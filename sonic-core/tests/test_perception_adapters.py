from __future__ import annotations

import asyncio

import pytest

from sonic.computer.models import ComputerState, ScreenObservation
from sonic.computer.provider import ComputerProvider
from sonic.computer_use.perception_adapters import (
    BrowserPerceptionAdapter,
    ComputerPerceptionAdapter,
)
from sonic.computer_use.perception_bus import PerceptionBus


class StubProvider(ComputerProvider):
    async def create(self, tenant_id, engagement_id, workspace_type=None, profile=None):
        raise NotImplementedError

    async def destroy(self, workspace_id):
        return True

    async def status(self, workspace_id):
        return ComputerState(
            workspace_id=workspace_id,
            tenant_id="tenant",
            active_window="Editor",
            open_applications=["Editor", "Terminal"],
            running_processes=["editor"],
        )

    async def screenshot(self, workspace_id):
        return ScreenObservation(
            screenshot_base64="frame",
            width=1280,
            height=800,
            active_window="Editor",
            visible_text="Ready",
            detected_controls=["save"],
        )

    async def gui_action(self, workspace_id, action, actor="operator"):
        return await self.screenshot(workspace_id)

    async def terminal(self, workspace_id, command, timeout=60, actor="operator"):
        raise NotImplementedError

    async def read_file(self, workspace_id, path):
        raise NotImplementedError

    async def write_file(self, workspace_id, path, content, actor="operator"):
        raise NotImplementedError

    async def list_files(self, workspace_id, path="."):
        raise NotImplementedError

    async def process_list(self, workspace_id):
        from sonic.computer.models import ProcessInfo
        return [ProcessInfo(pid=7, name="editor", cpu_pct=1.5, memory_mb=12.0)]

    async def application_list(self, workspace_id):
        return []

    async def list_files(self, workspace_id, path="."):
        from sonic.computer.models import FileEntry
        return [
            FileEntry(
                path="notes.txt",
                name="notes.txt",
                is_dir=False,
                size_bytes=4,
                modified_at="2026-09-18T10:00:00+05:30",
            )
        ]

    async def launch_application(self, workspace_id, app_name, actor="operator"):
        return True

    async def close_application(self, workspace_id, app_name, actor="operator"):
        return True

    async def install_application(self, workspace_id, package_name, actor="operator"):
        return True, ""

    async def uninstall_application(self, workspace_id, package_name, actor="operator"):
        return True

    async def service_action(self, workspace_id, service_name, action, actor="operator"):
        raise NotImplementedError

    async def git_action(self, workspace_id, action, **kwargs):
        raise NotImplementedError


class StubBrowser:
    """Expose only the real BrowserAgent observation methods used by the adapter."""

    async def current_page_observation(self):
        return {
            "url": "https://target.invalid/",
            "title": "Target",
            "text": "Ready",
            "api_endpoints": ["/api/status"],
            "interactive_elements": [
                {"selector": "button:nth-of-type(1)", "tag": "button", "text": "Save"},
                {"selector": "input:nth-of-type(1)", "tag": "input", "text": ""},
            ],
        }

    async def screenshot(self):
        return type("Page", (), {"screenshot_b64": "browser-frame"})()


@pytest.mark.asyncio
async def test_adapter_publishes_real_provider_state():
    bus = PerceptionBus()
    adapter = ComputerPerceptionAdapter(StubProvider(), "ws-1", bus)

    snapshot = await adapter.poll_once()

    assert snapshot.version == 1
    assert snapshot.width == 1280
    assert snapshot.active_window == "Editor"
    assert snapshot.windows == ("Editor", "Terminal")
    assert snapshot.processes == ("editor",)
    assert snapshot.controls == ("save",)


@pytest.mark.asyncio
async def test_adapter_publishes_filesystem_and_process_patches_without_screenshot():
    bus = PerceptionBus()
    adapter = ComputerPerceptionAdapter(StubProvider(), "ws-1", bus)

    await adapter.poll_filesystem_once("/workspace")
    assert bus.current().filesystem_state == (
        "notes.txt|notes.txt|0|4|2026-09-18T10:00:00+05:30",
    )

    snapshot = await adapter.poll_processes_once()
    assert snapshot.processes == ("7|editor|RUNNING|1.500|12.000",)


@pytest.mark.asyncio
async def test_adapter_deduplicates_unchanged_provider_state():
    bus = PerceptionBus()
    adapter = ComputerPerceptionAdapter(StubProvider(), "ws-1", bus)

    first = await adapter.poll_once()
    second = await adapter.poll_once()

    assert second is first
    assert bus.last_changed_fields == ()


@pytest.mark.asyncio
async def test_adapter_stops_cleanly():
    bus = PerceptionBus()
    adapter = ComputerPerceptionAdapter(
        StubProvider(),
        "ws-1",
        bus,
        interval_seconds=0.001,
    )
    task = asyncio.create_task(adapter.run())
    await asyncio.sleep(0.005)
    adapter.stop()
    await asyncio.wait_for(task, timeout=1)


@pytest.mark.asyncio
async def test_browser_adapter_publishes_structured_dom_controls():
    class BrowserStub:
        async def current_page_observation(self):
            return {
                "url": "https://local.test",
                "title": "Research",
                "text": "Ready",
                "api_endpoints": [],
                "interactive_elements": [
                    {
                        "tag": "button",
                        "text": " Save " * 200,
                        "selector": "#save",
                        "visible": True,
                        "bbox": [1.2, 2.8, 100, 40],
                        "attributes": {"aria-label": "Save"},
                    }
                ],
            }

        async def screenshot(self):
            return type("Screen", (), {"screenshot_b64": "browser-frame"})()

    bus = PerceptionBus()
    from sonic.computer_use.perception_adapters import BrowserPerceptionAdapter

    snapshot = await BrowserPerceptionAdapter(BrowserStub(), bus).poll_once()
    control = snapshot.browser_state["controls"][0]
    assert snapshot.controls == ("#save",)
    assert snapshot.structured_sources == ("browser_dom",)
    assert control["tag"] == "button"
    assert len(control["text"]) == 500
    assert control["bbox"] == (1, 2, 100, 40)
    assert control["attributes"] == {"aria-label": "Save"}


@pytest.mark.asyncio
async def test_browser_adapter_publishes_existing_dom_observation():
    bus = PerceptionBus()
    adapter = BrowserPerceptionAdapter(StubBrowser(), bus)

    snapshot = await adapter.poll_once()

    assert snapshot.screen_hash
    assert snapshot.visible_text == "Ready"
    assert snapshot.active_window == "Target"
    assert snapshot.controls == (
        "button:nth-of-type(1)",
        "input:nth-of-type(1)",
    )
    assert snapshot.browser_state["url"] == "https://target.invalid/"
    assert snapshot.browser_state["api_endpoints"] == ["/api/status"]


def test_browser_adapter_requires_existing_provider_surface():
    with pytest.raises(TypeError, match="current_page_observation"):
        BrowserPerceptionAdapter(object(), PerceptionBus())
