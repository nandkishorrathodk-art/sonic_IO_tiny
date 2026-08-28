"""
SONIC-REDA — Abstract LLM Provider Interface
================================================
This is the CORE ABSTRACTION that all LLM providers must implement.

Any model provider (Claude, OpenAI, Grok, DeepSeek, local, custom) 
must subclass LLMProvider and implement these methods.

This ensures:
    1. Every provider is interchangeable
    2. Model Router can switch between them seamlessly
    3. New providers can be added with minimal effort
    4. All agents use the same interface regardless of backend model
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from typing import AsyncIterator

from sonic.logger import get_logger
from sonic.llm.schemas import (
    LLMChunk,
    LLMRequest,
    LLMResponse,
    ModelInfo,
    ProviderName,
    TokenUsage,
)

logger = get_logger(__name__)


class LLMProvider(ABC):
    """
    Abstract base class for all LLM providers.
    
    Every provider (Claude, OpenAI, Grok, DeepSeek, Local) must implement:
        - complete()   → Single response
        - stream()     → Streaming async generator
        - list_models() → Available models
        - health_check() → Is the provider reachable?
    
    Usage:
        provider = ClaudeProvider(api_key="...")
        response = await provider.complete(request)
        
        async for chunk in provider.stream(request):
            print(chunk.content, end="")
    """

    def __init__(self, provider_name: ProviderName, api_key: str = "", base_url: str = ""):
        self.provider_name = provider_name
        self.api_key = api_key
        self.base_url = base_url
        self._request_count = 0
        self._total_tokens = 0
        self._total_cost_usd = 0.0

    # ============================================
    # Abstract Methods (MUST be implemented)
    # ============================================

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Send a completion request and return the full response.
        
        Args:
            request: Provider-agnostic LLM request
            
        Returns:
            Provider-agnostic LLM response
            
        Raises:
            Exception: If the API call fails after retries
        """
        ...

    @abstractmethod
    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        """
        Send a streaming completion request.
        Yields chunks as they arrive from the provider.
        
        Args:
            request: Provider-agnostic LLM request (stream flag is set)
            
        Yields:
            LLMChunk objects with incremental content
        """
        ...

    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """
        Return the list of models available from this provider.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the provider is reachable and the API key is valid.
        
        Returns:
            True if healthy, False otherwise
        """
        ...

    # ============================================
    # Shared Methods (inherited by all providers)
    # ============================================

    def generate_request_id(self) -> str:
        """Generate a unique request ID for tracking."""
        return f"{self.provider_name}-{uuid.uuid4().hex[:12]}"

    def track_usage(self, usage: TokenUsage, cost_usd: float) -> None:
        """Track cumulative usage statistics."""
        self._request_count += 1
        self._total_tokens += usage.total_tokens
        self._total_cost_usd += cost_usd

    def get_stats(self) -> dict:
        """Get cumulative provider usage statistics."""
        return {
            "provider": self.provider_name,
            "total_requests": self._request_count,
            "total_tokens": self._total_tokens,
            "total_cost_usd": round(self._total_cost_usd, 6),
        }

    async def complete_with_timing(self, request: LLMRequest) -> LLMResponse:
        """
        Wrapper around complete() that adds latency measurement.
        All agents should use this instead of complete() directly.
        """
        request_id = self.generate_request_id()
        start_time = time.perf_counter()

        logger.info(
            "llm_request_start",
            provider=self.provider_name,
            model=request.model,
            task_type=request.task_type,
            agent_id=request.agent_id,
            request_id=request_id,
        )

        try:
            response = await self.complete(request)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            response.latency_ms = elapsed_ms
            response.request_id = request_id
            self.track_usage(response.usage, response.cost_usd)

            logger.info(
                "llm_request_complete",
                provider=self.provider_name,
                model=response.model,
                latency_ms=round(elapsed_ms, 1),
                tokens=response.usage.total_tokens,
                cost_usd=round(response.cost_usd, 6),
                request_id=request_id,
            )
            return response

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "llm_request_failed",
                provider=self.provider_name,
                model=request.model,
                error=str(e),
                latency_ms=round(elapsed_ms, 1),
                request_id=request_id,
            )
            raise

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} provider={self.provider_name}>"
