from __future__ import annotations

import logging
import time

import httpx

from app.config import Settings, get_settings
from app.core.contracts import AIRequest, AIResponse, ProviderError
from app.providers.base import ConfiguredProvider

logger = logging.getLogger(__name__)

_ANTHROPIC_DEFAULT_MODEL = "claude-3-5-sonnet-20241022"
_ANTHROPIC_API_VERSION = "2023-06-01"
_DEFAULT_MAX_TOKENS = 4096


class AnthropicProvider(ConfiguredProvider):
    """Adapter for Anthropic's Messages API.

    Uses plain ``httpx`` — no Anthropic SDK dependency.
    Inherited by ``FreeModelProvider`` for Anthropic-compatible endpoints.
    """

    name = "anthropic"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def generate(self, request: AIRequest) -> AIResponse:
        base_url = self._settings.anthropic_base_url or "https://api.anthropic.com"
        auth_token = self._settings.anthropic_auth_token

        model = request.model or self._settings.anthropic_model or _ANTHROPIC_DEFAULT_MODEL

        # ── Debug: log AI request metadata ─────────────────────────────
        logger.info(
            "[AI REQUEST] provider=%s base_url=%s model=%s key_set=%s",
            self.name,
            base_url,
            model,
            bool(auth_token),
        )

        if not auth_token:
            raise ProviderError(
                provider=self.name,
                status_code=None,
                message="ANTHROPIC_AUTH_TOKEN is not configured",
            )

        build_message = _build_anthropic_messages(request)
        payload: dict = {
            "model": model,
            "max_tokens": _DEFAULT_MAX_TOKENS,
            "messages": build_message["messages"],
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if build_message.get("system"):
            payload["system"] = build_message["system"]

        headers = {
            "x-api-key": auth_token,
            "anthropic-version": _ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }

        start = time.monotonic()
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    f"{base_url.rstrip('/')}/v1/messages",
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
            detail = _extract_error_detail(response)
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
        content = _extract_anthropic_content(data)
        usage: dict[str, int] = {
            "input_tokens": data.get("usage", {}).get("input_tokens", 0),
            "output_tokens": data.get("usage", {}).get("output_tokens", 0),
        }

        logger.info(
            "[AI RESPONSE] provider=%s success=true latency=%.2fs "
            "model=%s input_tokens=%s output_tokens=%s stop_reason=%s",
            self.name,
            latency,
            data.get("model", model),
            usage.get("input_tokens", "?"),
            usage.get("output_tokens", "?"),
            data.get("stop_reason", "?"),
        )

        return AIResponse(
            content=content,
            model=data.get("model", model),
            provider=self.name,
            usage=usage,
            raw_metadata={"stop_reason": data.get("stop_reason"), "type": data.get("type")},
        )


# ---- helpers (module-level for testability) ----


def _build_anthropic_messages(request: AIRequest) -> dict:
    """Split system messages from user/assistant messages.

    Anthropic's Messages API expects system instructions in a top-level
    ``system`` field rather than as a message with role ``system``.
    """
    system_parts: list[str] = []
    messages: list[dict[str, str]] = []

    for msg in request.messages:
        if msg.role == "system":
            system_parts.append(msg.content)
        else:
            messages.append({"role": msg.role, "content": msg.content})

    result: dict = {"messages": messages}
    if system_parts:
        result["system"] = "\n\n".join(system_parts)
    return result


def _extract_anthropic_content(data: dict) -> str:
    """Extract concatenated text from Anthropic's content-block response."""
    blocks = data.get("content", [])
    texts: list[str] = []
    for block in blocks:
        if block.get("type") == "text":
            texts.append(block.get("text", ""))
    return "\n".join(texts)


def _extract_error_detail(response: httpx.Response) -> str:
    """Pull a human-readable error message from the response body, or fall back to status."""
    try:
        body = response.json()
        err = body.get("error", {})
        return err.get("message", str(response.status_code))
    except Exception:
        return response.text[:500] or f"HTTP {response.status_code}"
