"""Provider-backed adapters for the Continuum perception bus.

Adapters translate existing ComputerProvider observations into bus updates.
They do not execute host commands, invent events, or bypass provider policy.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

from sonic.computer.provider import ComputerProvider
from sonic.computer_use.perception_bus import PerceptionBus, PerceptionSnapshot


class BrowserPerceptionProvider(Protocol):
    """The existing browser observation surface consumed by the adapter.

    This deliberately describes the methods already exposed by
    ``BrowserAgent`` rather than introducing a second browser or accessibility
    API.  Providers that do not implement this surface cannot be adapted.
    """

    async def current_page_observation(self) -> dict[str, Any]: ...

    async def screenshot(self) -> Any: ...


class BrowserPerceptionAdapter:
    """Publish real DOM/browser observations into the Continuum bus.

    The browser observation is kept under ``browser_state``.  Interactive
    controls are copied from the provider's DOM observation only; no
    accessibility events or synthetic controls are generated.
    """

    def __init__(self, provider: BrowserPerceptionProvider, bus: PerceptionBus) -> None:
        if not callable(getattr(provider, "current_page_observation", None)):
            raise TypeError("browser provider must expose current_page_observation()")
        if not callable(getattr(provider, "screenshot", None)):
            raise TypeError("browser provider must expose screenshot()")
        self.provider = provider
        self.bus = bus

    @staticmethod
    def _structured_controls(interactive: Any) -> list[dict[str, Any]]:
        """Keep only bounded, actionable DOM metadata for fast consumers."""
        if not isinstance(interactive, (list, tuple)):
            return []
        controls: list[dict[str, Any]] = []
        for item in interactive[:100]:
            if not isinstance(item, dict) or not item.get("selector"):
                continue
            bbox = item.get("bbox")
            normalized_bbox = None
            if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                try:
                    normalized_bbox = tuple(int(value) for value in bbox)
                except (TypeError, ValueError):
                    normalized_bbox = None
            controls.append({
                "tag": str(item.get("tag", "")),
                "text": str(item.get("text", ""))[:500],
                "selector": str(item["selector"]),
                "visible": bool(item.get("visible", True)),
                "bbox": normalized_bbox,
                "attributes": {
                    str(key): str(value)[:500]
                    for key, value in (item.get("attributes") or {}).items()
                } if isinstance(item.get("attributes"), dict) else {},
            })
        return controls

    async def poll_once(self) -> PerceptionSnapshot:
        """Read the provider's live DOM and screenshot without inventing data."""
        observation, screen = await asyncio.gather(
            self.provider.current_page_observation(),
            self.provider.screenshot(),
        )
        if not isinstance(observation, dict):
            raise TypeError("browser observation must be a mapping")

        structured_controls = self._structured_controls(
            observation.get("interactive_elements", ())
        )
        controls = tuple(item["selector"] for item in structured_controls)
        browser_state = {
            key: observation[key]
            for key in ("url", "title", "text", "api_endpoints")
            if key in observation
        }
        browser_state["controls"] = structured_controls
        structured_sources = ("browser_dom",) if (
            observation.get("text") or structured_controls
        ) else ()
        return self.bus.publish(
            screenshot_base64=str(getattr(screen, "screenshot_b64", "") or ""),
            active_window=str(observation.get("title", "") or ""),
            visible_text=str(observation.get("text", "") or ""),
            controls=controls,
            browser_state=browser_state,
            structured_sources=structured_sources,
        )


class PerceptionEventSource(Protocol):
    """Existing provider event surface consumed without inventing events."""

    def events(self) -> AsyncIterator[dict[str, Any]]: ...


