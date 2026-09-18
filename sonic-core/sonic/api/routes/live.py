"""
SONIC-REDA — Live Settings Routes
=====================================
Runtime configuration surface for the dashboard Settings page.

Honesty note:
    Secrets are never returned. ``GET /live/settings`` reports whether an LLM
    API key is configured (``llm_api_key_set``) but never the key itself. The
    POST handler accepts a key for the live process and records that it was
    set; it is intentionally NOT echoed back.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from sonic.auth.middleware import require_auth, require_operator
from sonic.auth.models import User
from sonic.config import get_settings
from sonic.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Process-local runtime overrides. Kept in memory only — never persisted to
# disk and never returned to callers.
_runtime_overrides: dict[str, object] = {"llm_api_key_set": False}
_runtime_config: dict[str, object] = {}


class LiveSettingsUpdate(BaseModel):
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    daytona_url: str | None = None
    allowed_domains: list[str] | None = None


def _current_allowed_domains() -> list[str]:
    settings = get_settings()
    raw = getattr(settings, "cors_origins", "") or ""
    domains = [d.strip() for d in str(raw).split(",") if d.strip()]
    return domains or ["localhost", "127.0.0.1"]


@router.get("/live/settings")
async def get_live_settings(user: User = Depends(require_auth)):
    """Return the live, non-secret runtime configuration."""
    env_key_set = bool(os.environ.get("NVIDIA_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    return {
        "llm_base_url": _runtime_config.get("llm_base_url")
        or os.environ.get("NVIDIA_BASE_URL")
        or os.environ.get("LLM_BASE_URL")
        or "https://integrate.api.nvidia.com/v1",
        "llm_model": _runtime_config.get("llm_model")
        or os.environ.get("SONIC_AGENT_MODEL")
        or os.environ.get("DEFAULT_MODEL")
        or "",
        "llm_api_key_set": bool(env_key_set or _runtime_overrides.get("llm_api_key_set")),
        "daytona_url": _runtime_config.get("daytona_url")
        or os.environ.get("DAYTONA_API_URL")
        or "http://localhost:12000",
        "allowed_domains": _runtime_config.get("allowed_domains") or _current_allowed_domains(),
    }


@router.post("/live/settings")
async def update_live_settings(
    req: LiveSettingsUpdate,
    user: User = Depends(require_operator),
):
    """Apply live runtime settings to this process.

    The API key is applied to the process environment for subsequent LLM calls
    but is never returned. Settings are process-local and reset on restart.
    """
    if req.llm_base_url:
        _runtime_config["llm_base_url"] = req.llm_base_url
        os.environ["NVIDIA_BASE_URL"] = req.llm_base_url
    if req.llm_model:
        _runtime_config["llm_model"] = req.llm_model
        os.environ["SONIC_AGENT_MODEL"] = req.llm_model
    if req.daytona_url:
        _runtime_config["daytona_url"] = req.daytona_url
    if req.allowed_domains is not None:
        _runtime_config["allowed_domains"] = req.allowed_domains
    if req.llm_api_key:
        os.environ["NVIDIA_API_KEY"] = req.llm_api_key
        _runtime_overrides["llm_api_key_set"] = True
        logger.info("live_settings_api_key_updated", user=user.email)

    return {"status": "saved", "llm_api_key_set": bool(_runtime_overrides.get("llm_api_key_set"))}
