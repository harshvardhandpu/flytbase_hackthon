from __future__ import annotations

import httpx

from app.config import Settings, get_settings
from app.core.contracts import AIRequest, AIResponse, ProviderError
from app.providers.base import ConfiguredProvider

_OPENAI_DEFAULT_MODEL = "gpt-4o"
_OPENAI_DEFAULT_BASE_URL = "https://api.openai.com"


class OpenAIProvider(ConfiguredProvider):
    """Adapter for OpenAI's Chat Completions API.

    Uses plain ``httpx`` — no OpenAI SDK dependency.
    Compatible with any OpenAI-compatible endpoint by setting ``OPENAI_BASE_URL``.
    """

    name = "openai"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def generate(self, request: AIRequest) -> AIResponse:
        base_url = self._settings.openai_base_url or _OPENAI_DEFAULT_BASE_URL
        api_key = self._settings.openai_api_key
        if not api_key:
            raise ProviderError(
                provider=self.name,
                status_code=None,
                message="OPENAI_API_KEY is not configured",
            )

        model = request.model or self._settings.openai_model or _OPENAI_DEFAULT_MODEL

        payload: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        headers = {
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    f"{base_url.rstrip('/')}/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
            except httpx.RequestError as exc:
                raise ProviderError(
                    provider=self.name,
                    status_code=None,
                    message=f"Request failed: {exc}",
                ) from exc

        if response.status_code != 200:
            detail = _extract_openai_error(response)
            raise ProviderError(
                provider=self.name,
                status_code=response.status_code,
                message=detail,
            )

        data = response.json()
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage: dict[str, int] = {
            "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
            "completion_tokens": data.get("usage", {}).get("completion_tokens", 0),
            "total_tokens": data.get("usage", {}).get("total_tokens", 0),
        }

        return AIResponse(
            content=message.get("content", ""),
            model=data.get("model", model),
            provider=self.name,
            usage=usage,
            raw_metadata={
                "finish_reason": choice.get("finish_reason"),
                "system_fingerprint": data.get("system_fingerprint"),
            },
        )


def _extract_openai_error(response: httpx.Response) -> str:
    try:
        body = response.json()
        err = body.get("error", {})
        return err.get("message", str(response.status_code))
    except Exception:
        return response.text[:500] or f"HTTP {response.status_code}"
