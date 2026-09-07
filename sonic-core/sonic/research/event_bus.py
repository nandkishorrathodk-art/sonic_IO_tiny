"""
SONIC — Asynchronous Pub/Sub Research Event Bus
=================================================
Core asynchronous event distribution substrate enabling multi-agent specialists
to communicate, publish discoveries, and trigger reactive workflows.
"""

from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from pydantic import BaseModel, Field

from sonic.logger import get_logger

logger = get_logger(__name__)


# =====================================================================
# 1. Typed Research Events
# =====================================================================

class ResearchEvent(BaseModel):
    """Base class for all typed events flowing through the Research Event Bus."""
    event_id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    timestamp: float = Field(default_factory=time.time)
    source: str = ""
    topic: str = "research.event"
    data: dict[str, Any] = Field(default_factory=dict)


class TargetDiscoveredEvent(ResearchEvent):
    """Emitted when a host, IP, domain, or network service target is discovered."""
    topic: str = "target.discovered"
    target: str
    target_type: str = "host"  # "host", "domain", "ip", "url", "network_service"
    port: int | None = None
    service: str | None = None
    banner: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EndpointDiscoveredEvent(ResearchEvent):
    """Emitted when an HTTP/API route or web endpoint is identified."""
    topic: str = "endpoint.discovered"
    url: str
    method: str = "GET"
    params: list[str] = Field(default_factory=list)
    headers: dict[str, str] = Field(default_factory=dict)
    auth_required: bool | None = None
    content_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnomalyDetectedEvent(ResearchEvent):
    """Emitted when anomalous behavior, misconfiguration, or leak is spotted."""
    topic: str = "anomaly.detected"
    description: str = ""
    anomaly_type: str = ""
    observation: str = ""
    severity: str = "medium"  # "info", "low", "medium", "high", "critical"
    component: str = ""
    target: str = ""
    evidence: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        # Harmonize description and observation
        if not self.description and self.observation:
            self.description = self.observation
        elif not self.observation and self.description:
            self.observation = self.description


class HypothesisProposedEvent(ResearchEvent):
    """Emitted when a specialist proposes a new vulnerability or attack hypothesis."""
    topic: str = "hypothesis.proposed"
    hypothesis_id: str
    statement: str
    vulnerability_class: str = ""
    confidence: float = 0.5
    falsification_criteria: str = ""
    target: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class HypothesisFalsifiedEvent(ResearchEvent):
    """Emitted when counter-evidence disproves an active hypothesis."""
    topic: str = "hypothesis.falsified"
    hypothesis_id: str
    reason: str = ""
    evidence: Any = None
    disproved_by: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class VulnerabilityVerifiedEvent(ResearchEvent):
    """Emitted when a vulnerability hypothesis survives rigorous adversarial validation."""
    topic: str = "vulnerability.verified"
    vulnerability_id: str = Field(default_factory=lambda: f"vuln-{uuid.uuid4().hex[:8]}")
    title: str = ""
    vulnerability_class: str = ""
    severity: str = "high"  # "low", "medium", "high", "critical"
    target: str = ""
    evidence: Any = None
    reproduction_steps: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchStateChangedEvent(ResearchEvent):
    """Emitted when a specialist agent transitions between lifecycle states."""
    topic: str = "research.state_changed"
    agent_name: str
    old_state: str
    new_state: str
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


E = TypeVar("E", bound=ResearchEvent)
EventHandler = Callable[[Any], Coroutine[Any, Any, None] | None]


# =====================================================================
# 2. Asynchronous Pub/Sub Event Bus
# =====================================================================

