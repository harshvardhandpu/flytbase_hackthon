from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["anthropic", "openai", "freemodel", "local"]


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


@lru_cache
def get_settings() -> Settings:
    return Settings()
