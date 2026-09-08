"""
SONIC A-SEA — Computer-Use Visual Grounding Engine
===================================================
Adapted and enhanced from open-computer-use (OS-Atlas & ShowUI).
Translates natural language UI queries ("click the chrome address bar",
"submit button", "terminal window") into precise pixel coordinates (x, y)
on the active desktop screen, avoiding coordinate guessing or hallucination.
"""

from __future__ import annotations

import asyncio
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


def extract_bbox_midpoint(bbox_response: Any, width: int = 1280, height: int = 800) -> Optional[Tuple[int, int]]:
    """Extract (x, y) pixel midpoint from multimodal model grounding output.
    
    Supports:
    - Direct (x, y) tuple or list of numbers
    - Box tags: <|box_start|>(x1, y1, x2, y2)<|box_end|>
    - Normalized coordinates [0, 1000] (standard UI grounding format)
    - Normalized floats [0.0, 1.0]
    - Direct pixel pairs [x, y]
    """
    if not bbox_response:
        return None

    if isinstance(bbox_response, (tuple, list)):
        try:
            if len(bbox_response) >= 4:
                x1, y1, x2, y2 = float(bbox_response[0]), float(bbox_response[1]), float(bbox_response[2]), float(bbox_response[3])
                if max(x1, y1, x2, y2) <= 1.0:
                    mid_x = int(((x1 + x2) / 2.0) * width)
                    mid_y = int(((y1 + y2) / 2.0) * height)
                elif max(x1, y1, x2, y2) > width or max(x1, y1, x2, y2) > height:
                    mid_x = int(((x1 + x2) / 2.0 / 1000.0) * width)
                    mid_y = int(((y1 + y2) / 2.0 / 1000.0) * height)
                else:
                    mid_x = int((x1 + x2) / 2.0)
                    mid_y = int((y1 + y2) / 2.0)
                return min(max(0, mid_x), width), min(max(0, mid_y), height)
            elif len(bbox_response) >= 2:
                x, y = float(bbox_response[0]), float(bbox_response[1])
                if max(x, y) <= 1.0:
                    px = int(x * width)
                    py = int(y * height)
                elif x > width or y > height:
                    px = int((x / 1000.0) * width)
                    py = int((y / 1000.0) * height)
                else:
                    px, py = int(x), int(y)
                return min(max(0, px), width), min(max(0, py), height)
        except (ValueError, TypeError):
            pass

    if not isinstance(bbox_response, str):
        bbox_response = str(bbox_response)

    match = re.search(r"<\|box_start\|>(.*?)<\|box_end\|>", bbox_response, re.DOTALL)
    inner_text = match.group(1) if match else bbox_response

    numbers = [float(num) for num in re.findall(r"\d+\.?\d*", inner_text)]
    if not numbers:
        return None

    if len(numbers) >= 4:
        x1, y1, x2, y2 = numbers[0], numbers[1], numbers[2], numbers[3]
        if max(x1, y1, x2, y2) <= 1.0:
            mid_x = int(((x1 + x2) / 2.0) * width)
            mid_y = int(((y1 + y2) / 2.0) * height)
        elif match is not None and max(x1, y1, x2, y2) <= 1000:
            # Model grounding bounding box tags always use [0, 1000] scale
            mid_x = int(((x1 + x2) / 2.0 / 1000.0) * width)
            mid_y = int(((y1 + y2) / 2.0 / 1000.0) * height)
        elif max(x1, y1, x2, y2) > width or max(x1, y1, x2, y2) > height:
            mid_x = int(((x1 + x2) / 2.0 / 1000.0) * width)
            mid_y = int(((y1 + y2) / 2.0 / 1000.0) * height)
        else:
            mid_x = int((x1 + x2) / 2.0)
            mid_y = int((y1 + y2) / 2.0)
        return min(max(0, mid_x), width), min(max(0, mid_y), height)

    elif len(numbers) >= 2:
        x, y = numbers[0], numbers[1]
        if max(x, y) <= 1.0:
            px = int(x * width)
            py = int(y * height)
        elif match is not None and max(x, y) <= 1000:
            px = int((x / 1000.0) * width)
            py = int((y / 1000.0) * height)
        elif x > width or y > height:
            px = int((x / 1000.0) * width)
            py = int((y / 1000.0) * height)
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
    "search button": (0.620, 0.380),

    # Burp Suite Window & Toolbars (Phase 8 Cyber Workstation)
    "burp suite": (0.250, 0.040),
    "burpsuite": (0.250, 0.040),
    "burp dashboard tab": (0.045, 0.040),
    "burp target tab": (0.110, 0.040),
    "burp proxy tab": (0.165, 0.040),
    "proxy tab": (0.165, 0.040),
    "burp intruder tab": (0.220, 0.040),
    "burp repeater tab": (0.275, 0.040),
    "repeater tab": (0.275, 0.040),
    "burp sequencer tab": (0.330, 0.040),
    "burp decoder tab": (0.385, 0.040),
    "burp comparer tab": (0.435, 0.040),
    "burp extensions tab": (0.490, 0.040),
    "burp intercept tab": (0.050, 0.075),
    "intercept tab": (0.050, 0.075),
    "burp http history tab": (0.130, 0.075),
    "burp http history": (0.130, 0.075),
    "http history": (0.130, 0.075),
    "burp proxy options tab": (0.230, 0.075),
    "burp forward button": (0.045, 0.110),
    "burp forward": (0.045, 0.110),
    "forward button": (0.045, 0.110),
    "burp drop button": (0.095, 0.110),
    "burp drop": (0.095, 0.110),
    "drop button": (0.095, 0.110),
    "burp intercept toggle": (0.155, 0.110),
    "intercept is on": (0.155, 0.110),
    "intercept is off": (0.155, 0.110),
    "burp action button": (0.225, 0.110),

    # Web Applications, Marketplaces & Navigation (e.g. OpenSea, Web3, dApps)
    "web search bar": (0.350, 0.160),
    "search opensea": (0.350, 0.160),
    "opensea search": (0.350, 0.160),
    "opensea search bar": (0.350, 0.160),
    "search input": (0.350, 0.160),
    "opensea logo": (0.120, 0.160),
    "connect wallet": (0.880, 0.160),
    "wallet": (0.880, 0.160),
    "connect": (0.880, 0.160),
    "explore": (0.220, 0.160),
    "profile": (0.930, 0.160),
    "profile icon": (0.930, 0.160),
    "cart": (0.965, 0.160),
    "featured banner": (0.500, 0.450),
    "first item": (0.250, 0.450),
    "second item": (0.500, 0.450),
    "third item": (0.750, 0.450),
    "trending": (0.150, 0.280),
    "top items": (0.220, 0.280),
    "page content": (0.500, 0.500),
    "web content": (0.500, 0.500),
    "browser content": (0.500, 0.500),
    "close popup": (0.850, 0.200),
    "dismiss": (0.850, 0.200),
    "accept cookies": (0.500, 0.850),

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
                if isinstance(grounding_output, (tuple, list)) and len(grounding_output) >= 2:
                    return int(grounding_output[0]), int(grounding_output[1])
                coords = extract_bbox_midpoint(grounding_output, width, height)
                if coords:
                    return coords
        except Exception as exc:
            logger.warning("grounding_fn_resolution_failed", query=query, error=str(exc))

    # 3. Landmark & Semantic Matching (Exact first, then whole-word boundary)
    for key, (norm_x, norm_y) in _COMMON_UI_LANDMARKS.items():
        if key == clean_query:
            return int(norm_x * width), int(norm_y * height)

    for key, (norm_x, norm_y) in _COMMON_UI_LANDMARKS.items():
        if len(key) >= 4 and (
            re.search(r'\b' + re.escape(key) + r'\b', clean_query)
            or re.search(r'\b' + re.escape(clean_query) + r'\b', key)
        ):
            return int(norm_x * width), int(norm_y * height)

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
                if isinstance(grounding_output, (tuple, list)) and len(grounding_output) >= 2:
                    return int(grounding_output[0]), int(grounding_output[1])
                coords = extract_bbox_midpoint(grounding_output, width, height)
                if coords:
                    return coords
        except Exception as exc:
            logger.warning("grounding_fn_async_resolution_failed", query=query, error=str(exc))

    # 3. Landmark & Semantic Matching (Exact first, then whole-word boundary)
    for key, (norm_x, norm_y) in _COMMON_UI_LANDMARKS.items():
        if key == clean_query:
            return int(norm_x * width), int(norm_y * height)

    for key, (norm_x, norm_y) in _COMMON_UI_LANDMARKS.items():
        if len(key) >= 4 and (
            re.search(r'\b' + re.escape(key) + r'\b', clean_query)
            or re.search(r'\b' + re.escape(clean_query) + r'\b', key)
        ):
            return int(norm_x * width), int(norm_y * height)

    return None


