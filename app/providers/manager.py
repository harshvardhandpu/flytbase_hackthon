from app.config import Settings
from app.core.contracts import AIProvider
from app.providers.anthropic import AnthropicProvider
from app.providers.base import UnavailableProvider
from app.providers.freemodel import FreeModelProvider
from app.providers.local import LocalProvider
from app.providers.openai import OpenAIProvider


class ProviderManager:
    """Resolves configuration once; agents only receive the resulting contract."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def resolve(self) -> AIProvider:
        provider = self._settings.ai_provider
        if provider is None:
            if self._settings.anthropic_base_url or self._settings.anthropic_auth_token:
                provider = "freemodel"
            elif self._settings.openai_api_key:
                provider = "openai"

        match provider:
            case "anthropic":
                return AnthropicProvider(settings=self._settings)
            case "openai":
                return OpenAIProvider(settings=self._settings)
            case "freemodel":
                return FreeModelProvider(settings=self._settings)
            case "local":
                return LocalProvider()
            case _:
                return UnavailableProvider()
