from sonic.computer_use.perception_bus import PerceptionBus


def test_perception_bus_versions_and_rejects_stale_futures():
    bus = PerceptionBus()
    first = bus.publish(
        screenshot_base64="frame-a",
        width=1280,
        height=800,
        active_window="Browser",
        windows=["Browser", "Terminal"],
        processes=["browser"],
        controls=["submit"],
    )
    target = bus.register_target(
        "submit", (10, 20, 100, 40), source="accessibility", confidence=1.0
    )
    future = bus.prepare("click", "submit")

    assert first.version == 1
    assert target.state_version == 1
    assert bus.resolve("submit") == target
    assert bus.is_current(future)
    assert bus.current().windows == ("Browser", "Terminal")
    assert bus.current().processes == ("browser",)

    bus.publish(screenshot_base64="frame-b")
    assert bus.current().version == 2
    assert bus.resolve("submit") is None
    assert not bus.is_current(future)


def test_perception_bus_clamps_confidence_and_hashes_frames():
    bus = PerceptionBus()
    snapshot = bus.publish(screenshot_base64="same-frame")
    match = bus.register_target(
        "target", (0, 0, 1, 1), source="dom", confidence=4.0
    )

    assert len(snapshot.screen_hash) == 32
    assert match.confidence == 1.0
    assert bus.last_update_latency_ns >= 0


def test_perception_bus_invalidates_targets_after_external_action():
    bus = PerceptionBus()
    bus.publish(screenshot_base64="frame")
    bus.register_target("menu", (1, 2, 3, 4), source="atspi", confidence=1.0)
    future = bus.prepare("click", "menu")

    version = bus.invalidate()

    assert version == 2
    assert bus.resolve("menu") is None
    assert not bus.is_current(future)


def test_perception_bus_deduplicates_unchanged_frames():
    bus = PerceptionBus()
    first = bus.publish(
        screenshot_base64="frame",
        width=1280,
        height=800,
        active_window="Editor",
        visible_text="Ready",
    )
    changes = []
    bus.subscribe(changes.append)

    same = bus.publish(
        screenshot_base64="frame",
        width=1280,
        height=800,
        active_window="Editor",
        visible_text="Ready",
    )

    assert same.version == first.version
    assert changes == []
    assert bus.last_changed_fields == ()
    assert bus.visual_changed is False


def test_perception_bus_emits_incremental_change_and_unsubscribes():
    bus = PerceptionBus()
    bus.publish(active_window="Editor", processes=["editor"])
    changes = []
    unsubscribe = bus.subscribe(changes.append)

    snapshot = bus.apply_patch(active_window="Terminal")

    assert snapshot.version == 2
    assert len(changes) == 1
    assert changes[0].previous_version == 1
    assert changes[0].changed_fields == ("active_window",)
    assert bus.last_changed_fields == ("active_window",)
    unsubscribe()
    bus.apply_patch(active_window="Browser")
    assert len(changes) == 1


def test_perception_bus_rejects_unknown_patch_fields():
    bus = PerceptionBus()

    try:
        bus.apply_patch(unknown_state="invalid")
    except ValueError as exc:
        assert "unknown_state" in str(exc)
    else:
        raise AssertionError("unknown perception fields must be rejected")


def test_perception_bus_tracks_structured_sources_and_provider_residuals():
    bus = PerceptionBus()
    snapshot = bus.publish(
        structured_sources=("browser_dom",),
        visual_residuals=[(10, 20, 100, 80), (-1, 2, 3, 4), (5, 5, 5, 9)],
    )

    assert snapshot.structured_sources == ("browser_dom",)
    assert snapshot.visual_residuals == ((10, 20, 100, 80),)
    assert bus.structured_state_available is True
    assert bus.visual_residuals == ((10, 20, 100, 80),)
