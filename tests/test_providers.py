from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.config import Settings
from app.core.contracts import AIMessage, AIRequest, ProviderError
from app.providers.anthropic import (
    AnthropicProvider,
    _build_anthropic_messages,
    _extract_anthropic_content,
)
from app.providers.openai import OpenAIProvider

# =============================================================================
# Anthropic message helpers
# =============================================================================


class TestBuildAnthropicMessages:
    def test_separates_system_messages(self) -> None:
        request = AIRequest(
            messages=[
                AIMessage(role="system", content="You are a helpful assistant."),
                AIMessage(role="user", content="Hello"),
                AIMessage(role="assistant", content="Hi there"),
            ]
        )
        result = _build_anthropic_messages(request)
        assert result["system"] == "You are a helpful assistant."
        assert result["messages"] == [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

    def test_merges_multiple_system_messages(self) -> None:
        request = AIRequest(
            messages=[
                AIMessage(role="system", content="Rule one."),
                AIMessage(role="system", content="Rule two."),
                AIMessage(role="user", content="OK"),
            ]
        )
        result = _build_anthropic_messages(request)
        assert result["system"] == "Rule one.\n\nRule two."
        assert len(result["messages"]) == 1

    def test_no_system_message(self) -> None:
        request = AIRequest(messages=[AIMessage(role="user", content="Hello")])
        result = _build_anthropic_messages(request)
        assert "system" not in result
        assert len(result["messages"]) == 1

    def test_empty_messages(self) -> None:
        request = AIRequest(messages=[])
        result = _build_anthropic_messages(request)
        assert "system" not in result
        assert result["messages"] == []


class TestExtractAnthropicContent:
    def test_single_text_block(self) -> None:
        data = {"content": [{"type": "text", "text": "Hello world"}]}
        assert _extract_anthropic_content(data) == "Hello world"

    def test_multiple_text_blocks(self) -> None:
        data = {
            "content": [
                {"type": "text", "text": "Part one."},
                {"type": "text", "text": "Part two."},
            ]
        }
        assert _extract_anthropic_content(data) == "Part one.\nPart two."

    def test_skips_non_text_blocks(self) -> None:
        data = {
            "content": [
                {"type": "text", "text": "Hello"},
                {"type": "tool_use", "id": "abc", "name": "search", "input": {"q": "x"}},
            ]
        }
        assert _extract_anthropic_content(data) == "Hello"

    def test_empty_content(self) -> None:
        assert _extract_anthropic_content({"content": []}) == ""


# =============================================================================
# AnthropicProvider
# =============================================================================


class TestAnthropicProvider:
    @pytest.mark.asyncio
    async def test_raises_when_token_missing(self) -> None:
        settings = Settings(anthropic_base_url="https://api.example.com", anthropic_auth_token=None)
        provider = AnthropicProvider(settings=settings)
        with pytest.raises(ProviderError, match="ANTHROPIC_AUTH_TOKEN is not configured"):
            await provider.generate(AIRequest(messages=[]))

    @pytest.mark.asyncio
    async def test_generate_success(self) -> None:
        settings = Settings(
            anthropic_base_url="https://api.anthropic.com",
            anthropic_auth_token="sk-ant-test123",
            anthropic_model="claude-3-haiku-20240307",
        )
        provider = AnthropicProvider(settings=settings)

        fake_response = {
            "id": "msg_123",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello from Claude!"}],
            "model": "claude-3-haiku-20240307",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = httpx.Response(200, json=fake_response)

            result = await provider.generate(
                AIRequest(
                    messages=[AIMessage(role="user", content="Hello")],
                    temperature=0.5,
                )
            )

        assert result.content == "Hello from Claude!"
        assert result.model == "claude-3-haiku-20240307"
        assert result.provider == "anthropic"
        assert result.usage == {"input_tokens": 10, "output_tokens": 5}

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["model"] == "claude-3-haiku-20240307"
        assert call_kwargs["json"]["messages"] == [{"role": "user", "content": "Hello"}]
        assert call_kwargs["json"]["temperature"] == 0.5
        assert call_kwargs["headers"]["x-api-key"] == "sk-ant-test123"

    @pytest.mark.asyncio
    async def test_generate_with_system_message(self) -> None:
        settings = Settings(
            anthropic_base_url="https://api.anthropic.com",
            anthropic_auth_token="sk-ant-test123",
            anthropic_model="claude-3-haiku-20240307",
        )
        provider = AnthropicProvider(settings=settings)

        fake_response = {
            "id": "msg_456",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Understood."}],
            "model": "claude-3-haiku-20240307",
            "usage": {"input_tokens": 15, "output_tokens": 3},
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = httpx.Response(200, json=fake_response)

            result = await provider.generate(
                AIRequest(
                    messages=[
                        AIMessage(role="system", content="You are a BDR assistant."),
                        AIMessage(role="user", content="Research Acme Corp"),
                    ]
                )
            )

        assert result.content == "Understood."
        call_json = mock_post.call_args[1]["json"]
        assert "system" in call_json
        assert call_json["system"] == "You are a BDR assistant."
        assert all(m["role"] != "system" for m in call_json["messages"])

    @pytest.mark.asyncio
    async def test_generate_http_error(self) -> None:
        settings = Settings(
            anthropic_base_url="https://api.anthropic.com",
            anthropic_auth_token="sk-ant-test123",
        )
        provider = AnthropicProvider(settings=settings)

        error_body = {"error": {"type": "authentication_error", "message": "Invalid API key"}}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = httpx.Response(401, json=error_body)

            with pytest.raises(ProviderError) as exc:
                await provider.generate(AIRequest(messages=[AIMessage(role="user", content="Hi")]))

            assert exc.value.status_code == 401
            assert "Invalid API key" in str(exc.value)
            assert exc.value.provider == "anthropic"

    @pytest.mark.asyncio
    async def test_generate_network_error(self) -> None:
        settings = Settings(
            anthropic_base_url="https://api.anthropic.com",
            anthropic_auth_token="sk-ant-test123",
        )
        provider = AnthropicProvider(settings=settings)

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.RequestError("Connection refused")

            with pytest.raises(ProviderError, match="Connection refused"):
                await provider.generate(AIRequest(messages=[AIMessage(role="user", content="Hi")]))


# =============================================================================
# OpenAIProvider
# =============================================================================


class TestOpenAIProvider:
    @pytest.mark.asyncio
    async def test_raises_when_api_key_missing(self) -> None:
        settings = Settings(openai_base_url="https://api.openai.com", openai_api_key=None)
        provider = OpenAIProvider(settings=settings)
        with pytest.raises(ProviderError, match="OPENAI_API_KEY is not configured"):
            await provider.generate(AIRequest(messages=[]))

    @pytest.mark.asyncio
    async def test_generate_success(self) -> None:
        settings = Settings(
            openai_api_key="sk-test123",
            openai_model="gpt-4o-mini",
        )
        provider = OpenAIProvider(settings=settings)

        fake_response = {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 1720000000,
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello from GPT!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = httpx.Response(200, json=fake_response)

            result = await provider.generate(
                AIRequest(
                    messages=[AIMessage(role="user", content="Hello")],
                    temperature=0.7,
                )
            )

        assert result.content == "Hello from GPT!"
        assert result.model == "gpt-4o-mini"
        assert result.provider == "openai"
        assert result.usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["model"] == "gpt-4o-mini"
        assert call_kwargs["json"]["messages"] == [{"role": "user", "content": "Hello"}]
        assert call_kwargs["json"]["temperature"] == 0.7
        assert call_kwargs["headers"]["Authorization"] == "Bearer sk-test123"

    @pytest.mark.asyncio
    async def test_generate_with_system_message(self) -> None:
        settings = Settings(
            openai_api_key="sk-test123",
            openai_base_url="https://api.openai.com",
        )
        provider = OpenAIProvider(settings=settings)

        fake_response = {
            "id": "chatcmpl-456",
            "model": "gpt-4o",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "OK"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {},
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = httpx.Response(200, json=fake_response)

            result = await provider.generate(
                AIRequest(
                    messages=[
                        AIMessage(role="system", content="You are a BDR assistant."),
                        AIMessage(role="user", content="Research Acme Corp"),
                    ]
                )
            )

        assert result.content == "OK"
        call_json = mock_post.call_args[1]["json"]
        assert call_json["messages"] == [
            {"role": "system", "content": "You are a BDR assistant."},
            {"role": "user", "content": "Research Acme Corp"},
        ]

    @pytest.mark.asyncio
    async def test_generate_http_error(self) -> None:
        settings = Settings(
            openai_api_key="sk-test123",
            openai_base_url="https://api.openai.com",
        )
        provider = OpenAIProvider(settings=settings)

        error_body = {
            "error": {
                "message": "Incorrect API key provided",
                "type": "invalid_request_error",
            }
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = httpx.Response(401, json=error_body)

            with pytest.raises(ProviderError) as exc:
                await provider.generate(
                    AIRequest(messages=[AIMessage(role="user", content="Hi")])
                )

            assert exc.value.status_code == 401
            assert "Incorrect API key" in str(exc.value)
            assert exc.value.provider == "openai"

    @pytest.mark.asyncio
    async def test_generate_network_error(self) -> None:
        settings = Settings(
            openai_api_key="sk-test123",
            openai_base_url="https://api.openai.com",
        )
        provider = OpenAIProvider(settings=settings)

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.RequestError("Connection timed out")

            with pytest.raises(ProviderError, match="Connection timed out"):
                await provider.generate(
                    AIRequest(messages=[AIMessage(role="user", content="Hi")])
                )

    @pytest.mark.asyncio
    async def test_inherits_model_from_settings(self) -> None:
        settings = Settings(
            openai_api_key="sk-test123",
            openai_model="gpt-4-turbo",
        )
        provider = OpenAIProvider(settings=settings)

        fake_response = {
            "id": "chatcmpl-789",
            "model": "gpt-4-turbo",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "OK"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {},
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = httpx.Response(200, json=fake_response)
            result = await provider.generate(
                AIRequest(messages=[AIMessage(role="user", content="Hi")])
            )

        assert result.model == "gpt-4-turbo"
        call_json = mock_post.call_args[1]["json"]
        assert call_json["model"] == "gpt-4-turbo"
