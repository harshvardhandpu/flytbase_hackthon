from __future__ import annotations

import logging
import time

import httpx

from app.config import Settings, get_settings
from app.core.contracts import AIRequest, AIResponse, ProviderError
from app.providers.base import ConfiguredProvider

logger = logging.getLogger(__name__)

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

        model = request.model or self._settings.openai_model or _OPENAI_DEFAULT_MODEL

        # ── Debug: log AI request metadata ─────────────────────────────
        logger.info(
            "[AI REQUEST] provider=%s base_url=%s model=%s key_set=%s",
            self.name,
            base_url,
            model,
            bool(api_key),
        )

        if not api_key:
            raise ProviderError(
                provider=self.name,
                status_code=None,
                message="OPENAI_API_KEY is not configured",
            )

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

        start = time.monotonic()
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    f"{base_url.rstrip('/')}/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
            except httpx.RequestError as exc:
                latency = time.monotonic() - start
                logger.error(
                    "[AI RESPONSE] provider=%s success=false latency=%.2fs error=RequestError: %s",
                    self.name,
                    latency,
                    exc,
                )
                raise ProviderError(
                    provider=self.name,
                    status_code=None,
                    message=f"Request failed: {exc}",
                ) from exc

        latency = time.monotonic() - start

        if response.status_code != 200:
            detail = _extract_openai_error(response)
            logger.error(
                "[AI RESPONSE] provider=%s success=false latency=%.2fs "
                "status_code=%s error=%s",
                self.name,
                latency,
                response.status_code,
                detail,
            )
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

        logger.info(
            "[AI RESPONSE] provider=%s success=true latency=%.2fs "
            "model=%s total_tokens=%s finish_reason=%s",
            self.name,
            latency,
            data.get("model", model),
            usage.get("total_tokens", "?"),
            choice.get("finish_reason", "?"),
        )

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
