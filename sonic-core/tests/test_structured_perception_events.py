import asyncio

import pytest

from sonic.computer_use.perception_adapters import StructuredPerceptionEventAdapter
from sonic.computer_use.perception_bus import PerceptionBus


class _Events:
    def __init__(self, events):
        self._events = events

    async def _iterate(self):
        for event in self._events:
            yield event

    def events(self):
        return self._iterate()


@pytest.mark.asyncio
async def test_structured_events_update_bus_without_screenshot():
    bus = PerceptionBus()
    source = _Events([
        {"active_window": "Editor", "processes": ("editor",)},
        {"filesystem_state": ("file.txt|file.txt|0|4|1",)},
    ])

    await StructuredPerceptionEventAdapter(source, bus).run()

    snapshot = bus.current()
    assert snapshot.active_window == "Editor"
    assert snapshot.processes == ("editor",)
    assert snapshot.filesystem_state == ("file.txt|file.txt|0|4|1",)
    assert snapshot.screen_hash == ""


@pytest.mark.asyncio
async def test_invalid_event_is_reported_and_does_not_break_following_events():
    bus = PerceptionBus()
    source = _Events([
        {"unsupported": True},
        {"visible_text": "real event"},
    ])
    errors = []

    await StructuredPerceptionEventAdapter(source, bus).run(
        on_error=errors.append,
    )

    assert len(errors) == 1
    assert "Unsupported perception event fields" in str(errors[0])
    assert bus.current().visible_text == "real event"


@pytest.mark.asyncio
async def test_event_adapter_stop_halts_remaining_source_events():
    bus = PerceptionBus()
    adapter = None

    class _StoppingEvents:
        async def _iterate(self):
            yield {"active_window": "first"}
            adapter.stop()
            yield {"active_window": "must-not-apply"}

        def events(self):
            return self._iterate()

    adapter = StructuredPerceptionEventAdapter(_StoppingEvents(), bus)
    await adapter.run()

    assert bus.current().active_window == "first"
