"""
Tests for visual grounding engine (adapted from open-computer-use).
"""

from sonic.computer_use.grounding import extract_bbox_midpoint, draw_action_marker


def test_extract_bbox_midpoint_box_tags():
    # Tagged normalized 0-1000 format
    resp = "<|box_start|>(100, 200, 300, 400)<|box_end|>"
    pt = extract_bbox_midpoint(resp, width=1280, height=800)
    assert pt is not None
    # midpoint of 100 and 300 is 200 (200 / 1000 * 1280 = 256)
    # midpoint of 200 and 400 is 300 (300 / 1000 * 800 = 240)
    assert pt == (256, 240)


def test_extract_bbox_midpoint_float_range():
    # 0.0 - 1.0 range
    resp = "0.5, 0.5"
    pt = extract_bbox_midpoint(resp, width=1280, height=800)
    assert pt == (640, 400)


def test_draw_action_marker_fallback():
    dummy_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    res = draw_action_marker(dummy_b64, (50, 50))
    assert res is not None
    assert len(res) > 0
