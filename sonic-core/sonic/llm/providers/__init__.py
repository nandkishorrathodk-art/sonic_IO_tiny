"""
SONIC-REDA LLM Providers
=========================
Single custom provider that works with ANY OpenAI-compatible or Anthropic endpoint.

Usage:
    from sonic.llm.providers.custom import CustomLLMProvider

    provider = CustomLLMProvider(
        name="grok",
        base_url="https://api.x.ai/v1",
        api_key="xai-...",
        default_model="grok-3",
    )
"""

from sonic.llm.providers.custom import CustomLLMProvider

__all__ = ["CustomLLMProvider"]
