"""
SONIC-REDA — LLM Routes
===========================
Test endpoints for the Custom LLM Provider + Model Router.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sonic.auth.middleware import require_auth
from sonic.auth.models import User
from sonic.config import CONFIGS_DIR
from sonic.llm.router import ModelRouter
from sonic.llm.schemas import LLMRequest, Message, MessageRole

router = APIRouter()

# Lazy-loaded router singleton
_model_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    """Get or create the Model Router singleton."""
    global _model_router
    if _model_router is None:
        config_path = CONFIGS_DIR / "models.yaml"
        _model_router = ModelRouter.from_config(config_path)
    return _model_router


class ChatRequest(BaseModel):
    """Simple chat request for testing."""
    message: str
    provider: str | None = None  # Explicit provider name
    model: str | None = None  # Explicit model override
    task_type: str | None = None  # Routing hint
    temperature: float = 0.7
    max_tokens: int = 2048


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user: User = Depends(require_auth),
):
    """
    Send a chat message through the Model Router.
    Useful for testing provider connectivity and routing.
    """
    router_instance = get_model_router()

    if not router_instance.providers:
        raise HTTPException(
            status_code=503,
            detail="No LLM providers configured. Check your API keys in .env",
        )

    llm_request = LLMRequest(
        messages=[
            Message(role=MessageRole.USER, content=request.message),
        ],
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        task_type=request.task_type,
    )

    try:
        response = await router_instance.complete(
            llm_request,
            task_type=request.task_type,
            provider_name=request.provider,
        )
        return {
            "content": response.content,
            "model": response.model,
            "provider": response.provider,
            "usage": response.usage.model_dump(),
            "latency_ms": round(response.latency_ms, 1),
            "cost_usd": round(response.cost_usd, 6),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"LLM request failed: {str(e)}",
        )


@router.get("/providers")
async def list_providers(user: User = Depends(require_auth)):
    """List all configured LLM providers and their models."""
    router_instance = get_model_router()
    return {
        "providers": {
            name: {
                "base_url": p.base_url,
                "default_model": p.default_model,
                "capabilities": p.capabilities,
                "stats": p.get_stats(),
            }
            for name, p in router_instance.providers.items()
        },
        "routing_rules": router_instance.routing_rules,
        "default_provider": router_instance.default_provider,
    }


@router.get("/stats")
async def llm_stats(user: User = Depends(require_auth)):
    """Get LLM usage statistics and costs."""
    router_instance = get_model_router()
    return router_instance.get_stats()
