"""Low-latency, versioned perception state for computer-use actions.

The bus is intentionally local and dependency-free.  It does not replace
semantic browser/accessibility providers or the safety policy; it gives those
providers one shared, immutable-ish snapshot and lets fast actions reject
stale targets before dispatch.
"""

from __future__ import annotations

import hashlib
import time
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
    observed_at_ns: int


@dataclass(frozen=True)
class ActionFuture:
    """A prepared action that is valid only for its originating snapshot."""

    action: str
    target: TargetMatch | None
    state_version: int
    created_at_ns: int


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
            observed_at_ns=time.perf_counter_ns(),
        )
        self._targets: dict[tuple[int, str], TargetMatch] = {}
        self._last_publish_latency_ns = 0

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
        width: int = 0,
        height: int = 0,
        active_window: str = "",
        windows: list[str] | tuple[str, ...] = (),
        processes: list[str] | tuple[str, ...] = (),
        visible_text: str = "",
        controls: list[str] | tuple[str, ...] = (),
        browser_state: dict[str, Any] | None = None,
    ) -> PerceptionSnapshot:
        """Publish one live observation and atomically advance its version."""
        started = time.perf_counter_ns()
        with self._lock:
            now = time.perf_counter_ns()
            self._version += 1
            self._snapshot = PerceptionSnapshot(
                version=self._version,
                screen_hash=self._screen_hash(screenshot_base64),
                width=max(0, int(width)),
                height=max(0, int(height)),
                active_window=str(active_window or ""),
                windows=tuple(str(item) for item in windows),
                processes=tuple(str(item) for item in processes),
                visible_text=str(visible_text or ""),
                controls=tuple(str(item) for item in controls),
                browser_state=dict(browser_state or {}),
                observed_at_ns=now,
            )
            self._targets.clear()
            self._last_publish_latency_ns = max(0, time.perf_counter_ns() - started)
            return self._snapshot

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
                observed_at_ns=time.perf_counter_ns(),
            )
            return self._version

    @property
    def last_update_latency_ns(self) -> int:
        """Time spent publishing the latest snapshot, useful for telemetry."""
        with self._lock:
            return self._last_publish_latency_ns
