"""Tests for OpenAI provider retry / 503 ResourceExhausted handling."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.core.contracts import AIMessage, AIRequest, ProviderError
from app.providers import openai as openai_mod
from app.providers.openai import (
    _MAX_ATTEMPTS,
    _PROVIDER_MAX_TOKENS_CAP,
    OpenAIProvider,
    _is_retryable_provider_error,
    _message_is_capacity_error,
)


def _settings() -> Settings:
    return Settings(
        openai_api_key="sk-test",
        openai_base_url="https://api.openai.com",
        openai_model="gpt-4o-mini",
    )


def _request(*, agent: str = "research", max_tokens: int = 1600) -> AIRequest:
    return AIRequest(
        messages=[
            AIMessage(role="system", content="sys"),
            AIMessage(role="user", content="user compact signals"),
        ],
        temperature=0.1,
        max_tokens=max_tokens,
        metadata={"agent": agent},
    )


def _http_response(status_code: int, body: dict | None = None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    if body is not None:
        resp.json.return_value = body
    else:
        resp.json.side_effect = Exception("no json")
    resp.text = text or str(status_code)
    return resp


def _success_body(content: str = '{"description":"ok"}') -> dict:
    return {
        "model": "gpt-4o-mini",
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }


class TestCapacityDetection:
    def test_resource_exhausted_message(self) -> None:
        msg = "ResourceExhausted: Worker local total request limit reached (48/48)"
        assert _message_is_capacity_error(msg) is True

    def test_is_retryable_503(self) -> None:
        exc = ProviderError(provider="openai", status_code=503, message="busy")
        assert _is_retryable_provider_error(exc) is True

    def test_is_retryable_429(self) -> None:
        exc = ProviderError(provider="openai", status_code=429, message="rate limit")
        assert _is_retryable_provider_error(exc) is True

    def test_not_retryable_401(self) -> None:
        exc = ProviderError(provider="openai", status_code=401, message="bad key")
        assert _is_retryable_provider_error(exc) is False


class TestOpenAIRetryBehavior:
    @pytest.mark.asyncio
    async def test_successful_synthesis_first_attempt(self) -> None:
        provider = OpenAIProvider(settings=_settings())
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(
            return_value=_http_response(200, _success_body('{"ok":true}'))
        )

        with (
            patch.object(openai_mod.httpx, "AsyncClient", return_value=mock_client),
            patch.object(openai_mod.asyncio, "sleep", new_callable=AsyncMock) as sleep,
        ):
            result = await provider.generate(_request())

        assert result.content == '{"ok":true}'
        assert result.raw_metadata.get("status") != "degraded"
        assert mock_client.post.await_count == 1
        sleep.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_503_then_success_on_second_attempt(self) -> None:
        provider = OpenAIProvider(settings=_settings())
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(
            side_effect=[
                _http_response(
                    503,
                    {
                        "error": {
                            "message": (
                                "ResourceExhausted: Worker local total "
                                "request limit reached (48/48)"
                            )
                        }
                    },
                ),
                _http_response(200, _success_body('{"description":"recovered"}')),
            ]
        )

        with (
            patch.object(openai_mod.httpx, "AsyncClient", return_value=mock_client),
            patch.object(openai_mod.asyncio, "sleep", new_callable=AsyncMock) as sleep,
        ):
            result = await provider.generate(_request())

        assert result.content == '{"description":"recovered"}'
        assert mock_client.post.await_count == 2
        # First failure → delay 2.0s before retry
        sleep.assert_awaited()
        assert sleep.await_args_list[0].args[0] == 2.0

    @pytest.mark.asyncio
    async def test_503_all_attempts_return_degraded_fallback(self) -> None:
        provider = OpenAIProvider(settings=_settings())
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        fail = _http_response(
            503,
            {
                "error": {
                    "message": (
                        "ResourceExhausted: Worker local total "
                        "request limit reached (48/48)"
                    )
                }
            },
        )
        mock_client.post = AsyncMock(side_effect=[fail, fail, fail])

        with (
            patch.object(openai_mod.httpx, "AsyncClient", return_value=mock_client),
            patch.object(openai_mod.asyncio, "sleep", new_callable=AsyncMock) as sleep,
        ):
            result = await provider.generate(_request())

        assert mock_client.post.await_count == _MAX_ATTEMPTS
        assert result.raw_metadata.get("status") == "degraded"
        assert "fallback" in result.content.lower() or "unavailable" in result.content.lower()
        # Delays 2, 5, 10 after each of 3 failures
        delays = [c.args[0] for c in sleep.await_args_list]
        assert delays == [2.0, 5.0, 10.0]

    @pytest.mark.asyncio
    async def test_payload_max_tokens_capped(self) -> None:
        provider = OpenAIProvider(settings=_settings())
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(
            return_value=_http_response(200, _success_body("ok"))
        )

        with patch.object(openai_mod.httpx, "AsyncClient", return_value=mock_client):
            await provider.generate(_request(max_tokens=8000))

        sent = mock_client.post.await_args.kwargs["json"]
        assert sent["max_tokens"] == _PROVIDER_MAX_TOKENS_CAP
        assert sent["temperature"] == 0.1

    @pytest.mark.asyncio
    async def test_non_retryable_error_raises_immediately(self) -> None:
        provider = OpenAIProvider(settings=_settings())
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(
            return_value=_http_response(401, {"error": {"message": "invalid api key"}})
        )

        with (
            patch.object(openai_mod.httpx, "AsyncClient", return_value=mock_client),
            patch.object(openai_mod.asyncio, "sleep", new_callable=AsyncMock) as sleep,
            pytest.raises(ProviderError) as ei,
        ):
            await provider.generate(_request())

        assert ei.value.status_code == 401
        assert mock_client.post.await_count == 1
        sleep.assert_not_awaited()


class TestResearchFallbackOnDegraded:
    @pytest.mark.asyncio
    async def test_research_uses_structured_fallback_when_provider_degraded(
        self,
    ) -> None:
        """Degraded AI response must not empty research evidence."""
        import uuid
        from unittest.mock import MagicMock

        from app.agents.research import ResearchAgent
        from app.core.contracts import AgentContext, AgentTaskInput, AIResponse
        from app.tools import SimulatedContentExtractorTool, SimulatedWebSearchTool, ToolManager

        class DegradedAI:
            name = "openai"

            async def generate(self, request: AIRequest) -> AIResponse:
                return AIResponse(
                    content="[AI provider temporarily unavailable — using fallback analysis.]",
                    provider="openai",
                    raw_metadata={"status": "degraded", "reason": "ResourceExhausted"},
                )

        tools = ToolManager(
            [SimulatedWebSearchTool(), SimulatedContentExtractorTool()]
        )
        tm = MagicMock()
        tm.append_log.return_value = None
        agent = ResearchAgent(
            ai_provider=DegradedAI(),  # type: ignore[arg-type]
            tool_manager=tools,
            task_manager=tm,
        )
        result = await agent.run(
            AgentContext(task_id=uuid.uuid4(), correlation_id="t"),
            AgentTaskInput(
                id=uuid.uuid4(),
                agent_type="research",
                input_data={"company_name": "FlytBase", "domain": "flytbase.com"},
            ),
        )
        findings = result.output_data["findings"]
        assert findings["company_overview"]
        assert findings["latest_news"] or findings["recent_signals"]
        assert findings["operational_pain_points"] or findings["buying_signals"]
        assert findings["sources"]
        assert findings.get("recommended_sales_angle") or findings.get("why_now")
        assert findings.get("next_action") or findings.get("recommended_next_action")
