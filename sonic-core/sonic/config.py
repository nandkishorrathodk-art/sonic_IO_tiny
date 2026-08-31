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

from pydantic import AliasChoices, Field
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
    super_admin_emails: str = ""  # Comma-separated super-admin email addresses
    tenant_admin_emails: str = ""  # Comma-separated tenant-admin email addresses
    jwt_secret: str = Field(
        default="CHANGE-ME",
        validation_alias=AliasChoices("SECRET_KEY", "JWT_SECRET", "jwt_secret"),
    )
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
    cors_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:8000,http://127.0.0.1:8000,"
        "http://localhost:12000,http://127.0.0.1:12000,"
        "http://localhost:12001,http://127.0.0.1:12001"
    )

    # ---- Computed Properties ----

    # Secret values that must never be used outside local development.
    _INSECURE_JWT_SECRETS = {"CHANGE-ME", "", "secret", "changeme"}

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def validate_jwt_secret(self) -> tuple[bool, str]:
        """
        Validate the JWT signing secret.

        Returns (ok, reason). In production a weak/default secret is a hard
        failure; in development it is permitted but flagged for rotation.
        """
        secret = self.jwt_secret
        if secret in self._INSECURE_JWT_SECRETS:
            if self.is_production:
                return False, (
                    "jwt_secret is unset or default in production. Set a strong "
                    "(>=32 byte) random SECRET_KEY via environment before booting."
                )
            return True, "jwt_secret uses the development default; rotate before production."
        if len(secret) < 32 and self.is_production:
            return False, "jwt_secret must be at least 32 bytes in production."
        return True, "ok"

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
    def super_admin_emails_list(self) -> list[str]:
        if not self.super_admin_emails:
            return []
        return [e.strip().lower() for e in self.super_admin_emails.split(",") if e.strip()]

    @property
    def tenant_admin_emails_list(self) -> list[str]:
        if not self.tenant_admin_emails:
            return []
        return [e.strip().lower() for e in self.tenant_admin_emails.split(",") if e.strip()]

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
