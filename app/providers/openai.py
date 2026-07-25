from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.core.contracts import AIRequest, AIResponse, ProviderError
from app.providers.base import ConfiguredProvider

logger = logging.getLogger(__name__)

_OPENAI_DEFAULT_MODEL = "gpt-4o"
_OPENAI_DEFAULT_BASE_URL = "https://api.openai.com"
_NVIDIA_HOST = "integrate.api.nvidia.com"

# ── Request throttling ─────────────────────────────────────────────────
# Global semaphore shared across all OpenAIProvider instances (via module
# singleton) to prevent concurrent requests from overwhelming the provider.
# NVIDIA DeepSeek has a per-worker limit of 48 concurrent requests. One
# inbound simulation triggers ~6 AI calls across Research + Qualification +
# Inbound + Pipeline agents. With semaphore=1 only one request is active
# at a time, preventing ResourceExhausted amplification.
_AI_REQUEST_LIMIT = 1
_ai_semaphore = asyncio.Semaphore(_AI_REQUEST_LIMIT)

_MAX_RETRIES = 1
_RETRY_BASE_DELAY = 2.0  # seconds


class OpenAIProvider(ConfiguredProvider):
    """Adapter for OpenAI's Chat Completions API.

    Uses plain ``httpx`` — no OpenAI SDK dependency.
    Compatible with any OpenAI-compatible endpoint by setting ``OPENAI_BASE_URL``.

    Throttling & resilience:
    - Global ``asyncio.Semaphore`` limits concurrent requests to
      ``AI_REQUEST_LIMIT=2``.
    - On 503 ``ResourceExhausted``, retries once after 2 s backoff
      (``_MAX_RETRIES=1``).
    - If the provider still returns 503 after the retry, a degraded
      ``AIResponse`` is returned instead of raising ``ProviderError``,
      allowing downstream agents to continue with best-effort results.

    NVIDIA DeepSeek support:
    - Auto-detects NVIDIA endpoint via base URL
    - Adds ``chat_template_kwargs`` with ``thinking=true`` and
      ``reasoning_effort="high"`` for deeper reasoning
    """

    name = "openai"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def generate(self, request: AIRequest) -> AIResponse:
        raw_base_url = self._settings.openai_base_url or _OPENAI_DEFAULT_BASE_URL
        api_key = self._settings.openai_api_key

        model = request.model or self._settings.openai_model or _OPENAI_DEFAULT_MODEL

        # Normalise base URL: strip trailing /v1 to avoid double-path
        # when users set OPENAI_BASE_URL=https://integrate.api.nvidia.com/v1
        base_url = _normalize_openai_base_url(raw_base_url)

        # Detect NVIDIA DeepSeek endpoint for special handling
        is_nvidia = _NVIDIA_HOST in base_url

        # Build the final request URL once for debug logging
        request_url = f"{base_url}/v1/chat/completions"

        # ── Debug: log AI request metadata ─────────────────────────────
        agent_label = request.metadata.get("agent", "unknown")
        logger.info(
            "[AI REQUEST] provider=%s agent=%s base_url=%s request_url=%s model=%s "
            "key_set=%s nvidia=%s",
            self.name,
            agent_label,
            base_url,
            request_url,
            model,
            bool(api_key),
            is_nvidia,
        )

        if not api_key:
            raise ProviderError(
                provider=self.name,
                status_code=None,
                message="OPENAI_API_KEY is not configured",
            )

        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        # ── NVIDIA DeepSeek: add chat_template_kwargs ──────────────────
        if is_nvidia:
            payload["chat_template_kwargs"] = {
                "thinking": True,
                "reasoning_effort": "high",
            }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        }

        # ── Throttle: wait for semaphore before hitting the provider ────
        logger.info(
            "[AI QUEUE] provider=%s waiting (limit=%s active=%s)",
            self.name,
            _AI_REQUEST_LIMIT,
            _AI_REQUEST_LIMIT - _ai_semaphore._value,  # pyright: ignore
        )
        async with _ai_semaphore:
            logger.info("[AI QUEUE] provider=%s acquired semaphore", self.name)

            # ── Retry loop for 503 ResourceExhausted ───────────────────
            last_exc: Exception | None = None
            for attempt in range(1, _MAX_RETRIES + 1):
                try:
                    return await self._post_with_retry(
                        request_url=request_url,
                        headers=headers,
                        payload=payload,
                        model=model,
                        attempt=attempt,
                    )
                except ProviderError as exc:
                    last_exc = exc
                    # Only retry on 503 ResourceExhausted
                    if exc.status_code != 503:
                        raise
                    if attempt < _MAX_RETRIES:
                        delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                        logger.warning(
                            "[AI RETRY] provider=%s attempt=%s/%s status=503 "
                            "retry_after=%.1fs error=%s",
                            self.name,
                            attempt,
                            _MAX_RETRIES,
                            delay,
                            exc.message,
                        )
                        await asyncio.sleep(delay)

            # All retries exhausted — return degraded response
            last_error = last_exc.message if isinstance(last_exc, ProviderError) else "unknown"
            logger.error(
                "[AI FALLBACK] provider=%s after %s retries — returning degraded "
                "response. error=%s",
                self.name,
                _MAX_RETRIES,
                last_error,
            )
            return AIResponse(
                content=(
                    "[AI provider temporarily unavailable — using fallback analysis. "
                    f"Reason: {last_error}]"
                ),
                model=model,
                provider=self.name,
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                raw_metadata={
                    "status": "degraded",
                    "reason": last_error,
                    "retries_attempted": _MAX_RETRIES,
                    "semaphore_limit": _AI_REQUEST_LIMIT,
                },
            )

    async def _post_with_retry(
        self,
        *,
        request_url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        model: str,
        attempt: int,
    ) -> AIResponse:
        start = time.monotonic()

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    request_url,
                    headers=headers,
                    json=payload,
                )
            except httpx.RequestError as exc:
                latency = time.monotonic() - start
                logger.error(
                    "[AI RESPONSE] provider=%s success=false latency=%.2fs "
                    "error=RequestError: %s",
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

        if response.status_code == 503:
            detail = _extract_openai_error(response)
            logger.error(
                "[AI RESPONSE] provider=%s success=false latency=%.2fs "
                "status_code=503 attempt=%s/%s error=%s",
                self.name,
                latency,
                attempt,
                _MAX_RETRIES,
                detail,
            )
            raise ProviderError(
                provider=self.name,
                status_code=503,
                message=detail,
            )

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
            "model=%s total_tokens=%s finish_reason=%s attempt=%s/%s",
            self.name,
            latency,
            data.get("model", model),
            usage.get("total_tokens", "?"),
            choice.get("finish_reason", "?"),
            attempt,
            _MAX_RETRIES,
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


def _normalize_openai_base_url(url: str) -> str:
    """Strip trailing ``/v1`` so the provider can safely append ``/v1/chat/completions``.

    Handles:
    - ``https://integrate.api.nvidia.com``        → keeps as-is
    - ``https://integrate.api.nvidia.com/v1``      → strips ``/v1``
    - ``https://integrate.api.nvidia.com/v1/``     → strips trailing ``/v1/``
    - ``https://api.openai.com``                  → keeps as-is
    """
    stripped = url.rstrip("/")
    if stripped.endswith("/v1"):
        stripped = stripped[:-3]
    return stripped.rstrip("/")


def _extract_openai_error(response: httpx.Response) -> str:
    try:
        body = response.json()
        err = body.get("error", {})
        return err.get("message", str(response.status_code))
    except Exception:
        return response.text[:500] or f"HTTP {response.status_code}"
