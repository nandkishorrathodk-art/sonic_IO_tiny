import pytest

from sonic.computer_use.perception_adapters import (
    DockerContainerEventSource,
    StructuredPerceptionEventAdapter,
)
from sonic.computer_use.perception_bus import PerceptionBus


class _DockerEvents:
    async def _iterate(self):
        yield {"runtime_state": "RUNNING"}
        yield {"runtime_state": "STOPPED"}

    def events(self):
        return self._iterate()


@pytest.mark.asyncio
async def test_docker_lifecycle_events_update_runtime_state_only():
    bus = PerceptionBus()
    await StructuredPerceptionEventAdapter(_DockerEvents(), bus).run()

    assert bus.current().runtime_state == "STOPPED"
    assert bus.current().filesystem_state == ()
    assert bus.current().processes == ()


def test_docker_event_source_requires_container_id():
    with pytest.raises(ValueError, match="container_id"):
        DockerContainerEventSource("")


@pytest.mark.asyncio
async def test_docker_event_source_maps_only_lifecycle_events(monkeypatch):
    class _Stdout:
        def __aiter__(self):
            async def lines():
                for line in (
                    b'{"status":"start"}\n',
                    b'{"status":"exec_start"}\n',
                    b'{"status":"die"}\n',
                ):
                    yield line

            return lines()

    class _Process:
        stdout = _Stdout()
        returncode = 0

        def terminate(self):
            self.terminated = True

        async def wait(self):
            return 0

    async def create_process(*args, **kwargs):
        return _Process()

    monkeypatch.setattr(
        "sonic.computer_use.perception_adapters.asyncio.create_subprocess_exec",
        create_process,
    )
    events = []
    async for event in DockerContainerEventSource("container-id").events():
        events.append(event)

    assert events == [{"runtime_state": "RUNNING"}, {"runtime_state": "STOPPED"}]
