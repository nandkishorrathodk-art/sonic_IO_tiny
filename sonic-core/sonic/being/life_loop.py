"""
SONIC-REDA — Being Life Loop (the always-on autonomous tick)
============================================================

The "always-on" part of the AI human: a long-lived loop that runs when no
operator goal is active, letting the being pursue self-directed curiosity
through the REAL observe->reason->act loop between (and independent of) API
requests. Before this, the CuriosityLoop existed but was dead unless manually
poked — a being that only acts when poked is a tool, not a being.

The loop is owned by a Being (stable persistent identity). Each tick:
    1. proposes a curious goal (LLM, novelty-biased) from the live observation
    2. pursues it via the agent's real loop (every action passes the Phase-6
       ActionPolicy safety envelope — the being CANNOT escape it when idle)
    3. records the outcome in the BeingMind (mood evolves; facts persist)
    4. sleeps until the next tick

It is spawned as a long-lived `asyncio.Task` (see `start()`/`stop()`) — the
natural integration point is `api/main.py:lifespan()`, cancelled on shutdown.
It never raises out: a failed tick is logged and the loop continues, so a
single bad cycle cannot kill the being.

The being is NOT autonomous-without-guardrails: it requires an ActionPolicy
(Phase 6). Constructing a life loop without a safety policy is refused, mir
roring `ComputerUseAgent(self_host=True)`'s hard requirement.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict, defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sonic.being.identity import (
    Being,
    BeingMind,
    get_being_store,
    record_idle_cycle,
)
from sonic.logger import get_logger

logger = get_logger(__name__)

_active_life_loop: BeingLifeLoop | None = None


def register_life_loop(loop: BeingLifeLoop) -> None:
    """Expose the process-local idle actor to the foreground control plane."""
    global _active_life_loop
    _active_life_loop = loop


def pause_for_operator() -> None:
    """Prevent new idle cycles while an operator mission owns the workstation."""
    if _active_life_loop is not None:
        _active_life_loop.pause_for_operator()


def resume_after_operator() -> None:
    """Release the workstation back to idle autonomy after a mission ends."""
    if _active_life_loop is not None:
        _active_life_loop.resume_after_operator()


# ---------------------------------------------------------------------------
# NEXUS L1 -- EventBus (Continuous Infinity Loop event surface)
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class BusEvent:
    """A single cognition event published on the bus."""
    topic: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)
    event_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "payload": self.payload,
            "created_at": self.created_at,
            "event_id": self.event_id,
        }


Handler = Callable[[BusEvent], Awaitable[Any]] | Callable[[BusEvent], Any]


class EventBus:
    """An LRU-bounded, coalesced in-process event bus for always-on cognition.

    The being is woken by *any* event (subprocess result, webhook, trace
    completion, state transition) rather than only fixed ticks. `publish` is
    fire-and-forget and coalesced by topic so unbounded growth is impossible;
    `subscribe` registers the WAKE handlers of cognition.
    """

    def __init__(self, max_frontier: int = 512) -> None:
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)
        self._frontier: OrderedDict[str, BusEvent] = OrderedDict()
        self._max_frontier = max_frontier
        self._published = 0

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._subscribers[topic].append(handler)

    def publish(self, topic: str, payload: dict[str, Any] | None = None) -> BusEvent:
        event = BusEvent(topic=topic, payload=payload or {})
        # coalesce: same topic payloads overwrite rather than append unboundedly
        self._frontier.pop(topic, None)
        self._frontier[topic] = event
        while len(self._frontier) > self._max_frontier:
            self._frontier.popitem(last=False)
        self._published += 1
        for handler in self._subscribers.get(topic, []):
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    asyncio.ensure_future(result)
            except Exception as e:
                logger.warning("eventbus_handler_failed", topic=topic, error=str(e))
        return event

    def frontier(self) -> list[BusEvent]:
        return list(self._frontier.values())

    def frontier_topics(self) -> list[str]:
        return list(self._frontier.keys())

    def latest(self, topic: str) -> BusEvent | None:
        return self._frontier.get(topic)

    def reset(self) -> None:
        self._frontier.clear()
        self._subscribers.clear()

    def stats(self) -> dict[str, Any]:
        return {
            "published_total": self._published,
            "frontier_size": len(self._frontier),
            "subscribers": sum(len(h) for h in self._subscribers.values()),
        }


class BeingLifeLoop:
    """Always-on autonomous curiosity tick owned by a persistent Being.

    Args:
        being:          the stable persistent identity (from get_or_create_being).
        agent:          a ComputerUseAgent with a safety policy set — every
                        autonomous action the being takes flows through its
                        execute_action() and thus the ActionPolicy gate.
        curiosity:      the CuriosityLoop that proposes + measures self-directed
                        goals.
        workspace_id:   the being's home workspace (get_or_create_home) where
                        idle exploration happens.
        tick_interval:  seconds between idle cycles (default 60s). 0 = run as
                        fast as cycles complete (tests).
    """

    def __init__(
        self,
        being: Being,
        agent: Any,
        curiosity: Any,
        workspace_id: str,
        tick_interval: float = 60.0,
    ):
        if getattr(agent, "safety", None) is None:
            raise ValueError(
                "BeingLifeLoop requires a ComputerUseAgent with a safety policy — "
                "an always-on autonomous being must not act without the fail-closed "
                "ActionPolicy envelope."
            )
        self.being = being
        self.agent = agent
        self.curiosity = curiosity
        self.workspace_id = workspace_id
        self.tick_interval = tick_interval
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._operator_active = asyncio.Event()
        self.cycles_completed = 0
        self.before_tick_hooks: list = []
        self.bus: EventBus = EventBus()

    def pause_for_operator(self) -> None:
        self._operator_active.set()
        logger.info("being_life_loop_paused_for_operator", being_id=self.being.being_id)

    def resume_after_operator(self) -> None:
        self._operator_active.clear()
        logger.info("being_life_loop_resumed_after_operator", being_id=self.being.being_id)

    # ------------------------------------------------------------------
    def mind(self) -> BeingMind:
        return get_being_store().get_mind(self.being.being_id)

    async def tick(self) -> Any:
        """Run ONE self-directed curiosity cycle as the being.

        Returns the CuriosityCycleResult. The pursuit goes through the agent's
        real loop, so every action is gated by the ActionPolicy. The outcome is
        recorded in the BeingMind (mood evolves, facts persist across restart).
        """
        for hook in self.before_tick_hooks:
            try:
                hook()
            except Exception as e:
                logger.warning("being_tick_hook_failed", error=str(e))
        try:
            res = await self.agent.idle_cycle(self.workspace_id, self.curiosity)
            learned = getattr(res, "learned_fact", None)
            record_idle_cycle(self.being.being_id, learned)
            self.cycles_completed += 1
            logger.info(
                "being_idle_cycle",
                being_id=self.being.being_id,
                cycle=self.cycles_completed,
                goal=getattr(res, "proposed_goal", "")[:80],
                novel=getattr(res, "was_novel", False),
                info_gain=getattr(res, "info_gain", 0.0),
            )
            # Publish the cycle outcome onto the continuous-event bus so any
            # subscribed cognition layer can react without a fixed tick.
            self.bus.publish("being.idle_cycle", {
                "being_id": self.being.being_id,
                "cycle": self.cycles_completed,
                "goal": getattr(res, "proposed_goal", ""),
                "was_novel": getattr(res, "was_novel", False),
                "info_gain": getattr(res, "info_gain", 0.0),
                "learned_fact": str(learned),
            })
            return res
        except Exception as e:
            # A single failed tick must never kill the being.
            logger.warning("being_idle_cycle_failed",
                           being_id=self.being.being_id, error=str(e))
            record_idle_cycle(self.being.being_id, None)  # count as dead-end
            return None

    async def _run(self) -> None:
        """The long-lived loop: tick, yield, repeat — until stop().

        Always yields to the event loop between ticks (even at interval=0) so
        that stop() can set the cancellation event; a tight loop with no await
        would starve the loop and never observe the stop signal.
        """
        while not self._stop.is_set():
            if self._operator_active.is_set():
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=0.25)
                except TimeoutError:
                    pass
                continue
            await self.tick()
            interval = self.tick_interval if self.tick_interval > 0 else 0.01
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except TimeoutError:
                pass  # interval elapsed, tick again

    # ------------------------------------------------------------------
    def start(self) -> asyncio.Task:
        """Spawn the always-on loop as a long-lived background task."""
        if self._task is not None and not self._task.done():
            return self._task
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name=f"being-life-{self.being.being_id}")
        logger.info("being_life_loop_started", being_id=self.being.being_id,
                    tick_interval=self.tick_interval)
        return self._task

    async def stop(self, timeout: float = 5.0) -> None:
        """Signal the loop to stop and await cancellation (shutdown hook)."""
        self._stop.set()
        if self._task is not None and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=timeout)
            except TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
        logger.info("being_life_loop_stopped", being_id=self.being.being_id,
                    cycles=self.cycles_completed)