async def query_multimodal_grounding(
    llm_router: Any,
    query: str,
    screenshot_b64: str,
    width: int = 1280,
    height: int = 800,
) -> Optional[Tuple[int, int]]:
    """Ground a visual UI query using the configured multimodal vision model (e.g. moonshotai/kimi-k3)."""
    if not llm_router or not screenshot_b64:
        return None
    from sonic.llm.schemas import ImageContent, LLMRequest, Message, MessageRole

    raw_b64 = screenshot_b64.split(",", 1)[-1] if "," in screenshot_b64 else screenshot_b64
    images = [ImageContent(base64=raw_b64, media_type="image/png")]
    prompt = (
        f"Analyze this desktop screenshot ({width}x{height} resolution). "
        f"Locate the UI element: '{query}'. "
        f"Return ONLY the exact pixel coordinates or bounding box in format: "
        f"<|box_start|>(x1, y1, x2, y2)<|box_end|> or [x, y]. Do not output extra text."
    )
    req = LLMRequest(
        messages=[
            Message(role=MessageRole.USER, content=prompt, images=images)
        ],
        task_type="vision",
        max_tokens=64,
        temperature=0.1,
    )
    try:
        res = await asyncio.wait_for(llm_router.complete(req), timeout=8.0)
        return extract_bbox_midpoint(res.content, width=width, height=height)
    except Exception as exc:
        logger.warning("multimodal_grounding_model_query_failed", query=query, error=str(exc))
        return None