class DockerContainerEventSource:
    """Stream lifecycle events emitted by Docker for one container."""

    def __init__(self, container_id: str) -> None:
        if not container_id.strip():
            raise ValueError("container_id must not be empty")
        self.container_id = container_id

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        process = await asyncio.create_subprocess_exec(
            "docker", "events",
            "--filter", f"container={self.container_id}",
            "--format", "{{json .}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            assert process.stdout is not None
            async for raw_line in process.stdout:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                event = json.loads(line)
                status = str(event.get("status", "")).lower()
                runtime_state = {
                    "start": "RUNNING",
                    "restart": "RUNNING",
                    "create": "CREATED",
                    "pause": "PAUSED",
                    "unpause": "RUNNING",
                    "stop": "STOPPED",
                    "die": "STOPPED",
                    "destroy": "DESTROYED",
                }.get(status)
                if runtime_state is not None:
                    yield {"runtime_state": runtime_state}
        finally:
            if process.returncode is None:
                process.terminate()
            await process.wait()


class StructuredPerceptionEventAdapter:
    """Apply provider-emitted structured events directly to the perception bus.

    Event sources own the truth and may emit only fields understood by
    ``PerceptionBus.apply_patch``.  This adapter never screenshots, polls, or
    synthesizes a transition when the source has no event.
    """

    _ALLOWED_FIELDS = {
        "screen_hash",
        "width",
        "height",
        "active_window",
        "windows",
        "processes",
        "visible_text",
        "controls",
        "browser_state",
        "filesystem_state",
        "runtime_state",
    }

    def __init__(self, source: PerceptionEventSource, bus: PerceptionBus) -> None:
        if not callable(getattr(source, "events", None)):
            raise TypeError("event source must expose events()")
        self.source = source
        self.bus = bus
        self._stop_event = asyncio.Event()

    def stop(self) -> None:
        """Stop after the current source event is consumed."""
        self._stop_event.set()

    async def run(
        self,
        *,
        on_error: Callable[[Exception], Awaitable[None] | None] | None = None,
    ) -> None:
        """Consume real source events until stopped or the source completes."""
        self._stop_event.clear()
        async for event in self.source.events():
            if self._stop_event.is_set():
                break
            try:
                if not isinstance(event, dict):
                    raise TypeError("perception event must be a mapping")
                unknown = set(event) - self._ALLOWED_FIELDS
                if unknown:
                    raise ValueError(
                        f"Unsupported perception event fields: {sorted(unknown)}"
                    )
                self.bus.apply_patch(**event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if on_error is None:
                    raise
                result = on_error(exc)
                if asyncio.iscoroutine(result):
                    await result


class ComputerPerceptionAdapter:
    """Publish real provider state and screen observations into a bus."""

    def __init__(
        self,
        provider: ComputerProvider,
        workspace_id: str,
        bus: PerceptionBus,
        *,
        interval_seconds: float = 0.25,
    ) -> None:
        if not workspace_id.strip():
            raise ValueError("workspace_id must not be empty")
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than zero")
        self.provider = provider
        self.workspace_id = workspace_id
        self.bus = bus
        self.interval_seconds = interval_seconds
        self._stop_event = asyncio.Event()

    async def poll_once(self) -> PerceptionSnapshot:
        """Read one provider snapshot and publish it atomically."""
        state, screen = await asyncio.gather(
            self.provider.status(self.workspace_id),
            self.provider.screenshot(self.workspace_id),
        )
        return self.bus.publish(
            screenshot_base64=screen.screenshot_base64,
            width=screen.width,
            height=screen.height,
            active_window=screen.active_window or state.active_window,
            windows=state.open_applications,
            processes=state.running_processes,
            visible_text=screen.visible_text,
            controls=screen.detected_controls,
            visual_residuals=getattr(screen, "changed_regions", ()),
            structured_sources=("desktop_state", "window_state"),
        )

    async def poll_filesystem_once(self, path: str = ".") -> PerceptionSnapshot:
        """Publish a provider-backed filesystem listing as an incremental patch."""
        entries = await self.provider.list_files(self.workspace_id, path)
        filesystem_state = tuple(
            f"{entry.path}|{entry.name}|{int(entry.is_dir)}|"
            f"{entry.size_bytes}|{entry.modified_at}"
            for entry in entries
        )
        return self.bus.apply_patch(filesystem_state=filesystem_state)

    async def poll_processes_once(self) -> PerceptionSnapshot:
        """Publish provider process metadata without taking a screenshot."""
        processes = await self.provider.process_list(self.workspace_id)
        process_state = tuple(
            f"{process.pid}|{process.name}|{process.status}|"
            f"{process.cpu_pct:.3f}|{process.memory_mb:.3f}"
            for process in processes
        )
        return self.bus.apply_patch(processes=process_state)

    async def run(
        self,
        *,
        on_error: Callable[[Exception], Awaitable[None] | None] | None = None,
    ) -> None:
        """Continuously adapt provider observations until stopped."""
        self._stop_event.clear()
        while not self._stop_event.is_set():
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if on_error is not None:
                    result = on_error(exc)
                    if asyncio.iscoroutine(result):
                        await result
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.interval_seconds,
                )
            except TimeoutError:
                continue

    def stop(self) -> None:
        """Request a running adapter loop to stop after its current poll."""
        self._stop_event.set()
