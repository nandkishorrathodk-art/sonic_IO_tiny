import pytest
import time
from unittest.mock import AsyncMock, MagicMock

from sonic.computer_use.grounding import (
    extract_bbox_midpoint,
    resolve_ui_target,
    _COMMON_UI_LANDMARKS,
)
from sonic.llm.router import ModelRouter
from sonic.llm.schemas import ImageContent, LLMRequest, Message, MessageRole


def test_models_yaml_kimi_k3_routing():
    """Verify visual tasks use a provider/model configured for multimodal input."""
    router = ModelRouter.from_config("configs/models.yaml", env_vars={"NVIDIA_API_KEY": "test-key", "GROQ_API_KEY": "groq-key"})
    assert router.default_provider == "groq"
    
    prov_vision, model_vision = router._resolve_provider(task_type="vision")
    assert prov_vision.name == "nvidia"
    assert model_vision == "moonshotai/kimi-k3"

    prov_cu, model_cu = router._resolve_provider(task_type="computer_use")
    assert prov_cu.name == "nvidia"
    assert model_cu == "moonshotai/kimi-k3"

    prov_reasoning, model_reasoning = router._resolve_provider(task_type="reasoning")
    assert prov_reasoning.name == "groq"
    assert model_reasoning == "qwen/qwen3.8-27b"


@pytest.mark.asyncio
async def test_multimodal_image_auto_routes_to_vision():
    """Verify that requests carrying images automatically route to vision model."""
    router = ModelRouter.from_config("configs/models.yaml", env_vars={"NVIDIA_API_KEY": "test-key", "GROQ_API_KEY": "groq-key"})
    mock_provider = MagicMock()
    mock_provider.name = "nvidia"
    mock_provider.default_model = "moonshotai/kimi-k3"
    mock_provider.complete_with_timing = AsyncMock()
    
    mock_response = MagicMock()
    mock_response.request_id = "test-123"
    mock_response.provider = "nvidia"
    mock_response.model = "moonshotai/kimi-k3"
    mock_response.content = "<|box_start|>(350, 160, 450, 200)<|box_end|>"
    mock_response.usage.prompt_tokens = 50
    mock_response.usage.completion_tokens = 10
    mock_response.cost_usd = 0.0001
    mock_provider.complete_with_timing.return_value = mock_response

    router.providers["nvidia"] = mock_provider

    req = LLMRequest(
        messages=[
            Message(
                role=MessageRole.USER,
                content="Where is the search bar?",
                images=[ImageContent(base64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")],
            )
        ],
        task_type="reasoning",
    )
    res = await router.complete(req)
    assert req.task_type == "vision"
    assert res.content == "<|box_start|>(350, 160, 450, 200)<|box_end|>"


def test_bbox_parsing_accuracy():
    """Verify bbox extraction handles <|box_start|>, normalized 0-1000, 0-1, and direct pixels."""
    coords = extract_bbox_midpoint("<|box_start|>(100, 100, 300, 300)<|box_end|>", width=1280, height=800)
    assert coords == (256, 160)

    coords_float = extract_bbox_midpoint("[0.5, 0.5]", width=1280, height=800)
    assert coords_float == (640, 400)

    coords_px = extract_bbox_midpoint("Center is [640, 400]", width=1280, height=800)
    assert coords_px == (640, 400)


def test_expanded_web_landmarks():
    """Vendor-specific landmarks are not embedded in the grounding catalog."""
    assert _COMMON_UI_LANDMARKS == {}
    assert resolve_ui_target("search field", width=1280, height=800) is None
    assert resolve_ui_target("connect wallet", width=1280, height=800) is None