class ResearchEventBus:
    """
    Asynchronous Pub/Sub Event Bus for parallel multi-agent research coordination.

    Features:
      - Typed event subscriptions (by class or topic string pattern)
      - Wildcard topics ('*', 'target.*')
      - Async callback handlers and asyncio.Queue subscriptions
      - Resilient dispatch (handler failures logged without crashing other subscribers)
      - Comprehensive in-memory event history and filtering
    """

    def __init__(self, history_limit: int = 1000) -> None:
        self._history_limit = history_limit
        self._history: list[ResearchEvent] = []
        self._type_subscribers: dict[type[ResearchEvent], list[EventHandler]] = {}
        self._topic_subscribers: dict[str, list[EventHandler]] = {}
        self._queues: list[tuple[type[ResearchEvent] | str, asyncio.Queue[ResearchEvent]]] = []
        self._lock = asyncio.Lock()

    @property
    def event_count(self) -> int:
        return len(self._history)

    def subscribe(
        self,
        subscription: type[E] | str,
        handler: EventHandler,
    ) -> None:
        """
        Subscribe a callback handler to an event class or topic string.
        Handler can be an async coroutine or sync callable.
        """
        if isinstance(subscription, type) and issubclass(subscription, ResearchEvent):
            self._type_subscribers.setdefault(subscription, []).append(handler)
        elif isinstance(subscription, str):
            self._topic_subscribers.setdefault(subscription, []).append(handler)
        else:
            raise TypeError(
                f"Subscription must be a ResearchEvent subclass or topic str, got {type(subscription)}"
            )

    def subscribe_topic(self, topic: str, handler: EventHandler) -> None:
        """Convenience alias to subscribe explicitly to a topic string pattern."""
        self.subscribe(topic, handler)

    def unsubscribe(
        self,
        subscription: type[E] | str,
        handler: EventHandler,
    ) -> bool:
        """Unsubscribe a callback handler."""
        removed = False
        if isinstance(subscription, type) and issubclass(subscription, ResearchEvent):
            handlers = self._type_subscribers.get(subscription, [])
            if handler in handlers:
                handlers.remove(handler)
                removed = True
        elif isinstance(subscription, str):
            handlers = self._topic_subscribers.get(subscription, [])
            if handler in handlers:
                handlers.remove(handler)
                removed = True
        return removed

    def subscribe_queue(
        self,
        subscription: type[E] | str = "*",
        maxsize: int = 0,
    ) -> asyncio.Queue[ResearchEvent]:
        """Create an asyncio.Queue that receives all matching published events."""
        q: asyncio.Queue[ResearchEvent] = asyncio.Queue(maxsize=maxsize)
        self._queues.append((subscription, q))
        return q

    def unsubscribe_queue(self, queue: asyncio.Queue[ResearchEvent]) -> bool:
        """Remove a queue subscription."""
        for item in list(self._queues):
            if item[1] is queue:
                self._queues.remove(item)
                return True
        return False

    async def publish(self, event: ResearchEvent) -> int:
        """
        Publish an event to all matching subscribers and queues.
        Returns the number of handlers/queues the event was dispatched to.
        """
        async with self._lock:
            self._history.append(event)
            if len(self._history) > self._history_limit:
                self._history.pop(0)

        matched_handlers: list[EventHandler] = []

        # 1. Match type subscriptions
        for event_cls, handlers in self._type_subscribers.items():
            if isinstance(event, event_cls):
                matched_handlers.extend(handlers)

        # 2. Match topic subscriptions
        topic = event.topic
        for topic_pattern, handlers in self._topic_subscribers.items():
            if self._topic_matches(topic_pattern, topic):
                matched_handlers.extend(handlers)

        # De-duplicate handlers while preserving order
        unique_handlers: list[EventHandler] = []
        for h in matched_handlers:
            if h not in unique_handlers:
                unique_handlers.append(h)

        # 3. Match queue subscriptions
        matched_queues: list[asyncio.Queue[ResearchEvent]] = []
        for sub, q in self._queues:
            if isinstance(sub, type) and issubclass(sub, ResearchEvent):
                if isinstance(event, sub):
                    matched_queues.append(q)
            elif isinstance(sub, str) and self._topic_matches(sub, topic):
                matched_queues.append(q)

        # 4. Dispatch to handlers concurrently
        if unique_handlers:
            async def _invoke(handler: EventHandler) -> None:
                try:
                    res = handler(event)
                    if inspect.isawaitable(res):
                        await res
                except Exception as ex:
                    logger.warning(
                        "research_event_bus_handler_error",
                        handler=getattr(handler, "__name__", str(handler)),
                        event_type=event.__class__.__name__,
                        error=str(ex),
                    )

            await asyncio.gather(*[_invoke(h) for h in unique_handlers], return_exceptions=True)

        # 5. Dispatch to queues
        for q in matched_queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("research_event_bus_queue_full", event_type=event.__class__.__name__)

        return len(unique_handlers) + len(matched_queues)

    def get_history(
        self,
        event_type: type[ResearchEvent] | str | None = None,
        limit: int | None = None,
    ) -> list[ResearchEvent]:
        """Return recorded event history, optionally filtered by event type or topic."""
        events = self._history
        if event_type is not None:
            if isinstance(event_type, type) and issubclass(event_type, ResearchEvent):
                events = [e for e in events if isinstance(e, event_type)]
            elif isinstance(event_type, str):
                events = [e for e in events if self._topic_matches(event_type, e.topic)]

        if limit is not None and limit > 0:
            return events[-limit:]
        return list(events)

    def clear_history(self) -> None:
        """Clear the recorded event history."""
        self._history.clear()

    @staticmethod
    def _topic_matches(pattern: str, topic: str) -> bool:
        """Support wildcard pattern matching: '*', '#', and prefix globs like 'target.*'."""
        if pattern in ("*", "#"):
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return topic == prefix or topic.startswith(f"{prefix}.")
        return pattern == topic
