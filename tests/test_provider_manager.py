from app.config import Settings
from app.providers.manager import ProviderManager


def test_explicit_provider_wins_over_inference() -> None:
    settings = Settings(
        ai_provider="local",
        anthropic_base_url="https://cc.freemodel.dev",
        anthropic_auth_token="token",
    )
    assert ProviderManager(settings).resolve().name == "local"


def test_anthropic_compatible_credentials_select_freemodel() -> None:
    settings = Settings(anthropic_base_url="https://cc.freemodel.dev")
    assert ProviderManager(settings).resolve().name == "freemodel"


def test_missing_provider_is_explicitly_unavailable() -> None:
    # Explicitly clear all provider-related fields so .env values
    # don't leak into the test (Pydantic BaseSettings auto-loads from .env).
    settings = Settings(
        ai_provider=None,
        anthropic_base_url=None,
        anthropic_auth_token=None,
        openai_api_key=None,
    )
    assert ProviderManager(settings).resolve().name == "unavailable"
