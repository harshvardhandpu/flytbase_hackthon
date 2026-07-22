from app.providers.anthropic import AnthropicProvider


class FreeModelProvider(AnthropicProvider):
    """Anthropic-compatible provider selected for Freebuff-style endpoints."""

    name = "freemodel"
