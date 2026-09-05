"""
SONIC A-SEA — Computer-Use Visual Grounding Engine
===================================================
Adapted and enhanced from open-computer-use (OS-Atlas & ShowUI).
Translates natural language UI queries ("click the chrome address bar",
"submit button", "terminal window") into precise pixel coordinates (x, y)
on the active desktop screen, avoiding coordinate guessing or hallucination.
"""

from __future__ import annotations

import base64
import io
import re
from typing import Tuple, Optional

try:
    from PIL import Image, ImageDraw
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

from sonic.logger import get_logger

logger = get_logger(__name__)


def extract_bbox_midpoint(bbox_response: str, width: int = 1280, height: int = 800) -> Optional[Tuple[int, int]]:
    """Extract (x, y) pixel midpoint from multimodal model grounding output.
    
    Supports:
    - Box tags: <|box_start|>(x1, y1, x2, y2)<|box_end|>
    - Normalized coordinates [0, 1000] (standard UI grounding format)
    - Normalized floats [0.0, 1.0]
    - Direct pixel pairs [x, y]
    """
    if not bbox_response:
        return None

    match = re.search(r"<\|box_start\|>(.*?)<\|box_end\|>", bbox_response, re.DOTALL)
    inner_text = match.group(1) if match else bbox_response

    numbers = [float(num) for num in re.findall(r"\d+\.?\d*", inner_text)]
    if not numbers:
        return None

    if len(numbers) >= 4:
        x1, y1, x2, y2 = numbers[0], numbers[1], numbers[2], numbers[3]
        # If coordinates are normalized in 0-1000 range
        if max(x1, y1, x2, y2) <= 1000 and max(x1, y1, x2, y2) > 1:
            mid_x = int(((x1 + x2) / 2.0 / 1000.0) * width)
            mid_y = int(((y1 + y2) / 2.0 / 1000.0) * height)
        # If coordinates are normalized in 0.0-1.0 range
        elif max(x1, y1, x2, y2) <= 1.0:
            mid_x = int(((x1 + x2) / 2.0) * width)
            mid_y = int(((y1 + y2) / 2.0) * height)
        else:
            mid_x = int((x1 + x2) / 2.0)
            mid_y = int((y1 + y2) / 2.0)
        return min(max(0, mid_x), width), min(max(0, mid_y), height)

    elif len(numbers) >= 2:
        x, y = numbers[0], numbers[1]
        if max(x, y) <= 1000 and max(x, y) > 1:
            px = int((x / 1000.0) * width)
            py = int((y / 1000.0) * height)
        elif max(x, y) <= 1.0:
            px = int(x * width)
            py = int(y * height)
        else:
            px = int(x)
            py = int(y)
        return min(max(0, px), width), min(max(0, py), height)

    return None


def draw_action_marker(
    image_b64: str,
    coordinates: Tuple[int, int],
    label: str = "CLICK",
    color: str = "#00ffcc",
    radius: int = 14,
) -> str:
    """Draw a visual target indicator and action label on a base64 screenshot."""
    if not _HAS_PIL or not image_b64:
        return image_b64
    try:
        raw_bytes = base64.b64decode(image_b64.split(",")[-1])
        image = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
        draw = ImageDraw.Draw(image)

        x, y = coordinates
        bbox = [x - radius, y - radius, x + radius, y + radius]

        # Use distinct styling for right-click / double-click
        ring_color = color
        if "RIGHT" in label.upper():
            ring_color = "#ff3366"
        elif "DOUBLE" in label.upper():
            ring_color = "#ffaa00"

        # Draw outer pulse ring + filled aim point
        draw.ellipse([x - radius - 4, y - radius - 4, x + radius + 4, y + radius + 4], outline=ring_color, width=2)
        draw.ellipse(bbox, fill=(0, 255, 204, 180), outline="black", width=2)

        # Draw crosshairs
        draw.line([(x - radius - 8, y), (x + radius + 8, y)], fill=ring_color, width=2)
        draw.line([(x, y - radius - 8), (x, y + radius + 8)], fill=ring_color, width=2)

        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception as e:
        logger.warning("draw_action_marker_failed", error=str(e))
        return image_b64


# Standard landmark positions for a standard desktop workstation (scaled to width, height)
_COMMON_UI_LANDMARKS: dict[str, tuple[float, float]] = {
    # Top panel / Application menu
    "applications menu": (0.016, 0.015),
    "applications": (0.016, 0.015),
    "app menu": (0.016, 0.015),
    "whisker menu": (0.016, 0.015),
    "start menu": (0.016, 0.015),
    # Quick launcher icons on top panel
    "terminal launcher": (0.038, 0.015),
    "terminal icon": (0.038, 0.015),
    "terminal": (0.038, 0.015),
    "browser launcher": (0.060, 0.015),
    "chrome icon": (0.060, 0.015),
    "chrome": (0.060, 0.015),
    "google chrome": (0.060, 0.015),
    "file manager launcher": (0.082, 0.015),
    "file manager": (0.082, 0.015),
    "thunar": (0.082, 0.015),
    # Desktop shortcuts / icons (left column)
    "home desktop icon": (0.030, 0.080),
    "trash": (0.030, 0.200),
    "filesystem": (0.030, 0.320),
    # Window controls (standard top-right of active maximized window)
    "close button": (0.985, 0.015),
    "close window": (0.985, 0.015),
    "window close": (0.985, 0.015),
    "minimize button": (0.950, 0.015),
    "minimize window": (0.950, 0.015),
    "maximize button": (0.968, 0.015),
    "maximize window": (0.968, 0.015),
    # Common screen regions
    "screen center": (0.500, 0.500),
    "center": (0.500, 0.500),
    "address bar": (0.500, 0.100),
    "search bar": (0.500, 0.500),
    "search box": (0.500, 0.500),
}


def resolve_ui_target(
    query: str,
    screenshot_b64: Optional[str] = None,
    width: int = 1280,
    height: int = 800,
    grounding_fn: Optional[Any] = None,
) -> Optional[Tuple[int, int]]:
    """Resolves a natural language UI target query to absolute screen coordinates (x, y).

    Resolution pipeline:
    1. Direct numeric coordinate check (if query is already "640,400").
    2. Dynamic Multimodal Grounding Function (vision LLM / ShowUI / OS-Atlas) if provided.
    3. Heuristic / Semantic Landmark Dictionary for standard workstation desktop elements.
    """
    if not query:
        return None

    clean_query = query.strip().lower()

    # 1. Direct numeric coordinates
    if "," in clean_query:
        parts = clean_query.split(",")
        if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
            return int(parts[0].strip()), int(parts[1].strip())

    # 2. Dynamic Grounding function (multimodal vision model callback)
    if grounding_fn and screenshot_b64:
        try:
            grounding_output = grounding_fn(query, screenshot_b64)
            coords = extract_bbox_midpoint(grounding_output, width, height)
            if coords:
                return coords
        except Exception as exc:
            logger.warning("grounding_fn_resolution_failed", query=query, error=str(exc))

    # 3. Landmark & Semantic Matching
    for key, (norm_x, norm_y) in _COMMON_UI_LANDMARKS.items():
        if key == clean_query or key in clean_query or clean_query in key:
            px = int(norm_x * width)
            py = int(norm_y * height)
            return px, py

    return None

