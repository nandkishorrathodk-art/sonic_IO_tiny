"""
SONIC-REDA — Model Router
============================
Routes LLM requests to the right provider based on:
    - Task type (planning, reasoning, fast_recon, coding, etc.)
    - Config from models.yaml
    - Fallback chains if primary provider fails

The router manages multiple CustomLLMProvider instances.
Team configures providers in models.yaml or via API.

Usage:
    router = ModelRouter.from_config("configs/models.yaml")
    
    # Route by task type
    response = await router.complete(request, task_type="reasoning")
    
    # Use specific provider
    response = await router.complete(request, provider_name="grok")
    
    # Stream
    async for chunk in router.stream(request, task_type="coding"):
        print(chunk.content, end="")
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import yaml

from sonic.logger import get_logger

logger = get_logger(__name__)

from sonic.llm.providers.custom import CustomLLMProvider
from sonic.llm.schemas import (
    CostRecord,
    LLMChunk,
    LLMRequest,
    LLMResponse,
    SpeedTier,
)


class ModelRouter:
    """
    Central router that manages multiple LLM providers and routes requests.
    
    Providers are CustomLLMProvider instances configured with:
        - name, base_url, api_key, default_model
        
    Routing rules map task types to preferred providers with fallback chains.
    """

    def __init__(self):
        self.providers: dict[str, CustomLLMProvider] = {}
        self.routing_rules: dict[str, dict] = {}
        self.fallback_chain: list[str] = []
        self.default_provider: str = ""
        self.cost_records: list[CostRecord] = []

        # Cost limits
        self.max_per_request_usd: float = 1.0
        self.max_per_engagement_usd: float = 50.0

    # ============================================
    # Setup
    # ============================================

    def add_provider(self, provider: CustomLLMProvider) -> None:
        """Register a provider with the router."""
        self.providers[provider.name] = provider
        logger.info(
            "provider_registered",
            name=provider.name,
            base_url=provider.base_url,
            model=provider.default_model,
        )

    def add_provider_from_config(
        self,
        name: str,
        base_url: str,
        api_key: str,
        default_model: str,
        **kwargs: Any,
    ) -> CustomLLMProvider:
        """Create and register a provider from config values."""
        provider = CustomLLMProvider(
            name=name,
            base_url=base_url,
            api_key=api_key,
            default_model=default_model,
            **kwargs,
        )
        self.add_provider(provider)
        return provider

    @classmethod
    def from_config(cls, config_path: str | Path, env_vars: dict[str, str] | None = None) -> "ModelRouter":
        """
        Create a fully configured ModelRouter from a YAML config file.
        
        Args:
            config_path: Path to models.yaml
            env_vars: Dict of environment variables (for API keys).
                      If None, reads from os.environ.
        """
        import os
        env = env_vars or dict(os.environ)

        config_path = Path(config_path)
        if not config_path.exists():
            logger.warning("config_not_found", path=str(config_path))
            return cls()

        with open(config_path) as f:
            config = yaml.safe_load(f)

        router = cls()
        router.default_provider = config.get("default_provider", "")
        router.fallback_chain = config.get("global_fallback_chain", [])

        # Load cost limits
        cost_limits = config.get("cost_limits", {})
        router.max_per_request_usd = cost_limits.get("max_per_request_usd", 1.0)
        router.max_per_engagement_usd = cost_limits.get("max_per_engagement_usd", 50.0)

        # Register providers from config
        providers_config = config.get("providers", {})
        for provider_name, pconfig in providers_config.items():
            # Resolve API key from env var
            api_key_env = pconfig.get("api_key_env", "")
            base_url_env = pconfig.get("base_url_env", "")

            api_key = env.get(api_key_env, "") if api_key_env else ""
            base_url = env.get(base_url_env, pconfig.get("base_url", "")) if base_url_env else pconfig.get("base_url", "")

            if not base_url:
                logger.debug("provider_skipped_no_url", name=provider_name)
                continue

            # Get first model as default, rest as fallback chain
            models = pconfig.get("models", [])
            if not models:
                continue

            first_model = models[0]
            # Remaining models serve as model-level fallback (EOL/not-found recovery)
            fallback_model_ids = [m["id"] for m in models[1:]]
            speed_map = {"fast": SpeedTier.FAST, "medium": SpeedTier.MEDIUM, "slow": SpeedTier.SLOW}

            router.add_provider_from_config(
                name=provider_name,
                base_url=base_url,
                api_key=api_key,
                default_model=first_model["id"],
                cost_per_1k_input=first_model.get("cost_per_1k_input", 0.0),
                cost_per_1k_output=first_model.get("cost_per_1k_output", 0.0),
                speed_tier=speed_map.get(first_model.get("speed_tier", "medium"), SpeedTier.MEDIUM),
                capabilities=first_model.get("capabilities", []),
                fallback_models=fallback_model_ids,
            )

        # Load routing rules
        rules_config = config.get("routing_rules", {})
        for task_type, rule in rules_config.items():
            router.routing_rules[task_type] = {
                "provider": rule.get("provider", router.default_provider),
                "model": rule.get("model"),
                "fallback": rule.get("fallback", []),
                "description": rule.get("description", ""),
            }

        logger.info(
            "router_loaded",
            providers=list(router.providers.keys()),
            rules=list(router.routing_rules.keys()),
        )
        return router

    # ============================================
    # Routing Logic
    # ============================================

    def _resolve_provider(
        self,
        provider_name: str | None = None,
        task_type: str | None = None,
    ) -> tuple[CustomLLMProvider, str | None]:
        """
        Resolve which provider to use based on task_type or explicit provider name.
        
        Returns:
            (provider, model_override) tuple
        """
        # Explicit provider name takes priority
        if provider_name and provider_name in self.providers:
            return self.providers[provider_name], None

        # Route by task type
        if task_type and task_type in self.routing_rules:
            rule = self.routing_rules[task_type]
            target_provider = rule["provider"]
            target_model = rule.get("model")

            if target_provider in self.providers:
                return self.providers[target_provider], target_model

            # Try fallbacks from the rule
            for fallback in rule.get("fallback", []):
                fb_provider = fallback.split("/")[0] if "/" in fallback else fallback
                if fb_provider in self.providers:
                    fb_model = fallback.split("/")[1] if "/" in fallback else None
                    logger.info(
                        "routing_fallback",
                        task_type=task_type,
                        original=target_provider,
                        fallback=fb_provider,
                    )
                    return self.providers[fb_provider], fb_model

        # Use default provider
        if self.default_provider in self.providers:
            return self.providers[self.default_provider], None

        # Last resort: use first available provider
        if self.providers:
            first_name = next(iter(self.providers))
            logger.warning("routing_last_resort", provider=first_name)
            return self.providers[first_name], None

        raise RuntimeError("No LLM providers configured. Add at least one provider.")

    # ============================================
    # Complete & Stream
    # ============================================

    async def complete(
        self,
        request: LLMRequest,
        task_type: str | None = None,
        provider_name: str | None = None,
    ) -> LLMResponse:
        """
        Route and complete an LLM request.
        
        Args:
            request: The LLM request to send
            task_type: Optional task type for routing (e.g., "reasoning", "coding")
            provider_name: Optional explicit provider name
            
        Returns:
            LLMResponse from the selected provider
        """
        # Use request's task_type if not explicitly provided
        effective_task = task_type or request.task_type
        provider, model_override = self._resolve_provider(provider_name, effective_task)

        # Override model if routing rule specifies one
        if model_override and not request.model:
            request.model = model_override

        # Set task metadata
        request.task_type = effective_task

        try:
            response = await provider.complete_with_timing(request)

            # Track cost
            self.cost_records.append(CostRecord(
                request_id=response.request_id,
                provider=response.provider,
                model=response.model,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                cost_usd=response.cost_usd,
                agent_id=request.agent_id,
                engagement_id=request.engagement_id,
            ))

            return response

        except Exception as e:
            logger.error(
                "complete_failed",
                provider=provider.name,
                error=str(e),
                task_type=effective_task,
            )
            # Try fallback chain
            return await self._try_fallbacks(request, provider.name, effective_task)

    async def _try_fallbacks(
        self,
        request: LLMRequest,
        failed_provider: str,
        task_type: str | None,
    ) -> LLMResponse:
        """Try fallback providers when the primary fails."""
        # Get fallback chain from routing rule or global
        fallbacks = self.fallback_chain

        if task_type and task_type in self.routing_rules:
            rule_fallbacks = self.routing_rules[task_type].get("fallback", [])
            if rule_fallbacks:
                fallbacks = [
                    fb.split("/")[0] if "/" in fb else fb
                    for fb in rule_fallbacks
                ] + self.fallback_chain

        for fb_name in fallbacks:
            if fb_name == failed_provider or fb_name not in self.providers:
                continue

            logger.info("trying_fallback", provider=fb_name, task_type=task_type)
            try:
                fb_provider = self.providers[fb_name]
                return await fb_provider.complete_with_timing(request)
            except Exception as e:
                logger.warning("fallback_failed", provider=fb_name, error=str(e))
                continue

        raise RuntimeError(
            f"All providers failed for task_type={task_type}. "
            f"Tried: {failed_provider} + {fallbacks}"
        )

    async def stream(
        self,
        request: LLMRequest,
        task_type: str | None = None,
        provider_name: str | None = None,
    ) -> AsyncIterator[LLMChunk]:
        """Route and stream an LLM request."""
        effective_task = task_type or request.task_type
        provider, model_override = self._resolve_provider(provider_name, effective_task)

        if model_override and not request.model:
            request.model = model_override

        async for chunk in provider.stream(request):
            yield chunk

    # ============================================
    # Info & Stats
    # ============================================

    async def health_check_all(self) -> dict[str, bool]:
        """Check health of all registered providers."""
        results = {}
        for name, provider in self.providers.items():
            results[name] = await provider.health_check()
        return results

    def get_all_models(self) -> list[dict]:
        """List all available models across all providers."""
        models = []
        for provider in self.providers.values():
            for model in provider.list_models():
                models.append(model.model_dump())
        return models

    def get_total_cost(self, engagement_id: str | None = None) -> float:
        """Get total cost in USD, optionally filtered by engagement."""
        records = self.cost_records
        if engagement_id:
            records = [r for r in records if r.engagement_id == engagement_id]
        return sum(r.cost_usd for r in records)

    def get_stats(self) -> dict:
        """Get router-level statistics.

        Provider stats are derived from cost_records (single source of truth) so
        they never diverge from the router-level totals on partial failures or
        provider fallback.
        """
        provider_stats: dict[str, dict] = {}
        for name, provider in self.providers.items():
            prov_records = [r for r in self.cost_records if r.provider.value == provider.provider_name.value]
            provider_stats[name] = {
                "provider": provider.provider_name,
                "total_requests": len(prov_records),
                "total_tokens": sum(r.input_tokens + r.output_tokens for r in prov_records),
                "total_cost_usd": round(sum(r.cost_usd for r in prov_records), 6),
            }
        return {
            "providers": provider_stats,
            "total_cost_usd": round(self.get_total_cost(), 6),
            "total_requests": len(self.cost_records),
            "routing_rules": list(self.routing_rules.keys()),
        }
