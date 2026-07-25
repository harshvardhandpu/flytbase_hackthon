"""Tests for the WebSearchTool."""

from __future__ import annotations

import os

import pytest

from app.config import get_settings
from app.tools.web_search import WebSearchTool, resolve_tavily_api_key

_HAS_TAVILY_KEY = bool(get_settings().tavily_api_key or os.getenv("TAVILY_API_KEY"))


class TestWebSearchTool:
    """Tests for the simulated fallback path of WebSearchTool."""

    @pytest.fixture
    def tool(self) -> WebSearchTool:
        # Force simulated mode for tests (no API key configured)
        t = WebSearchTool()
        t._simulated = True
        return t

    @pytest.mark.asyncio
    async def test_simulated_search_returns_results(self, tool: WebSearchTool) -> None:
        result = await tool.execute({"query": "test company", "max_results": 3})
        assert result.content["result_count"] > 0
        assert len(result.sources) > 0
        assert result.content.get("simulated") is True

    @pytest.mark.asyncio
    async def test_simulated_search_flytbase_match(self, tool: WebSearchTool) -> None:
        result = await tool.execute({"query": "FlytBase drone platform", "max_results": 5})
        titles = [r["title"] for r in result.content["results"]]
        assert any("FlytBase" in t for t in titles)
        assert any("flytbase.com" in s.lower() for s in result.sources)

    @pytest.mark.asyncio
    async def test_simulated_search_drone_match(self, tool: WebSearchTool) -> None:
        result = await tool.execute({"query": "drone inspection software", "max_results": 3})
        titles = [r["title"] for r in result.content["results"]]
        assert any("Inspection" in t for t in titles)

    @pytest.mark.asyncio
    async def test_simulated_search_empty_query(self, tool: WebSearchTool) -> None:
        result = await tool.execute({"query": "", "max_results": 5})
        assert result.content["result_count"] > 0  # falls back to default results
        assert isinstance(result.content["results"], list)

    @pytest.mark.asyncio
    async def test_simulated_search_respects_max_results(self, tool: WebSearchTool) -> None:
        result = await tool.execute({"query": "FlytBase", "max_results": 2})
        assert result.content["result_count"] <= 2
        assert len(result.content["results"]) <= 2

    @pytest.mark.asyncio
    async def test_tavily_mode_known_api_key(self) -> None:
        """When simulated is False but no real API key, it should still fail gracefully."""
        tool = WebSearchTool()
        tool._simulated = False
        tool._api_key = ""
        result = await tool.execute({"query": "test", "max_results": 3})
        # Should fall back to simulated on API error
        assert result.content["result_count"] > 0
        assert result.content.get("simulated") is True

    @pytest.mark.asyncio
    async def test_missing_key_uses_fallback_provider(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Missing key must route to fallback and log provider=fallback."""
        import logging

        tool = WebSearchTool()
        tool._api_key = None
        tool._simulated = True
        with caplog.at_level(logging.INFO, logger="app.tools.web_search"):
            result = await tool.execute({"query": "BHP mining", "max_results": 2})
        assert result.content.get("simulated") is True
        assert any("[SEARCH] provider=fallback" in r.message for r in caplog.records)

    def test_resolve_tavily_api_key_prefers_os_environ(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Railway injects TAVILY_API_KEY into os.environ — that must win."""
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-from-environ")
        assert resolve_tavily_api_key() == "tvly-from-environ"

    def test_tavily_init_logs_key_present(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        monkeypatch.setenv("TAVILY_API_KEY", "tvly-init-check")
        with caplog.at_level(logging.INFO, logger="app.tools.web_search"):
            tool = WebSearchTool()
        assert tool._api_key == "tvly-init-check"
        assert not tool._simulated
        assert any(
            "[TAVILY INIT] key_present=true" in r.message for r in caplog.records
        )

    def test_tool_metadata(self, tool: WebSearchTool) -> None:
        assert tool.name == "web_search"
        assert "Search" in tool.description


@pytest.mark.skipif(not _HAS_TAVILY_KEY, reason="Requires TAVILY_API_KEY in .env")
class TestWebSearchRealApi:
    """Integration tests that hit the live Tavily API.

    These tests require ``TAVILY_API_KEY`` to be set in the environment
    or ``.env`` file. They are skipped automatically when no key is
    present so CI and fresh checkouts stay green.
    """

    @pytest.fixture(scope="class")
    def live_tool(self) -> WebSearchTool:
        tool = WebSearchTool()
        assert not tool._simulated, "Fix test setup: WebSearchTool is in simulated mode"
        return tool

    @pytest.mark.asyncio
    async def test_real_search_returns_live_results(self, live_tool: WebSearchTool) -> None:
        """Real API should return non-simulated results with real URLs."""
        result = await live_tool.execute({"query": "drone fleet management", "max_results": 3})

        assert result.content["result_count"] > 0
        # Real API responses must NOT carry the simulated flag
        assert result.content.get("simulated", False) is False
        # Every result should have a meaningful URL (not a placeholder domain)
        for r in result.content["results"]:
            assert r["url"]
            assert "example.com" not in r["url"]
            assert r["title"]
            assert r["snippet"]

    @pytest.mark.asyncio
    async def test_real_search_respects_max_results(self, live_tool: WebSearchTool) -> None:
        """The API should honour the max_results parameter."""
        result = await live_tool.execute({"query": "drone", "max_results": 2})
        assert result.content["result_count"] <= 2
        assert len(result.content["results"]) <= 2

    @pytest.mark.asyncio
    async def test_real_search_provides_sources(self, live_tool: WebSearchTool) -> None:
        """Real search should populate the sources list with real URLs."""
        result = await live_tool.execute({"query": "drone", "max_results": 3})
        assert result.sources
        for url in result.sources:
            assert url.startswith("http")
            assert "example.com" not in url

    @pytest.mark.asyncio
    async def test_real_search_api_key_detected(self) -> None:
        """WebSearchTool should initialize in non-simulated mode with a key present."""
        tool = WebSearchTool()
        assert not tool._simulated
        assert tool._api_key
