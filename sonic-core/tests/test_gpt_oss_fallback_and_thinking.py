"""
Unit and integration tests for openai/gpt-oss-20b NVIDIA fallback
and enhanced thinking / chain-of-thought capture.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from sonic.config import PROJECT_ROOT
from sonic.llm.router import ModelRouter
from sonic.llm.schemas import LLMRequest, LLMResponse, Message, MessageRole
from sonic.llm.providers.custom import CustomLLMProvider
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import ComputerWorldObservation


def test_models_yaml_registers_gpt_oss_under_nvidia():
    """Verify openai/gpt-oss-20b is registered in nvidia fallback models."""
    router = ModelRouter.from_config(PROJECT_ROOT / "configs" / "models.yaml")
    assert "nvidia" in router.providers
    nvidia = router.providers["nvidia"]
    assert "openai/gpt-oss-20b" in nvidia.fallback_models


def test_routing_rules_contain_fallbacks():
    """Verify every core routing rule is configured with a non-empty fallback chain."""
    router = ModelRouter.from_config(PROJECT_ROOT / "configs" / "models.yaml")
    expected_rules = ["planning", "reasoning", "coding", "hypothesis", "verification", "computer_use", "vision"]
    for rule in expected_rules:
        assert rule in router.routing_rules
        fallbacks = router.routing_rules[rule].get("fallback", [])
        assert fallbacks, f"{rule} has no configured fallbacks"


@pytest.mark.asyncio
async def test_custom_provider_passes_reasoning_effort():
    """Verify reasoning_effort is passed to extra_body for reasoning models."""
    provider = CustomLLMProvider(
        name="nvidia",
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="test-key",
        default_model="openai/gpt-oss-20b",
    )

    captured_kwargs = {}

    class MockChatCompletions:
        async def create(self, **kwargs):
            nonlocal captured_kwargs
            captured_kwargs = kwargs
            choice = MagicMock()
            choice.message.content = "THOUGHT: Analyzing\nACTION: TERMINAL_EXEC\nTARGET: ls\nPAYLOAD: {}\nEXPECTED: files"
            choice.message.reasoning_content = "Step 1: check files"
            choice.message.tool_calls = None
            choice.finish_reason = "stop"
            resp = MagicMock()
            resp.choices = [choice]
            resp.usage = None
            return resp

    mock_client = MagicMock()
    mock_client.chat.completions = MockChatCompletions()
    provider._openai_client = mock_client

    req = LLMRequest(
        messages=[Message(role=MessageRole.USER, content="hello")],
        model="openai/gpt-oss-20b",
        reasoning_effort="high",
    )

    response = await provider.complete(req)
    assert captured_kwargs.get("extra_body", {}).get("reasoning_effort") == "high"
    assert response.reasoning_content == "Step 1: check files"
    assert "Analyzing" in response.content


@pytest.mark.asyncio
async def test_custom_provider_uses_reasoning_content_when_content_empty():
    """Verify provider falls back to reasoning_content if content is empty."""
    provider = CustomLLMProvider(
        name="nvidia",
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="test-key",
        default_model="openai/gpt-oss-20b",
    )

    class MockChatCompletions:
        async def create(self, **kwargs):
            choice = MagicMock()
            choice.message.content = ""
            choice.message.reasoning_content = "THOUGHT: Deep thinking done\nACTION: TERMINAL_EXEC\nTARGET: pwd\nPAYLOAD: {}\nEXPECTED: path"
            choice.message.tool_calls = None
            choice.finish_reason = "stop"
            resp = MagicMock()
            resp.choices = [choice]
            resp.usage = None
            return resp

    mock_client = MagicMock()
    mock_client.chat.completions = MockChatCompletions()
    provider._openai_client = mock_client

    req = LLMRequest(
        messages=[Message(role=MessageRole.USER, content="inspect")],
        model="openai/gpt-oss-20b",
    )

    response = await provider.complete(req)
    assert response.reasoning_content.startswith("THOUGHT: Deep thinking done")
    assert response.content == response.reasoning_content


@pytest.mark.asyncio
async def test_agent_captures_reasoning_content_in_last_thought():
    """Verify ComputerUseAgent extracts reasoning_content directly into _last_thought."""
    mock_computer = MagicMock()
    mock_router = MagicMock()

    agent = ComputerUseAgent(
        computer_provider=mock_computer,
        llm_router=mock_router,
    )

    mock_router.complete = AsyncMock(return_value=LLMResponse(
        content="ACTION: TERMINAL_EXEC\nTARGET: echo 1\nPAYLOAD: {\"command\": \"echo 1\"}\nEXPECTED: 1",
        reasoning_content="Deconstructing goal into sub-steps: 1. Echo probe. 2. Verify response.",
        model="openai/gpt-oss-20b",
    ))

    obs = ComputerWorldObservation(
        terminal_output="Ready",
        filesystem_files=["app.py"],
    )

    action, target, payload, expected = await agent.choose_action(
        goal="Run probe",
        observation=obs,
        step_index=1,
    )

    assert agent._last_thought == "Deconstructing goal into sub-steps: 1. Echo probe. 2. Verify response."
    assert payload.get("command") == "echo 1"


@pytest.mark.asyncio
async def test_agent_history_preserves_and_feeds_back_thoughts():
    """Verify that thoughts are saved in history and fed back into the next step's context."""
    mock_computer = MagicMock()
    mock_computer.terminal = AsyncMock(return_value="pong")
    mock_computer.execute = AsyncMock(return_value=MagicMock(exit_code=0, stdout="pong", stderr=""))
    mock_router = MagicMock()

    agent = ComputerUseAgent(
        computer_provider=mock_computer,
        llm_router=mock_router,
    )

    # Simulate step 1 thought
    agent._last_thought = "Target seems to have an active HTTP service; checking ping"

    # Execute action
    from sonic.computer_use.models import ComputerActionType
    await agent.execute_action(
        action_type=ComputerActionType.TERMINAL_EXEC,
        target_resource="ping -c 1 127.0.0.1",
        payload={"command": "ping -c 1 127.0.0.1"},
        predicted_outcome="pong",
        workspace_id="default",
    )

    # 1. Check history recorded thought
    assert len(agent.history) == 1
    assert agent.history[0]["thought"] == "Target seems to have an active HTTP service; checking ping"

    # 2. Check rendered history displays thought
    formatted = agent._format_history()
    assert "Thought: Target seems to have an active HTTP service; checking ping" in formatted

    # 3. Check next step observation context includes immediate prior thought
    obs = ComputerWorldObservation(terminal_output="pong")
    _, obs_summary = agent._build_reasoning_context(
        goal="Assess target",
        observation=obs,
        step_index=2,
        primary_file="",
        test_file="",
    )
    assert "Your Immediate Prior Thought was:" in obs_summary
    assert "Target seems to have an active HTTP service; checking ping" in obs_summary


