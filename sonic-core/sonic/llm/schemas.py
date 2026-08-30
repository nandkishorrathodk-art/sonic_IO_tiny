"""
SONIC-REDA — LLM Data Schemas
================================
Pydantic models for LLM requests, responses, streaming, and model metadata.
These schemas are provider-agnostic — every provider maps to/from these.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ============================================
# Enums
# ============================================

class MessageRole(StrEnum):
    """Standard message roles across all providers."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class SpeedTier(StrEnum):
    """Model speed classification."""
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"


class ProviderName(StrEnum):
    """Supported LLM provider identifiers."""
    CLAUDE = "claude"
    OPENAI = "openai"
    GROK = "grok"
    DEEPSEEK = "deepseek"
    LOCAL = "local"


# ============================================
# Request Models
# ============================================

class ImageContent(BaseModel):
    """An image attached to a message (base64 or URL)."""
    base64: Optional[str] = None  # Raw base64 data (no data: prefix)
    url: Optional[str] = None     # Image URL
    media_type: str = "image/png"  # MIME type when base64 is used


class Message(BaseModel):
    """A single message in a conversation.

    For multimodal/vision requests, set `content` to the text prompt and
    `images` to a list of ImageContent. Providers will merge them into the
    appropriate multipart format (OpenAI content array, Anthropic content blocks).
    """
    role: MessageRole
    content: str
    images: list[ImageContent] = Field(default_factory=list)
    name: Optional[str] = None  # For tool messages
    tool_call_id: Optional[str] = None  # For tool responses

    @property
    def has_images(self) -> bool:
        return bool(self.images)


class ToolDefinition(BaseModel):
    """Tool/function definition for function calling."""
    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class LLMRequest(BaseModel):
    """
    Provider-agnostic LLM request.
    Every provider converts this into their specific format.
    """
    messages: list[Message]
    model: Optional[str] = None  # If None, use routing default
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    tools: Optional[list[ToolDefinition]] = None
    stop_sequences: Optional[list[str]] = None
    stream: bool = False

    # SONIC-REDA metadata
    task_type: Optional[str] = None  # e.g., "planning", "reasoning", "fast_recon"
    agent_id: Optional[str] = None  # Which agent is making this request
    engagement_id: Optional[str] = None  # Which engagement this belongs to


# ============================================
# Response Models
# ============================================

class ToolCall(BaseModel):
    """A tool/function call made by the model."""
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class TokenUsage(BaseModel):
    """Token usage statistics."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @property
    def cost_estimate(self) -> float:
        """Rough cost estimate (will be refined by provider)."""
        return 0.0


class LLMResponse(BaseModel):
    """
    Provider-agnostic LLM response.
    Every provider maps their response into this format.
    """
    content: str = ""
    model: str = ""
    provider: ProviderName = ProviderName.CLAUDE
    role: MessageRole = MessageRole.ASSISTANT
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    finish_reason: Optional[str] = None  # "stop", "tool_calls", "max_tokens"
    latency_ms: float = 0.0

    # SONIC-REDA metadata
    request_id: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    cost_usd: float = 0.0


class LLMChunk(BaseModel):
    """
    A single chunk from a streaming response.
    Used with async generators for real-time output.
    """
    content: str = ""
    role: Optional[MessageRole] = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: Optional[str] = None
    is_final: bool = False

    # Accumulated usage (only in final chunk)
    usage: Optional[TokenUsage] = None


# ============================================
# Model Metadata
# ============================================

class ModelInfo(BaseModel):
    """Information about an available model."""
    id: str  # e.g., "claude-sonnet-4-20250514"
    provider: ProviderName
    name: Optional[str] = None  # Human-readable name
    speed_tier: SpeedTier = SpeedTier.MEDIUM
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    max_context_tokens: int = 128000
    capabilities: list[str] = Field(default_factory=list)
    is_available: bool = True


class ModelRoutingRule(BaseModel):
    """Maps a task type to preferred model + fallbacks."""
    task_type: str
    description: str = ""
    provider: ProviderName
    model: str
    fallback: list[str] = Field(default_factory=list)  # "provider/model" format


# ============================================
# Cost Tracking
# ============================================

class CostRecord(BaseModel):
    """Tracks cost for a single LLM request."""
    request_id: str
    provider: ProviderName
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    agent_id: Optional[str] = None
    engagement_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
