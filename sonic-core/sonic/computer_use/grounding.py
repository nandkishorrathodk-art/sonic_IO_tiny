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
from typing import Any, Optional, Tuple

try:
    from PIL import Image, ImageDraw
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

from sonic.logger import get_logger

logger = get_logger(__name__)

# UI targets must be resolved from the current DOM/accessibility tree or screenshot pixels.


def extract_bbox_midpoint(
    bbox_response: Any,
    width: int = 1280,
    height: int = 800,
    is_normalized_1000: Optional[bool] = None,
) -> Optional[Tuple[int, int]]:
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
                elif is_normalized_1000 or (is_normalized_1000 is not False and max(x1, y1, x2, y2) <= 1000):
                    mid_x = int(((x1 + x2) / 2.0 / 1000.0) * width)
                    mid_y = int(((y1 + y2) / 2.0 / 1000.0) * height)
                else:
                    mid_x = int((x1 + x2) / 2.0)
                    mid_y = int((y1 + y2) / 2.0)
                mid_pt = (min(max(0, mid_x), width), min(max(0, mid_y), height))
                return None if mid_pt == (0, 0) else mid_pt
            elif len(bbox_response) >= 2:
                x, y = float(bbox_response[0]), float(bbox_response[1])
                if max(x, y) <= 1.0:
                    px = int(x * width)
                    py = int(y * height)
                elif is_normalized_1000 or (is_normalized_1000 is None and (x > width or y > height)):
                    px = int((x / 1000.0) * width)
                    py = int((y / 1000.0) * height)
                else:
                    px, py = int(x), int(y)
                pt = (min(max(0, px), width), min(max(0, py), height))
                return None if pt == (0, 0) else pt
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
        elif is_normalized_1000 or (is_normalized_1000 is not False and max(x1, y1, x2, y2) <= 1000):
            # Model grounding bounding box tags or normalized scale use [0, 1000]
            mid_x = int(((x1 + x2) / 2.0 / 1000.0) * width)
            mid_y = int(((y1 + y2) / 2.0 / 1000.0) * height)
        else:
            mid_x = int((x1 + x2) / 2.0)
            mid_y = int((y1 + y2) / 2.0)
        mid_pt = (min(max(0, mid_x), width), min(max(0, mid_y), height))
        return None if mid_pt == (0, 0) else mid_pt

    elif len(numbers) >= 2:
        x, y = numbers[0], numbers[1]
        if max(x, y) <= 1.0:
            px = int(x * width)
            py = int(y * height)
        elif is_normalized_1000 or (match is not None and max(x, y) <= 1000) or x > width or y > height:
            px = int((x / 1000.0) * width)
            py = int((y / 1000.0) * height)
        else:
            px = int(x)
            py = int(y)
        pt = (min(max(0, px), width), min(max(0, py), height))
        return None if pt == (0, 0) else pt

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


def resolve_ui_target(
    query: str,
    screenshot_b64: Optional[str] = None,
    width: int = 1280,
    height: int = 800,
    grounding_fn: Optional[Any] = None,
    allow_landmarks: bool = True,
) -> Optional[Tuple[int, int]]:
    """Resolves a natural language UI target query to absolute screen coordinates (x, y).

    Resolution pipeline:
    1. Direct numeric coordinate check (if query is already "640,400").
    2. Dynamic Multimodal Grounding Function (vision LLM / ShowUI / OS-Atlas) if provided.
    Strictly forbids falling back to arbitrary mock percentage landmarks or blind clicking.
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

    return None


async def resolve_ui_target_async(
    query: str,
    screenshot_b64: Optional[str] = None,
    width: int = 1280,
    height: int = 800,
    grounding_fn: Optional[Any] = None,
    allow_landmarks: bool = True,
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
    from sonic.llm.prompts import grounding_user_prompt
    from sonic.llm.schemas import ImageContent, LLMRequest, Message, MessageRole

    raw_b64 = screenshot_b64.split(",", 1)[-1] if "," in screenshot_b64 else screenshot_b64
    images = [ImageContent(base64=raw_b64, media_type="image/png")]
    prompt = grounding_user_prompt(query, width, height)
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
    Hierarchical micro-crop targeting of high-density UI toolbars (e.g. dense GUI components, navigation bars, buttons).

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
