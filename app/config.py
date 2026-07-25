from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["anthropic", "openai", "freemodel", "local"]


def normalize_database_url(database_url: str) -> str:
    """Select SQLAlchemy's psycopg v3 dialect for standard PostgreSQL URLs.

    Railway supplies ``DATABASE_URL`` as ``postgresql://...``.  SQLAlchemy
    treats that scheme as the legacy psycopg2 dialect unless a driver is named
    explicitly, while this application installs psycopg v3.
    """
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


class Settings(BaseSettings):
    """Runtime configuration sourced from environment variables or `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ScoutOS"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://scoutos:scoutos@localhost:5432/scoutos"
    redis_url: str | None = None
    ai_provider: ProviderName | None = None
    anthropic_base_url: str | None = None
    anthropic_auth_token: str | None = None
    anthropic_model: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str | None = None
    local_model: str | None = None

    # ── Search provider settings ───────────────────────────────────────
    search_provider: str = "simulated"
    tavily_api_key: str | None = None

    @field_validator("database_url", mode="before")
    @classmethod
    def use_psycopg_v3(cls, value: str) -> str:
        return normalize_database_url(value)

    @field_validator("tavily_api_key", mode="before")
    @classmethod
    def sanitize_tavily_api_key(cls, value: object) -> str | None:
        """Normalize TAVILY_API_KEY from env / Railway UI paste.

        Strips whitespace and accidental surrounding quotes. Empty values
        become ``None`` so WebSearchTool reliably detects a missing key.
        Never log the raw value.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            return None
        cleaned = value.strip().strip('"').strip("'").strip()
        return cleaned or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
