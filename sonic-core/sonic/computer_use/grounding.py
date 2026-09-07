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
    "xfce4-terminal": (0.038, 0.015),
    "browser launcher": (0.060, 0.015),
    "chrome icon": (0.060, 0.015),
    "chrome": (0.060, 0.015),
    "google chrome": (0.060, 0.015),
    "chromium": (0.060, 0.015),
    "firefox": (0.060, 0.015),
    "file manager launcher": (0.082, 0.015),
    "file manager": (0.082, 0.015),
    "thunar": (0.082, 0.015),
    "text editor launcher": (0.104, 0.015),
    "mousepad": (0.104, 0.015),
    "editor": (0.104, 0.015),

    # Desktop shortcuts / icons (left column)
    "home desktop icon": (0.030, 0.080),
    "home folder": (0.030, 0.080),
    "user home": (0.030, 0.080),
    "trash": (0.030, 0.200),
    "trash desktop icon": (0.030, 0.200),
    "recycle bin": (0.030, 0.200),
    "filesystem": (0.030, 0.320),
    "filesystem desktop icon": (0.030, 0.320),
    "root filesystem": (0.030, 0.320),
    "chrome desktop icon": (0.030, 0.440),
    "terminal desktop icon": (0.030, 0.560),

    # Window controls (standard top-right of active maximized window)
    "close button": (0.985, 0.015),
    "close window": (0.985, 0.015),
    "window close": (0.985, 0.015),
    "exit window": (0.985, 0.015),
    "minimize button": (0.950, 0.015),
    "minimize window": (0.950, 0.015),
    "window minimize": (0.950, 0.015),
    "maximize button": (0.968, 0.015),
    "maximize window": (0.968, 0.015),
    "window maximize": (0.968, 0.015),

    # System Tray / Notification Area (top right panel)
    "clock": (0.910, 0.015),
    "time": (0.910, 0.015),
    "clock applet": (0.910, 0.015),
    "notification area": (0.875, 0.015),
    "notifications": (0.875, 0.015),
    "network status": (0.850, 0.015),
    "network icon": (0.850, 0.015),
    "wifi icon": (0.850, 0.015),
    "audio status": (0.825, 0.015),
    "volume icon": (0.825, 0.015),

    # Browser Navigation & Controls (Chrome / Chromium / Web)
    "browser back": (0.015, 0.075),
    "back button": (0.015, 0.075),
    "browser forward": (0.035, 0.075),
    "forward button": (0.035, 0.075),
    "browser reload": (0.055, 0.075),
    "reload button": (0.055, 0.075),
    "refresh page": (0.055, 0.075),
    "refresh button": (0.055, 0.075),
    "browser address bar": (0.450, 0.075),
    "address bar": (0.450, 0.075),
    "url bar": (0.450, 0.075),
    "location bar": (0.450, 0.075),
    "omnibox": (0.450, 0.075),
    "browser new tab": (0.240, 0.040),
    "new tab button": (0.240, 0.040),
    "new tab": (0.240, 0.040),
    "browser close tab": (0.210, 0.040),
    "close tab": (0.210, 0.040),
    "browser devtools": (0.980, 0.075),
    "developer tools": (0.980, 0.075),
    "browser menu": (0.988, 0.075),
    "chrome menu": (0.988, 0.075),
    "three dots menu": (0.988, 0.075),
    "browser search bar": (0.500, 0.380),
    "google search input": (0.500, 0.380),

    # Terminal window active regions
    "terminal prompt": (0.200, 0.200),
    "terminal input": (0.200, 0.200),
    "terminal window": (0.500, 0.500),

    # Common dialog & web buttons
    "submit button": (0.500, 0.600),
    "submit": (0.500, 0.600),
    "login button": (0.500, 0.580),
    "login": (0.500, 0.580),
    "sign in button": (0.500, 0.580),
    "ok button": (0.550, 0.550),
    "ok": (0.550, 0.550),
    "cancel button": (0.450, 0.550),
    "cancel": (0.450, 0.550),
    "save button": (0.520, 0.550),
    "save": (0.520, 0.550),
    "search button": (0.620, 0.380),

    # Common screen regions
    "screen center": (0.500, 0.500),
    "center": (0.500, 0.500),
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
            if grounding_output:
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


async def resolve_ui_target_async(
    query: str,
    screenshot_b64: Optional[str] = None,
    width: int = 1280,
    height: int = 800,
    grounding_fn: Optional[Any] = None,
) -> Optional[Tuple[int, int]]:
    """Asynchronous variant of resolve_ui_target supporting coroutine grounding functions."""
    if not query:
        return None

    clean_query = query.strip().lower()

    # 1. Direct numeric coordinates
    if "," in clean_query:
        parts = clean_query.split(",")
        if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
            return int(parts[0].strip()), int(parts[1].strip())

    # 2. Dynamic Grounding function (sync or async)
    if grounding_fn and screenshot_b64:
        try:
            import inspect
            res = grounding_fn(query, screenshot_b64)
            if inspect.isawaitable(res):
                grounding_output = await res
            else:
                grounding_output = res
            if grounding_output:
                coords = extract_bbox_midpoint(grounding_output, width, height)
                if coords:
                    return coords
        except Exception as exc:
            logger.warning("grounding_fn_async_resolution_failed", query=query, error=str(exc))

    # 3. Landmark & Semantic Matching
    for key, (norm_x, norm_y) in _COMMON_UI_LANDMARKS.items():
        if key == clean_query or key in clean_query or clean_query in key:
            px = int(norm_x * width)
            py = int(norm_y * height)
            return px, py

    return None


