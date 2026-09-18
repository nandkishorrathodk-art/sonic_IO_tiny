"""Low-latency, versioned perception state for computer-use actions.

The bus is intentionally local and dependency-free.  It does not replace
semantic browser/accessibility providers or the safety policy; it gives those
providers one shared, immutable-ish snapshot and lets fast actions reject
stale targets before dispatch.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import Any


@dataclass(frozen=True)
class TargetMatch:
    """A semantic target resolved against one perception snapshot."""

    query: str
    source: str
    bbox: tuple[int, int, int, int]
    confidence: float
    state_version: int
    observed_at_ns: int


@dataclass(frozen=True)
class PerceptionSnapshot:
    """Versioned state shared by all workers for a single computer."""

    version: int
    screen_hash: str
    width: int
    height: int
    active_window: str
    windows: tuple[str, ...]
    processes: tuple[str, ...]
    visible_text: str
    controls: tuple[str, ...]
    browser_state: dict[str, Any]
    filesystem_state: tuple[str, ...]
    runtime_state: str
    structured_sources: tuple[str, ...]
    visual_residuals: tuple[tuple[int, int, int, int], ...]
    observed_at_ns: int


@dataclass(frozen=True)
class ActionFuture:
    """A prepared action that is valid only for its originating snapshot."""

    action: str
    target: TargetMatch | None
    state_version: int
    created_at_ns: int


@dataclass(frozen=True)
class PerceptionChange:
    """A minimal state transition emitted to low-latency consumers."""

    previous_version: int
    version: int
    changed_fields: tuple[str, ...]
    snapshot: PerceptionSnapshot
    observed_at_ns: int


class PerceptionBus:
    """Thread-safe state index with O(1) snapshot and stale-state checks."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._version = 0
        self._snapshot = PerceptionSnapshot(
            version=0,
            screen_hash="",
            width=0,
            height=0,
            active_window="",
            windows=(),
            processes=(),
            visible_text="",
            controls=(),
            browser_state={},
            filesystem_state=(),
            runtime_state="UNKNOWN",
            structured_sources=(),
            visual_residuals=(),
            observed_at_ns=time.perf_counter_ns(),
        )
        self._targets: dict[tuple[int, str], TargetMatch] = {}
        self._last_publish_latency_ns = 0
        self._last_changed_fields: tuple[str, ...] = ()
        self._subscribers: list[Callable[[PerceptionChange], None]] = []

    def subscribe(self, callback: Callable[[PerceptionChange], None]) -> Callable[[], None]:
        """Subscribe to state transitions and return an idempotent unsubscribe callback."""
        with self._lock:
            self._subscribers.append(callback)

        removed = False

        def unsubscribe() -> None:
            nonlocal removed
            if removed:
                return
            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)
                removed = True

        return unsubscribe

    @staticmethod
    def _changed_fields(
        previous: PerceptionSnapshot,
        current: PerceptionSnapshot,
    ) -> tuple[str, ...]:
        fields = (
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
            "structured_sources",
            "visual_residuals",
        )
        return tuple(
            field for field in fields
            if getattr(previous, field) != getattr(current, field)
        )

    def _emit(self, change: PerceptionChange, subscribers: list[Callable[[PerceptionChange], None]]) -> None:
        for callback in subscribers:
            try:
                callback(change)
            except Exception:
                # A telemetry/reflex subscriber must never break observation.
                continue

    @staticmethod
    def _screen_hash(screenshot_base64: str) -> str:
        if not screenshot_base64:
            return ""
        return hashlib.blake2s(
            screenshot_base64.encode("utf-8"), digest_size=16
        ).hexdigest()

    def publish(
        self,
        *,
        screenshot_base64: str = "",
        screen_hash: str | None = None,
        width: int = 0,
        height: int = 0,
        active_window: str = "",
        windows: list[str] | tuple[str, ...] = (),
        processes: list[str] | tuple[str, ...] = (),
        visible_text: str = "",
        controls: list[str] | tuple[str, ...] = (),
        browser_state: dict[str, Any] | None = None,
        filesystem_state: list[str] | tuple[str, ...] = (),
        runtime_state: str = "UNKNOWN",
        structured_sources: list[str] | tuple[str, ...] = (),
        visual_residuals: list[tuple[int, int, int, int]] | tuple[tuple[int, int, int, int], ...] = (),
    ) -> PerceptionSnapshot:
        """Publish one live observation and atomically advance its version."""
        started = time.perf_counter_ns()
        with self._lock:
            previous = self._snapshot
            candidate = PerceptionSnapshot(
                version=previous.version + 1,
                screen_hash=screen_hash if screen_hash is not None else self._screen_hash(screenshot_base64),
                width=max(0, int(width)),
                height=max(0, int(height)),
                active_window=str(active_window or ""),
                windows=tuple(str(item) for item in windows),
                processes=tuple(str(item) for item in processes),
                visible_text=str(visible_text or ""),
                controls=tuple(str(item) for item in controls),
                browser_state=dict(browser_state or {}),
                filesystem_state=tuple(str(item) for item in filesystem_state),
                runtime_state=str(runtime_state or "UNKNOWN"),
                structured_sources=tuple(str(item) for item in structured_sources),
                visual_residuals=self._normalize_regions(visual_residuals),
                observed_at_ns=time.perf_counter_ns(),
            )
            changed_fields = self._changed_fields(previous, candidate)
            if not changed_fields:
                self._last_changed_fields = ()
                self._last_publish_latency_ns = max(0, time.perf_counter_ns() - started)
                return previous
            now = time.perf_counter_ns()
            self._version += 1
            self._snapshot = PerceptionSnapshot(
                version=self._version,
                screen_hash=screen_hash if screen_hash is not None else self._screen_hash(screenshot_base64),
                width=max(0, int(width)),
                height=max(0, int(height)),
                active_window=str(active_window or ""),
                windows=tuple(str(item) for item in windows),
                processes=tuple(str(item) for item in processes),
                visible_text=str(visible_text or ""),
                controls=tuple(str(item) for item in controls),
                browser_state=dict(browser_state or {}),
                filesystem_state=tuple(str(item) for item in filesystem_state),
                runtime_state=str(runtime_state or "UNKNOWN"),
                structured_sources=tuple(str(item) for item in structured_sources),
                visual_residuals=self._normalize_regions(visual_residuals),
                observed_at_ns=now,
            )
            self._targets.clear()
            self._last_changed_fields = changed_fields
            self._last_publish_latency_ns = max(0, time.perf_counter_ns() - started)
            change = PerceptionChange(
                previous_version=previous.version,
                version=self._snapshot.version,
                changed_fields=changed_fields,
                snapshot=self._snapshot,
                observed_at_ns=now,
            )
            subscribers = list(self._subscribers)
            snapshot = self._snapshot
        self._emit(change, subscribers)
        return snapshot

    def apply_patch(self, **changes: Any) -> PerceptionSnapshot:
        """Apply only changed fields without requiring a new screenshot/OCR frame."""
        allowed = {
            "screen_hash", "width", "height", "active_window", "windows",
            "processes", "visible_text", "controls", "browser_state",
            "filesystem_state", "runtime_state",
            "structured_sources", "visual_residuals",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Unsupported perception fields: {sorted(unknown)}")
        current = self.current()
        values = {
            "screenshot_base64": "",
            "screen_hash": changes.get("screen_hash", current.screen_hash),
            "width": changes.get("width", current.width),
            "height": changes.get("height", current.height),
            "active_window": changes.get("active_window", current.active_window),
            "windows": changes.get("windows", current.windows),
            "processes": changes.get("processes", current.processes),
            "visible_text": changes.get("visible_text", current.visible_text),
            "controls": changes.get("controls", current.controls),
            "browser_state": changes.get("browser_state", current.browser_state),
            "filesystem_state": changes.get("filesystem_state", current.filesystem_state),
            "runtime_state": changes.get("runtime_state", current.runtime_state),
            "structured_sources": changes.get("structured_sources", current.structured_sources),
            "visual_residuals": changes.get("visual_residuals", current.visual_residuals),
        }
        return self.publish(**values)

    def current(self) -> PerceptionSnapshot:
        """Return the latest snapshot without copying image data."""
        with self._lock:
            return self._snapshot

    def register_target(
        self,
        query: str,
        bbox: tuple[int, int, int, int],
        *,
        source: str,
        confidence: float,
        state_version: int | None = None,
    ) -> TargetMatch:
        """Index a semantic target against the current state version."""
        with self._lock:
            version = self._version if state_version is None else state_version
            match = TargetMatch(
                query=query,
                source=source,
                bbox=tuple(int(value) for value in bbox),
                confidence=max(0.0, min(1.0, float(confidence))),
                state_version=version,
                observed_at_ns=time.perf_counter_ns(),
            )
            self._targets[(version, query.strip().lower())] = match
            return match

    def resolve(self, query: str) -> TargetMatch | None:
        """Resolve a target only from the current, non-stale snapshot."""
        with self._lock:
            return self._targets.get((self._version, query.strip().lower()))

    def prepare(self, action: str, query: str = "") -> ActionFuture:
        """Prepare an action for the current version; execution validates it."""
        with self._lock:
            return ActionFuture(
                action=action,
                target=self.resolve(query) if query else None,
                state_version=self._version,
                created_at_ns=time.perf_counter_ns(),
            )

    def is_current(self, future: ActionFuture) -> bool:
        """Return false when a new observation invalidated a prepared action."""
        with self._lock:
            return future.state_version == self._version

    def invalidate(self) -> int:
        """Advance the version when an external action may have changed UI state."""
        with self._lock:
            self._version += 1
            self._targets.clear()
            self._snapshot = PerceptionSnapshot(
                version=self._version,
                screen_hash=self._snapshot.screen_hash,
                width=self._snapshot.width,
                height=self._snapshot.height,
                active_window=self._snapshot.active_window,
                windows=self._snapshot.windows,
                processes=self._snapshot.processes,
                visible_text=self._snapshot.visible_text,
                controls=self._snapshot.controls,
                browser_state=dict(self._snapshot.browser_state),
                filesystem_state=self._snapshot.filesystem_state,
                runtime_state=self._snapshot.runtime_state,
                structured_sources=self._snapshot.structured_sources,
                visual_residuals=self._snapshot.visual_residuals,
                observed_at_ns=time.perf_counter_ns(),
            )
            return self._version

    @property
    def last_update_latency_ns(self) -> int:
        """Time spent publishing the latest snapshot, useful for telemetry."""
        with self._lock:
            return self._last_publish_latency_ns

    @property
    def last_changed_fields(self) -> tuple[str, ...]:
        """Return fields changed by the latest publish, or empty for a no-op."""
        with self._lock:
            return self._last_changed_fields

    @property
    def visual_changed(self) -> bool:
        """Whether the latest publication changed the visual frame."""
        with self._lock:
            return "screen_hash" in self._last_changed_fields

    @staticmethod
    def _normalize_regions(regions: Any) -> tuple[tuple[int, int, int, int], ...]:
        normalized: list[tuple[int, int, int, int]] = []
        if not isinstance(regions, (list, tuple)):
            return ()
        for region in regions[:256]:
            if not isinstance(region, (list, tuple)) or len(region) != 4:
                continue
            try:
                x1, y1, x2, y2 = (int(value) for value in region)
            except (TypeError, ValueError):
                continue
            if x2 <= x1 or y2 <= y1 or x1 < 0 or y1 < 0:
                continue
            normalized.append((x1, y1, x2, y2))
        return tuple(normalized)

    @property
    def structured_state_available(self) -> bool:
        """Whether a real structured source can answer part of the state."""
        with self._lock:
            return bool(self._snapshot.structured_sources)

    @property
    def visual_residuals(self) -> tuple[tuple[int, int, int, int], ...]:
        """Provider-reported changed regions; empty when unsupported."""
        with self._lock:
            return self._snapshot.visual_residuals
