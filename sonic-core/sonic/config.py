"""
SONIC-REDA — Global Configuration
===================================
Loads settings from environment variables and .env files.
Single source of truth for all configuration across the system.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Project root directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIGS_DIR = PROJECT_ROOT / "configs"


class AuthSettings(BaseSettings):
    """Google OAuth2 + JWT configuration."""

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    allowed_emails: list[str] = Field(default_factory=list)
    allowed_domains: list[str] = Field(default_factory=list)
    jwt_secret: str = "CHANGE-ME"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24


class LLMSettings(BaseSettings):
    """LLM API keys and routing configuration."""

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    xai_api_key: str = ""
    deepseek_api_key: str = ""
    local_llm_url: str = "http://localhost:11434"
    default_llm_provider: str = "claude"


class DatabaseSettings(BaseSettings):
    """Neo4j and Redis connection settings."""

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    redis_url: str = "redis://localhost:6379/0"


class AppSettings(BaseSettings):
    """Application-level settings."""

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:8000"]
    )


class Settings(BaseSettings):
    """
    Master settings — aggregates all sub-settings.
    Loads from .env file at project root.
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Sub-settings (flattened for env var loading)
    # -- Auth --
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    allowed_emails: str = ""  # Comma-separated in env
    allowed_domains: str = ""  # Comma-separated in env
    jwt_secret: str = "CHANGE-ME"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24

    # -- LLM --
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    xai_api_key: str = ""
    deepseek_api_key: str = ""
    local_llm_url: str = "http://localhost:11434"
    default_llm_provider: str = "claude"

    # -- Database --
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    redis_url: str = "redis://localhost:6379/0"

    # -- App --
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000,http://localhost:8000"

    # ---- Computed Properties ----

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"

    @property
    def allowed_emails_list(self) -> list[str]:
        """Parse comma-separated emails into a list."""
        if not self.allowed_emails:
            return []
        return [e.strip() for e in self.allowed_emails.split(",") if e.strip()]

    @property
    def allowed_domains_list(self) -> list[str]:
        """Parse comma-separated domains into a list."""
        if not self.allowed_domains:
            return []
        return [d.strip() for d in self.allowed_domains.split(",") if d.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        if not self.cors_origins:
            return []
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Call this everywhere instead of creating new Settings().
    """
    return Settings()
