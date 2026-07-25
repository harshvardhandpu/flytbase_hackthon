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
# inbound simulation triggers multiple AI calls across agents. With
# semaphore=1 only one request is active at a time in this process.
_AI_REQUEST_LIMIT = 1
_ai_semaphore = asyncio.Semaphore(_AI_REQUEST_LIMIT)

# ── Retry policy for transient provider capacity errors ────────────────
# Production log pattern:
#   ResourceExhausted: Worker local total request limit reached (48/48)
# Previously _MAX_RETRIES=1 meant only ONE attempt (range(1, 2)) and
# immediate degraded fallback — that is the root cause of "after 1 retries".
_MAX_ATTEMPTS = 3
# Delay AFTER each failed attempt before the next try / final fallback.
# attempt1 fail → 2s, attempt2 fail → 5s, attempt3 fail → 10s then degrade.
_RETRY_DELAYS_SEC: tuple[float, ...] = (2.0, 5.0, 10.0)

# Cap outbound generation size at the provider boundary (research uses ≤1600).
_PROVIDER_MAX_TOKENS_CAP = 1600


class OpenAIProvider(ConfiguredProvider):
    """Adapter for OpenAI's Chat Completions API.

    Uses plain ``httpx`` — no OpenAI SDK dependency.
    Compatible with any OpenAI-compatible endpoint by setting ``OPENAI_BASE_URL``.

    Throttling & resilience:
    - Global ``asyncio.Semaphore`` limits concurrent requests to 1 in-process.
    - On 503 / ResourceExhausted / rate-limit style errors, retries up to
      ``_MAX_ATTEMPTS`` (3) with delays 2s → 5s → 10s.
    - If the provider still fails after all attempts, a degraded
      ``AIResponse`` is returned instead of raising ``ProviderError``,
      allowing ResearchAgent (and others) to use structured fallbacks.

    NVIDIA DeepSeek support:
    - Auto-detects NVIDIA endpoint via base URL
    - Adds ``chat_template_kwargs`` for reasoning models
    """

    name = "openai"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def generate(self, request: AIRequest) -> AIResponse:
        raw_base_url = self._settings.openai_base_url or _OPENAI_DEFAULT_BASE_URL
        api_key = self._settings.openai_api_key

        model = request.model or self._settings.openai_model or _OPENAI_DEFAULT_MODEL

        # Normalise base URL: strip trailing /v1 to avoid double-path
        base_url = _normalize_openai_base_url(raw_base_url)
        is_nvidia = _NVIDIA_HOST in base_url
        request_url = f"{base_url}/v1/chat/completions"

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
            # Bound generation size under provider capacity pressure.
            # Research requests already use ≤1600; other agents may request less.
            payload["max_tokens"] = min(int(request.max_tokens), _PROVIDER_MAX_TOKENS_CAP)

        if is_nvidia:
            # Prefer lower-overhead settings under worker capacity pressure.
            payload["chat_template_kwargs"] = {
                "thinking": False,
                "reasoning_effort": "medium",
            }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        }

        logger.info(
            "[AI QUEUE] provider=%s waiting (limit=%s active=%s)",
            self.name,
            _AI_REQUEST_LIMIT,
            _AI_REQUEST_LIMIT - _ai_semaphore._value,  # pyright: ignore
        )

        async with _ai_semaphore:
            logger.info("[AI QUEUE] provider=%s acquired semaphore", self.name)

            last_exc: ProviderError | None = None
            for attempt in range(1, _MAX_ATTEMPTS + 1):
                try:
                    response = await self._post_once(
                        request_url=request_url,
                        headers=headers,
                        payload=payload,
                        model=model,
                        attempt=attempt,
                        agent_label=agent_label,
                    )
                    if agent_label == "research":
                        logger.info(
                            "[AI SYNTHESIS] provider=%s success=true fallback=false "
                            "latency_note=see_prior_AI_RESPONSE attempt=%s",
                            self.name,
                            attempt,
                        )
                    return response
                except ProviderError as exc:
                    last_exc = exc
                    if not _is_retryable_provider_error(exc):
                        raise

                    delay = _RETRY_DELAYS_SEC[min(attempt - 1, len(_RETRY_DELAYS_SEC) - 1)]
                    if attempt < _MAX_ATTEMPTS:
                        logger.warning(
                            "[AI RETRY] attempt=%s delay=%.1f reason=%s",
                            attempt,
                            delay,
                            _safe_reason(exc.message),
                        )
                        await asyncio.sleep(delay)
                        continue

                    # Final attempt failed — optional pause then degrade
                    logger.warning(
                        "[AI RETRY] attempt=%s delay=%.1f reason=%s (final before fallback)",
                        attempt,
                        delay,
                        _safe_reason(exc.message),
                    )
                    await asyncio.sleep(delay)

            # All attempts exhausted — degraded response for agent fallbacks
            last_error = last_exc.message if last_exc else "unknown"
            safe = _safe_reason(last_error)
            logger.error(
                "[AI FALLBACK] provider=%s after %s attempts — returning degraded "
                "response. reason=%s",
                self.name,
                _MAX_ATTEMPTS,
                safe,
            )
            if agent_label == "research":
                logger.info(
                    "[AI SYNTHESIS] provider=%s success=false fallback=true reason=%s",
                    self.name,
                    safe,
                )
            return AIResponse(
                content=(
                    "[AI provider temporarily unavailable — using fallback analysis. "
                    f"Reason: {safe}]"
                ),
                model=model,
                provider=self.name,
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                raw_metadata={
                    "status": "degraded",
                    "reason": safe,
                    "attempts": _MAX_ATTEMPTS,
                    "semaphore_limit": _AI_REQUEST_LIMIT,
                },
            )

    async def _post_once(
        self,
        *,
        request_url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        model: str,
        attempt: int,
        agent_label: str,
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
                    "attempt=%s/%s error=RequestError: %s",
                    self.name,
                    latency,
                    attempt,
                    _MAX_ATTEMPTS,
                    type(exc).__name__,
                )
                raise ProviderError(
                    provider=self.name,
                    status_code=None,
                    message=f"Request failed: {exc}",
                ) from exc

        latency = time.monotonic() - start
        detail = _extract_openai_error(response)

        if response.status_code == 503 or _looks_like_resource_exhausted(
            response.status_code, detail
        ):
            logger.error(
                "[AI RESPONSE] provider=%s success=false latency=%.2fs "
                "status_code=%s attempt=%s/%s error=%s",
                self.name,
                latency,
                response.status_code,
                attempt,
                _MAX_ATTEMPTS,
                _safe_reason(detail),
            )
            raise ProviderError(
                provider=self.name,
                status_code=response.status_code if response.status_code else 503,
                message=detail,
            )

        if response.status_code != 200:
            logger.error(
                "[AI RESPONSE] provider=%s success=false latency=%.2fs "
                "status_code=%s attempt=%s/%s error=%s",
                self.name,
                latency,
                response.status_code,
                attempt,
                _MAX_ATTEMPTS,
                _safe_reason(detail),
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
            "model=%s total_tokens=%s finish_reason=%s attempt=%s/%s agent=%s",
            self.name,
            latency,
            data.get("model", model),
            usage.get("total_tokens", "?"),
            choice.get("finish_reason", "?"),
            attempt,
            _MAX_ATTEMPTS,
            agent_label,
        )

        return AIResponse(
            content=message.get("content", ""),
            model=data.get("model", model),
            provider=self.name,
            usage=usage,
            raw_metadata={
                "finish_reason": choice.get("finish_reason"),
                "system_fingerprint": data.get("system_fingerprint"),
                "attempt": attempt,
                "latency_s": round(latency, 3),
            },
        )


def _is_retryable_provider_error(exc: ProviderError) -> bool:
    """True for transient capacity / rate-limit style failures."""
    if exc.status_code in (429, 502, 503, 504):
        return True
    return _message_is_capacity_error(exc.message or "")


def _looks_like_resource_exhausted(status_code: int, detail: str) -> bool:
    if status_code in (429, 502, 503, 504):
        return True
    return _message_is_capacity_error(detail)


def _message_is_capacity_error(message: str) -> bool:
    lower = (message or "").lower()
    needles = (
        "resourceexhausted",
        "resource exhausted",
        "request limit reached",
        "worker local total",
        "rate limit",
        "too many requests",
        "temporarily unavailable",
        "overloaded",
        "capacity",
        "try again",
    )
    return any(n in lower for n in needles)


def _safe_reason(message: str, limit: int = 160) -> str:
    """Truncate provider error text; never pass secrets (none should be present)."""
    text = (message or "unknown").replace("\n", " ").strip()
    return text[:limit]


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
        if isinstance(err, dict):
            return str(err.get("message", response.status_code))
        return str(err) if err else str(response.status_code)
    except Exception:
        return response.text[:500] or f"HTTP {response.status_code}"
