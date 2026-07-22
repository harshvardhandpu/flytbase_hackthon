from app.core.contracts import AIProvider, AIRequest, AIResponse


class ConfiguredProvider(AIProvider):
    """Adapter base; concrete SDK/network code is intentionally deferred."""

    name: str

    async def generate(self, request: AIRequest) -> AIResponse:
        raise NotImplementedError(f"{self.name} provider transport is not implemented in Phase 1")


class UnavailableProvider(ConfiguredProvider):
    name = "unavailable"

    async def generate(self, request: AIRequest) -> AIResponse:
        raise RuntimeError("No AI provider is configured. Set AI_PROVIDER and its credentials.")
