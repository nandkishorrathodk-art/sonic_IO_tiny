"""
SONIC v2 — Typed Event Bus
===========================
The asynchronous communication backbone connecting Central Research Brain,
Specialists, Safety Kernel, and Observation feeds.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Callable, Coroutine


class EventTopic(StrEnum):
    OBSERVATION = "observation"
    EXPERIMENT_REQUEST = "experiment_request"
    EXPERIMENT_RESULT = "experiment_result"
    HYPOTHESIS_UPDATED = "hypothesis_updated"
    FINDING_CANDIDATE = "finding_candidate"
    FINDING_VERIFIED = "finding_verified"
    DEAD_END_DETECTED = "dead_end_detected"
    SAFETY_AUDIT = "safety_audit"
    MISSION_STATE = "mission_state"


@dataclass(frozen=True)
class Event:
    """Immutable event published across the system."""
    topic: EventTopic
    sender: str
    payload: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


EventHandler = Callable[[Event], Any]


class EventBus:
    """Thread-safe, synchronous and asynchronous pub/sub event bus."""

    def __init__(self):
        self._subscribers: dict[EventTopic, list[EventHandler]] = defaultdict(list)
        self._event_log: list[Event] = []

    def subscribe(self, topic: EventTopic, handler: EventHandler) -> None:
        if handler not in self._subscribers[topic]:
            self._subscribers[topic].append(handler)

    def unsubscribe(self, topic: EventTopic, handler: EventHandler) -> None:
        if handler in self._subscribers[topic]:
            self._subscribers[topic].remove(handler)

    def publish(self, topic: EventTopic, sender: str, payload: dict[str, Any]) -> Event:
        """Publishes an event synchronously to all registered handlers."""
        event = Event(topic=topic, sender=sender, payload=payload)
        self._event_log.append(event)
        for handler in list(self._subscribers[topic]):
            try:
                res = handler(event)
                # If handler returns a coroutine in an active loop, schedule it
                if asyncio.iscoroutine(res):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(res)
                    except RuntimeError:
                        pass
            except Exception as e:
                # Handlers must not break publishing flow
                pass
        return event

    def get_events(self, topic: EventTopic | None = None) -> list[Event]:
        if topic:
            return [e for e in self._event_log if e.topic == topic]
        return list(self._event_log)

    def clear(self) -> None:
        self._subscribers.clear()
        self._event_log.clear()
