"""
SONIC-REDA — Custom LLM Provider
====================================
ONE universal provider that works with ANY OpenAI-compatible API endpoint.

Instead of separate Claude/OpenAI/Grok/DeepSeek providers, the team simply
configures instances with:
    - base_url: Any API endpoint (OpenAI, Grok, DeepSeek, local Ollama, custom)
    - api_key: Authentication key
    - model: Default model to use
    - name: Human-readable label for this provider

This covers 99% of LLM APIs because most providers now offer OpenAI-compatible
endpoints. For Anthropic Claude (which uses a different API format), a separate
adapter handles the conversion internally.

Usage:
    # OpenAI
    openai = CustomLLMProvider(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-...",
        default_model="gpt-4o",
    )

    # Grok (OpenAI-compatible)
    grok = CustomLLMProvider(
        name="grok",
        base_url="https://api.x.ai/v1",
        api_key="xai-...",
        default_model="grok-3",
    )

    # DeepSeek (OpenAI-compatible)
    deepseek = CustomLLMProvider(
        name="deepseek",
        base_url="https://api.deepseek.com",
        api_key="sk-...",
        default_model="deepseek-coder",
    )

    # Local Ollama
    local = CustomLLMProvider(
        name="local",
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        default_model="llama3.1:70b",
    )

    # Claude (auto-detected, uses Anthropic SDK internally)
    claude = CustomLLMProvider(
        name="claude",
        base_url="https://api.anthropic.com",
        api_key="sk-ant-...",
        default_model="claude-sonnet-4-20250514",
    )

    # Any custom endpoint your team runs
    custom = CustomLLMProvider(
        name="my-fine-tuned",
        base_url="https://my-company.com/llm/v1",
        api_key="my-key",
        default_model="ft-model-v3",
    )
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

from sonic.llm.base import LLMProvider
from sonic.logger import get_logger

logger = get_logger(__name__)
from sonic.llm.schemas import (
    LLMChunk,
    LLMRequest,
    LLMResponse,
    MessageRole,
    ModelInfo,
    ProviderName,
    SpeedTier,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)


def _is_anthropic_endpoint(base_url: str) -> bool:
    """Check if this is an Anthropic Claude endpoint (needs different API format)."""
    return "anthropic.com" in base_url.lower()


def _is_transport_error(error: Exception) -> bool:
    """Identify SDK transport failures that are safe to retry with raw HTTPX."""
    error_text = f"{type(error).__name__} {error}".lower()
    return any(
        marker in error_text
        for marker in ("connection", "connecterror", "timeout", "ssl", "transport", "network")
    )


def _is_model_not_found_error(error: Exception) -> bool:
    """Identify model-not-found / EOL / deprecated model errors.

    These indicate the model name is invalid or has been retired, not a
    transient transport failure. Used to trigger model-level fallback.
    """
    error_text = f"{type(error).__name__} {error}".lower()
    return any(
        marker in error_text
        for marker in (
            "model not found",
            "does not exist",
            "model_not_found",
            "deprecat",
            "no longer available",
            "has been retired",
            "not a valid model",
            "invalid model",
            "404",
        )
    )


def _is_transient_error(error: Exception) -> bool:
    """Identify transient errors that are safe to retry on the SAME provider/model.

    Covers rate limits (429), server errors (5xx), and network/transport
    failures. Non-transient errors (auth, bad request, model not found) are
    intentionally NOT retried — they will not succeed by repeating the request.
    """
    error_text = f"{type(error).__name__} {error}".lower()
    # HTTP status markers surfaced by SDKs / httpx.
    status_markers = (
        "429", "rate limit", "rate_limit", "overloaded",
        "500", "502", "503", "504", "server error", "service unavailable",
        "internal server error", "bad gateway", "gateway timeout",
        "too many requests",
    )
    if any(marker in error_text for marker in status_markers):
        return True
    return _is_transport_error(error)


def _is_quota_exhausted_error(error: Exception) -> bool:
    """Return true for provider quotas that cannot recover by immediate retry."""
    error_text = f"{type(error).__name__} {error}".lower()
    return (
        ("tokens per day" in error_text or "tpd" in error_text)
        and ("429" in error_text or "rate limit" in error_text or "rate_limit" in error_text)
    )


def _provider_reasoning_effort(model: str, requested: str | None) -> str | None:
    """Normalize reasoning controls for provider-specific OpenAI-compatible APIs."""
    if requested is None:
        return None
    # Groq's Qwen reasoning models accept only these two values. Sending
    # medium/high produces a non-transient 400 and needlessly burns fallback
    # latency before the provider can answer.
    if "qwen3.6" in model.lower() or "qwen3.8" in model.lower():
        return requested if requested in {"none", "default"} else "default"
    return requested


def _extract_json_object(raw: str) -> dict | None:
    """Best-effort extraction of a JSON object from an LLM tool-call argument string.

    Models occasionally wrap tool arguments in prose or trailing text, or emit
    slightly malformed JSON (e.g., trailing commas, single quotes). This scans
    for the first balanced ``{ ... }`` region and parses it; on failure it falls
    back to permissive fixes (single→double quotes, trailing comma removal).
    Returns the parsed dict, or ``None`` if no JSON object could be recovered.
    """
    if not raw:
        return None
    text = raw.strip()
    # Fast path: already valid JSON.
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        pass
    # Scan for the first balanced object region.
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        obj = json.loads(candidate)
                        return obj if isinstance(obj, dict) else None
                    except (json.JSONDecodeError, ValueError):
                        # Try permissive fixups on this candidate.
                        fixed = candidate.replace("'", '"')
                        fixed = re.sub(r",(\s*[}\]])", r"\1", fixed)
                        try:
                            obj = json.loads(fixed)
                            return obj if isinstance(obj, dict) else None
                        except (json.JSONDecodeError, ValueError):
                            break
        start = text.find("{", start + 1)
    return None


def parse_tool_arguments(raw: str | None) -> dict:
    """Parse an LLM tool-call argument string into a dict, tolerating noise.

    Public helper reused by the ReAct engine and provider code paths so that a
    single robust parsing strategy governs every tool-call argument.
    """
    if not raw or not raw.strip():
        return {}
    extracted = _extract_json_object(raw)
    if extracted is not None:
        return extracted
    # Last resort: the whole string is a bare value (e.g. a command). Wrap it so
    # callers that expect a dict still receive something usable.
    return {"value": raw.strip()}


class CustomLLMProvider(LLMProvider):
    """
    Universal LLM Provider — works with ANY OpenAI-compatible API.

    For Anthropic endpoints, automatically switches to Claude's API format.
    For everything else (OpenAI, Grok, DeepSeek, Ollama, custom), uses
    the standard OpenAI chat completions format.

    Config needed:
        - name: Label for this provider (e.g., "grok", "my-model")
        - base_url: API endpoint URL
        - api_key: API key for authentication
        - default_model: Model ID to use by default
    """

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        default_model: str,
        cost_per_1k_input: float = 0.0,
        cost_per_1k_output: float = 0.0,
        max_context_tokens: int = 128000,
        capabilities: list[str] | None = None,
        speed_tier: SpeedTier = SpeedTier.MEDIUM,
        timeout_seconds: int = 120,
        fallback_models: list[str] | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 0.5,
        retry_max_delay: float = 20.0,
        max_tokens_cap: int | None = None,
    ):
        # Map name to ProviderName enum if possible, else use CLAUDE as fallback
        try:
            provider_name = ProviderName(name.lower())
        except ValueError:
            provider_name = ProviderName.LOCAL  # Custom providers mapped as "local"

        super().__init__(
            provider_name=provider_name,
            api_key=api_key,
            base_url=base_url.rstrip("/"),
        )

        self.name = name
        self.default_model = default_model
        # Model-level fallback chain (tried when the primary model is EOL/not-found)
        self.fallback_models: list[str] = fallback_models or []
        self.cost_per_1k_input = cost_per_1k_input
        self.cost_per_1k_output = cost_per_1k_output
        self.max_context_tokens = max_context_tokens
        self.capabilities = capabilities or ["general"]
        self.speed_tier = speed_tier
        self.timeout_seconds = timeout_seconds
        self.is_anthropic = _is_anthropic_endpoint(base_url)
        # Transient-error retry policy (rate limits, 5xx, transport). These are
        # per-request retries on the SAME provider/model — distinct from the
        # model-level (EOL) and provider-level fallback chains. Set max_retries=0
        # to disable.
        self.max_retries = max(0, max_retries)
        self.retry_base_delay = max(0.0, retry_base_delay)
        self.retry_max_delay = max(self.retry_base_delay, retry_max_delay)
        # Hard cap on output tokens per request. Providers with strict per-minute
        # output budgets (e.g. Groq on-demand OTPM=1000) reject any request whose
        # declared max_tokens exceeds the limit, even when the actual output is
        # tiny. Capping avoids deterministic 429s that retries can never clear.
        self.max_tokens_cap = max_tokens_cap if (max_tokens_cap and max_tokens_cap > 0) else None

        # Try to use the official SDKs if available, otherwise fall back to httpx
        self._openai_client = None
        self._anthropic_client = None

        if self.is_anthropic:
            try:
                if api_key:
                    from anthropic import AsyncAnthropic
                    self._anthropic_client = AsyncAnthropic(api_key=api_key)
                    logger.info("provider_init_anthropic_sdk", name=name)
                else:
                    self._anthropic_client = None
            except Exception:
                self._anthropic_client = None
        else:
            try:
                if api_key:
                    from openai import AsyncOpenAI
                    self._openai_client = AsyncOpenAI(
                        api_key=api_key,
                        base_url=self.base_url,
                        timeout=timeout_seconds,
                    )
                    logger.info("provider_init_openai_sdk", name=name, base_url=base_url)
                else:
                    self._openai_client = None
            except Exception:
                self._openai_client = None

    def _effective_max_tokens(self, request_max_tokens: int) -> int:
        """Return request max_tokens, clamped by this provider's output cap."""
        raw = request_max_tokens if request_max_tokens > 0 else self.max_context_tokens
        if self.max_tokens_cap is not None:
            return min(raw, self.max_tokens_cap)
        return raw

    # ============================================
    # Message Conversion
    # ============================================

    def _to_openai_messages(self, request: LLMRequest) -> list[dict]:
        """Convert SONIC messages to OpenAI format (with multimodal/vision support)."""
        messages = []
        for msg in request.messages:
            if msg.has_images:
                # Build multipart content array for vision models
                content_parts: list[dict] = []
                if msg.content:
                    content_parts.append({"type": "text", "text": msg.content})
                for img in msg.images:
                    if img.base64:
                        data_url = f"data:{img.media_type};base64,{img.base64}"
                        content_parts.append({"type": "image_url", "image_url": {"url": data_url}})
                    elif img.url:
                        content_parts.append({"type": "image_url", "image_url": {"url": img.url}})
                messages.append({"role": msg.role.value, "content": content_parts})
            else:
                messages.append({"role": msg.role.value, "content": msg.content})
        return messages

    def _to_anthropic_messages(self, request: LLMRequest) -> tuple[str, list[dict]]:
        """Convert SONIC messages to Anthropic format (separate system prompt + vision blocks)."""
        system_prompt = ""
        messages = []
        for msg in request.messages:
            if msg.role == MessageRole.SYSTEM:
                system_prompt = msg.content
            elif msg.has_images:
                # Anthropic vision: content blocks with text + image
                content_blocks: list[dict] = []
                if msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                for img in msg.images:
                    if img.base64:
                        content_blocks.append({
                            "type": "image",
                            "source": {"type": "base64", "media_type": img.media_type, "data": img.base64},
                        })
                    elif img.url:
                        content_blocks.append({"type": "image", "source": {"type": "url", "url": img.url}})
                messages.append({"role": msg.role.value, "content": content_blocks})
            else:
                messages.append({"role": msg.role.value, "content": msg.content})
        return system_prompt, messages

    def _to_openai_tools(self, tools: list[ToolDefinition] | None) -> list[dict] | None:
        """Convert SONIC tools to OpenAI function calling format."""
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    def _to_anthropic_tools(self, tools: list[ToolDefinition] | None) -> list[dict] | None:
        """Convert SONIC tools to Anthropic tool format."""
        if not tools:
            return None
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            }
            for tool in tools
        ]

    def _calculate_cost(self, usage: TokenUsage) -> float:
        """Calculate cost in USD based on configured rates."""
        return (
            (usage.prompt_tokens / 1000) * self.cost_per_1k_input
            + (usage.completion_tokens / 1000) * self.cost_per_1k_output
        )

    # ============================================
    # Complete (Single Response)
    # ============================================

    async def _with_retry(
        self,
        request: LLMRequest,
        call: Any,
    ) -> LLMResponse:
        """Run a single completion attempt with transient-error retry/backoff.

        ``call`` is the bound, model-specific completion coroutine. Retries only
        on transient errors (429/5xx/transport); auth/bad-request/model-not-found
        errors propagate immediately to the model- and provider-level fallback
        chains (which live in ``complete`` and the router respectively).
        """
        attempt = 0
        last_error: Exception | None = None
        while attempt <= self.max_retries:
            try:
                return await call(request)
            except Exception as e:
                last_error = e
                if (
                    not _is_transient_error(e)
                    or _is_quota_exhausted_error(e)
                    or attempt == self.max_retries
                ):
                    raise
                # Exponential backoff with full jitter, capped at retry_max_delay.
                import random
                ceiling = min(self.retry_max_delay, self.retry_base_delay * (2 ** attempt))
                delay = random.uniform(0, ceiling)
                logger.warning(
                    "llm_transient_retry",
                    name=self.name,
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    backoff_seconds=round(delay, 2),
                    error=str(e),
                )
                await asyncio.sleep(delay)
                attempt += 1
        # Defensive: unreachable, but keep mypy satisfied.
        assert last_error is not None
        raise last_error

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request. Auto-detects Anthropic vs OpenAI format.

        Transient errors (rate limits, 5xx, transport) are retried on the same
        provider/model with exponential backoff. On model-not-found/EOL errors,
        retries with configured fallback_models before re-raising to the
        router's provider-level fallback chain.
        """
        original_model = request.model or self.default_model
        try:
            call = self._complete_anthropic if self.is_anthropic else self._complete_openai
            return await self._with_retry(request, call)
        except Exception as e:
            if _is_model_not_found_error(e) and self.fallback_models:
                logger.warning(
                    "model_not_found_trying_fallbacks",
                    name=self.name,
                    original_model=original_model,
                    fallbacks=self.fallback_models,
                    error=str(e),
                )
                for fb_model in self.fallback_models:
                    if fb_model == original_model:
                        continue
                    try:
                        request.model = fb_model
                        logger.info("model_fallback_attempt", name=self.name, model=fb_model)
                        call = self._complete_anthropic if self.is_anthropic else self._complete_openai
                        return await self._with_retry(request, call)
                    except Exception as fb_err:
                        if _is_model_not_found_error(fb_err):
                            logger.warning("model_fallback_also_not_found", name=self.name, model=fb_model)
                            continue
                        raise  # Different error — propagate
                # All fallbacks exhausted — re-raise original
            raise

    async def _complete_openai(self, request: LLMRequest) -> LLMResponse:
        """Complete via OpenAI-compatible API (works for most providers)."""
        model = request.model or self.default_model
        messages = self._to_openai_messages(request)
        tools = self._to_openai_tools(request.tools)

        if self._openai_client:
            # Use official SDK
            extra_body: dict[str, Any] = dict(request.extra_body)
            reasoning_models = ("gpt-oss", "deepseek-r1", "deepseek-reasoner", "reasoning", "o1", "o3")
            reasoning_effort = _provider_reasoning_effort(model, request.reasoning_effort)
            if reasoning_effort:
                extra_body["reasoning_effort"] = reasoning_effort
            elif any(rm in model.lower() for rm in reasoning_models):
                extra_body.setdefault("reasoning_effort", "high")

            eff_top_p = request.top_p
            if "kimi" in model.lower() or "moonshotai" in model.lower():
                eff_top_p = 0.95

            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "max_tokens": self._effective_max_tokens(request.max_tokens),
                "temperature": request.temperature,
                "top_p": eff_top_p,
            }
            if extra_body:
                kwargs["extra_body"] = extra_body
            if tools:
                kwargs["tools"] = tools
            if request.stop_sequences:
                kwargs["stop"] = request.stop_sequences

            try:
                response = await self._openai_client.chat.completions.create(**kwargs)
            except Exception as sdk_error:
                # The OpenAI SDK can fail at the Windows TLS/transport layer even
                # when the same OpenAI-compatible endpoint is reachable via
                # HTTPX. Retry only transport failures; API/auth errors must
                # remain visible and must not be hidden by a second request.
                if not _is_transport_error(sdk_error):
                    raise
                logger.warning(
                    "provider_sdk_transport_failed_using_httpx",
                    name=self.name,
                    error=str(sdk_error),
                )
                return await self._complete_httpx_openai(model, messages, request, tools)
            choice = response.choices[0]

            # Extract tool calls
            tool_calls = []
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    tool_calls.append(ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=parse_tool_arguments(tc.function.arguments),
                    ))

            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                completion_tokens=response.usage.completion_tokens if response.usage else 0,
                total_tokens=response.usage.total_tokens if response.usage else 0,
            )

            # Extract reasoning_content / chain-of-thought
            reasoning_content = (
                getattr(choice.message, "reasoning_content", None)
                or getattr(choice.message, "reasoning", None)
                or (choice.message.model_dump().get("reasoning_content") if hasattr(choice.message, "model_dump") else None)
                or ""
            )
            content = choice.message.content or ""
            if not content and reasoning_content:
                content = reasoning_content

            return LLMResponse(
                content=content,
                reasoning_content=reasoning_content,
                model=model,
                provider=self.provider_name,
                tool_calls=tool_calls,
                usage=usage,
                finish_reason=choice.finish_reason or "stop",
                cost_usd=self._calculate_cost(usage),
            )
        else:
            # Fallback to raw httpx
            return await self._complete_httpx_openai(model, messages, request, tools)

    async def _complete_httpx_openai(
        self,
        model: str,
        messages: list[dict],
        request: LLMRequest,
        tools: list[dict] | None,
    ) -> LLMResponse:
        """Fallback: raw HTTP request for OpenAI-compatible APIs."""
        eff_top_p = request.top_p
        if "kimi" in model.lower() or "moonshotai" in model.lower():
            eff_top_p = 0.95
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": self._effective_max_tokens(request.max_tokens),
            "temperature": request.temperature,
            "top_p": eff_top_p,
        }
        reasoning_models = ("gpt-oss", "deepseek-r1", "deepseek-reasoner", "reasoning", "o1", "o3")
        reasoning_effort = _provider_reasoning_effort(model, request.reasoning_effort)
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        elif any(rm in model.lower() for rm in reasoning_models):
            payload["reasoning_effort"] = "high"
        if request.extra_body:
            payload.update(request.extra_body)
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        msg = choice.get("message", {})
        content = msg.get("content") or ""
        reasoning_content = msg.get("reasoning_content") or msg.get("reasoning") or ""
        if not content and reasoning_content:
            content = reasoning_content

        # Extract tool calls
        tool_calls = []
        raw_tcs = msg.get("tool_calls") or []
        for tc in raw_tcs:
            fn = tc.get("function", {})
            args = fn.get("arguments", "")
            parsed_args = args if isinstance(args, dict) else parse_tool_arguments(args)
            tool_calls.append(ToolCall(
                id=tc.get("id", ""),
                name=fn.get("name", ""),
                arguments=parsed_args,
            ))

        usage_data = data.get("usage", {})
        usage = TokenUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        return LLMResponse(
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
            model=model,
            provider=self.provider_name,
            usage=usage,
            finish_reason=choice.get("finish_reason", "stop"),
            cost_usd=self._calculate_cost(usage),
        )

    async def _complete_anthropic(self, request: LLMRequest) -> LLMResponse:
        """Complete via Anthropic's Claude API."""
        model = request.model or self.default_model
        system_prompt, messages = self._to_anthropic_messages(request)
        tools = self._to_anthropic_tools(request.tools)

        if self._anthropic_client:
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
            }
            if system_prompt:
                kwargs["system"] = system_prompt
            if tools:
                kwargs["tools"] = tools

            response = await self._anthropic_client.messages.create(**kwargs)

            content = ""
            tool_calls = []
            for block in response.content:
                if block.type == "text":
                    content += block.text
                elif block.type == "tool_use":
                    tool_calls.append(ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    ))

            usage = TokenUsage(
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            )

            return LLMResponse(
                content=content,
                model=model,
                provider=self.provider_name,
                tool_calls=tool_calls,
                usage=usage,
                finish_reason=response.stop_reason or "stop",
                cost_usd=self._calculate_cost(usage),
            )
        else:
            # Fallback to raw httpx for Anthropic
            return await self._complete_httpx_anthropic(
                model, system_prompt, messages, request, tools
            )

    async def _complete_httpx_anthropic(
        self,
        model: str,
        system_prompt: str,
        messages: list[dict],
        request: LLMRequest,
        tools: list[dict] | None,
    ) -> LLMResponse:
        """Fallback: raw HTTP request for Anthropic API."""
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(
                f"{self.base_url}/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        content = ""
        tool_calls = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
            elif block.get("type") == "tool_use":
                raw_input = block.get("input", {})
                parsed_args = raw_input if isinstance(raw_input, dict) else parse_tool_arguments(str(raw_input))
                tool_calls.append(ToolCall(
                    id=block.get("id", ""),
                    name=block.get("name", ""),
                    arguments=parsed_args,
                ))

        usage_data = data.get("usage", {})
        usage = TokenUsage(
            prompt_tokens=usage_data.get("input_tokens", 0),
            completion_tokens=usage_data.get("output_tokens", 0),
            total_tokens=(
                usage_data.get("input_tokens", 0) + usage_data.get("output_tokens", 0)
            ),
        )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            model=model,
            provider=self.provider_name,
            usage=usage,
            finish_reason=data.get("stop_reason", "stop"),
            cost_usd=self._calculate_cost(usage),
        )

    # ============================================
    # Stream (Async Generator)
    # ============================================

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        """Stream a completion. Auto-detects Anthropic vs OpenAI format."""
        if self.is_anthropic:
            async for chunk in self._stream_anthropic(request):
                yield chunk
        else:
            async for chunk in self._stream_openai(request):
                yield chunk

    async def _stream_openai(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        """Stream via OpenAI-compatible API."""
        model = request.model or self.default_model

        if self._openai_client:
            messages = self._to_openai_messages(request)
            stream = await self._openai_client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=self._effective_max_tokens(request.max_tokens),
                temperature=request.temperature,
                stream=True,
            )

            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    c_text = delta.content or ""
                    r_text = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None) or ""
                    if c_text or r_text:
                        yield LLMChunk(content=c_text, reasoning_content=r_text)
                    if chunk.choices[0].finish_reason:
                        yield LLMChunk(
                            is_final=True,
                            finish_reason=chunk.choices[0].finish_reason,
                        )
        else:
            # httpx streaming fallback
            messages = self._to_openai_messages(request)
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": self._effective_max_tokens(request.max_tokens),
                "temperature": request.temperature,
                "stream": True,
            }
            reasoning_models = ("gpt-oss", "deepseek-r1", "deepseek-reasoner", "reasoning", "o1", "o3")
            if request.reasoning_effort:
                payload["reasoning_effort"] = request.reasoning_effort
            elif any(rm in model.lower() for rm in reasoning_models):
                payload["reasoning_effort"] = "high"
            if request.extra_body:
                payload.update(request.extra_body)

            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                ) as resp:
                    async for line in resp.aiter_lines():
                        if line.startswith("data: ") and line != "data: [DONE]":
                            data = json.loads(line[6:])
                            if data.get("choices"):
                                delta = data["choices"][0].get("delta", {})
                                c_text = delta.get("content") or ""
                                r_text = delta.get("reasoning_content") or delta.get("reasoning") or ""
                                if c_text or r_text:
                                    yield LLMChunk(content=c_text, reasoning_content=r_text)
                                if data["choices"][0].get("finish_reason"):
                                    yield LLMChunk(
                                        is_final=True,
                                        finish_reason=data["choices"][0]["finish_reason"],
                                    )

    async def _stream_anthropic(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        """Stream via Anthropic API."""
        model = request.model or self.default_model

        if self._anthropic_client:
            system_prompt, messages = self._to_anthropic_messages(request)
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
            }
            if system_prompt:
                kwargs["system"] = system_prompt

            async with self._anthropic_client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield LLMChunk(content=text)

                final = await stream.get_final_message()
                yield LLMChunk(
                    is_final=True,
                    finish_reason=final.stop_reason,
                    usage=TokenUsage(
                        prompt_tokens=final.usage.input_tokens,
                        completion_tokens=final.usage.output_tokens,
                        total_tokens=final.usage.input_tokens + final.usage.output_tokens,
                    ),
                )
        else:
            # Anthropic httpx streaming would go here
            # For now, fall back to non-streaming
            response = await self._complete_anthropic(request)
            yield LLMChunk(content=response.content, is_final=True)

    # ============================================
    # Model Info & Health
    # ============================================

    def list_models(self) -> list[ModelInfo]:
        """Return model info for this provider's configured model."""
        return [
            ModelInfo(
                id=self.default_model,
                provider=self.provider_name,
                name=f"{self.name} / {self.default_model}",
                speed_tier=self.speed_tier,
                cost_per_1k_input=self.cost_per_1k_input,
                cost_per_1k_output=self.cost_per_1k_output,
                max_context_tokens=self.max_context_tokens,
                capabilities=self.capabilities,
                is_available=True,
            )
        ]

    async def health_check(self) -> bool:
        """Verify this provider is reachable with a minimal request."""
        try:
            LLMRequest(
                messages=[{"role": "user", "content": "ping"}],
                model=self.default_model,
                max_tokens=5,
                temperature=0,
            )
            # Use a quick httpx call instead of full completion
            if self.is_anthropic:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(
                        f"{self.base_url}",
                        headers={"x-api-key": self.api_key},
                    )
                    return resp.status_code < 500
            else:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(
                        f"{self.base_url}/models",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                    )
                    return resp.status_code < 500
        except Exception as e:
            logger.warning("health_check_failed", provider=self.name, error=str(e))
            return False

    def __repr__(self) -> str:
        return (
            f"<CustomLLMProvider name={self.name!r} "
            f"base_url={self.base_url!r} "
            f"model={self.default_model!r}>"
        )