def crop_toolbar_region(
    screenshot_b64: str,
    bbox: Optional[Tuple[int, int, int, int]] = None,
    width: int = 1280,
    height: int = 800,
) -> Tuple[str, Tuple[int, int]]:
    """
    Hierarchical micro-crop targeting of high-density UI toolbars (e.g. 14-18px Java Swing buttons in Burp Suite).

    Args:
        screenshot_b64: Base64-encoded PNG screenshot of the desktop.
        bbox: Optional (x1, y1, x2, y2) bounding box to crop. Defaults to the top toolbar band (0, 0, width, min(240, height)).
        width: Desktop screen width.
        height: Desktop screen height.

    Returns:
        Tuple of (cropped_screenshot_b64, (offset_x, offset_y)).
        If PIL is unavailable or decoding fails, returns (screenshot_b64, (0, 0)).
    """
    if not _HAS_PIL or not screenshot_b64:
        return screenshot_b64, (0, 0)

    crop_box = bbox or (0, 0, width, min(240, height))
    x1, y1, x2, y2 = crop_box

    try:
        raw_b64 = screenshot_b64.split(",", 1)[-1] if "," in screenshot_b64 else screenshot_b64
        raw_bytes = base64.b64decode(raw_b64)
        image = Image.open(io.BytesIO(raw_bytes))
        cropped = image.crop((x1, y1, x2, y2))

        buffer = io.BytesIO()
        cropped.convert("RGB").save(buffer, format="PNG")
        cropped_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return cropped_b64, (x1, y1)
    except Exception as exc:
        logger.warning("crop_toolbar_region_failed", error=str(exc))
        return screenshot_b64, (0, 0)


def map_crop_to_screen(
    local_coords: Tuple[int, int],
    offset: Tuple[int, int],
) -> Tuple[int, int]:
    """Translate coordinates detected inside a micro-crop back to absolute desktop screen coordinates."""
    return local_coords[0] + offset[0], local_coords[1] + offset[1]


